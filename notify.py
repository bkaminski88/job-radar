"""
notify.py — sends new job alerts to Discord via webhook.

A Discord webhook is just a URL you POST a JSON payload to — no OAuth,
no bot process to host. Set one up in Discord:
  Server Settings -> Integrations -> Webhooks -> New Webhook -> Copy URL

The URL is a secret (anyone with it can post to your channel), so it's
read from an environment variable, never hardcoded. Locally, put it in
a .env file (see .env.example). In GitHub Actions, it's a repo secret.
"""

import os
import requests

REQUEST_TIMEOUT = 10
DISCORD_CONTENT_LIMIT = 2000  # Discord's hard limit on a message's `content` field
DISCORD_SAFETY_MARGIN = 100  # headroom for the header line, emoji, and count digits


def _format_job_line(job: dict) -> str:
    location = f" — {job['location']}" if job.get("location") else ""
    line = f"**{job['title']}** at {job['company']}{location}\n{job.get('url', '')}"

    # Stage 2: jobs that went through fit_pipeline.evaluate_job() carry these
    # keys (see main.py). Plain Stage 1 jobs won't have them — render either way.
    if job.get("llm_score") is not None:
        line += f"\nFit: {job['llm_score']}/10 ({job.get('llm_recommendation', 'n/a')})"
        if job.get("llm_reasoning"):
            line += f"\n_{job['llm_reasoning']}_"
        flags = job.get("llm_flags") or []
        if flags:
            line += f"\nFlags: {', '.join(flags)}"

    return line


def _batch_job_lines(jobs: list[dict]) -> list[list[str]]:
    """
    Group formatted job lines into batches that fit Discord's 2000-char
    content limit. A fixed job-count-per-batch doesn't guarantee this once
    real LLM reasoning text is involved (a handful of verbose jobs alone can
    exceed 2000 chars), so batch by rendered size instead.
    """
    max_len = DISCORD_CONTENT_LIMIT - DISCORD_SAFETY_MARGIN
    batches: list[list[str]] = []
    current: list[str] = []
    current_len = 0

    for job in jobs:
        line = _format_job_line(job)
        if len(line) > max_len:
            # One job's own content is pathologically long (e.g. runaway LLM
            # reasoning) — truncate defensively so it can still be sent.
            line = line[: max_len - 1] + "…"
        sep_len = 2 if current else 0  # "\n\n" between entries
        if current and current_len + sep_len + len(line) > max_len:
            batches.append(current)
            current, current_len, sep_len = [], 0, 0
        current.append(line)
        current_len += sep_len + len(line)

    if current:
        batches.append(current)
    return batches


def send_discord_notification(jobs: list[dict], webhook_url: str | None = None) -> None:
    """
    Post one message per batch of jobs, sized to stay under Discord's
    2000-char content limit.
    """
    webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("No DISCORD_WEBHOOK_URL set — skipping notification, printing instead:")
        for job in jobs:
            print(" -", _format_job_line(job).replace("\n", " | "))
        return

    if not jobs:
        print("No new jobs to notify about.")
        return

    for batch in _batch_job_lines(jobs):
        content = f"\U0001F514 **{len(batch)} new job(s) found:**\n\n" + "\n\n".join(batch)
        try:
            resp = requests.post(
                webhook_url, json={"content": content}, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            # Don't let a Discord hiccup crash the whole run — log and move on.
            print(f"Failed to send Discord notification: {e}")
