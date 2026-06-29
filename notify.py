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
DISCORD_BATCH_LIMIT = 10  # keep messages readable; split larger batches


def _format_job_line(job: dict) -> str:
    location = f" — {job['location']}" if job.get("location") else ""
    return f"**{job['title']}** at {job['company']}{location}\n{job.get('url', '')}"


def send_discord_notification(jobs: list[dict], webhook_url: str | None = None) -> None:
    """
    Post one message per batch of jobs to keep things readable in Discord.
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

    # Discord messages have a 2000-char limit; batch a handful per message
    # rather than firing one HTTP request per single job.
    for i in range(0, len(jobs), DISCORD_BATCH_LIMIT):
        batch = jobs[i : i + DISCORD_BATCH_LIMIT]
        content = f"\U0001F514 **{len(batch)} new job(s) found:**\n\n" + "\n\n".join(
            _format_job_line(j) for j in batch
        )
        try:
            resp = requests.post(
                webhook_url, json={"content": content}, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            # Don't let a Discord hiccup crash the whole run — log and move on.
            print(f"Failed to send Discord notification: {e}")
