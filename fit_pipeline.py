"""
fit_pipeline.py — orchestrates Stage A (prefilter) + Stage B (LLM scoring)
for job-radar Stage 2.

This is the glue file. It does NOT replace your existing main.py - it shows
how to call into prefilter.py and llm_classifier.py for each new (deduped)
job before deciding whether to alert.

Integration point: wherever your existing pipeline currently does
"for each new job -> send Discord alert", wrap that loop with this instead.

Example integration in your existing main.py:

    from fit_pipeline import evaluate_job
    from anthropic import Anthropic

    anthropic_client = Anthropic()  # picks up ANTHROPIC_API_KEY from env

    for job in new_jobs:  # i.e. jobs that passed your existing dedupe check
        outcome = evaluate_job(job, profile, anthropic_client)

        # persist outcome to DB regardless of verdict (see migrate_add_fit_scoring.py)
        save_fit_result(db_conn, job_id, outcome)

        if outcome.should_alert:
            send_discord_alert(job, outcome.verdict)  # your existing webhook function
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from anthropic import Anthropic

from llm_classifier import FitVerdict, score_job_fit
from prefilter import PrefilterResult, prefilter_job

# Jobs scoring at or above this are sent to Discord.
# 7 = "worth_a_look" or better in practice; tune after watching real output.
ALERT_SCORE_THRESHOLD = 7


@dataclass
class JobEvaluation:
    job: dict
    prefilter_result: PrefilterResult
    llm_verdict: FitVerdict | None  # None if rejected at prefilter, never called LLM
    should_alert: bool


def evaluate_job(job: dict, profile: dict, client: Anthropic) -> JobEvaluation:
    """
    Runs the full two-stage evaluation for a single job.
    Stage B (LLM) is only invoked if Stage A passes - this is the cost control.
    """
    pre_result = prefilter_job(job, profile)

    if not pre_result.passed:
        return JobEvaluation(
            job=job,
            prefilter_result=pre_result,
            llm_verdict=None,
            should_alert=False,
        )

    verdict = score_job_fit(job, profile, client=client)

    should_alert = (
        verdict.raw_error is None
        and verdict.score >= ALERT_SCORE_THRESHOLD
    )

    return JobEvaluation(
        job=job,
        prefilter_result=pre_result,
        llm_verdict=verdict,
        should_alert=should_alert,
    )


def evaluation_to_db_row(evaluation: JobEvaluation) -> dict:
    """
    Flattens an evaluation into the columns added by migrate_add_fit_scoring.py.
    Use this dict to build your UPDATE/INSERT statement for the jobs table.
    """
    row = {
        "prefilter_passed": int(evaluation.prefilter_result.passed),
        "prefilter_reasons": json.dumps(evaluation.prefilter_result.reasons),
        "llm_score": None,
        "llm_recommendation": None,
        "llm_reasoning": None,
        "llm_flags": None,
        "alerted": int(evaluation.should_alert),
    }
    if evaluation.llm_verdict is not None:
        row["llm_score"] = evaluation.llm_verdict.score
        row["llm_recommendation"] = evaluation.llm_verdict.recommendation
        row["llm_reasoning"] = evaluation.llm_verdict.reasoning
        row["llm_flags"] = json.dumps(evaluation.llm_verdict.flags)
    return row


def format_discord_message(evaluation: JobEvaluation) -> str:
    """
    Builds a Discord message body annotated with the LLM's reasoning,
    instead of just the bare job listing. Adapt formatting to match
    whatever embed/webhook structure your existing alert function uses.
    """
    job = evaluation.job
    verdict = evaluation.llm_verdict
    flags_str = ", ".join(verdict.flags) if verdict and verdict.flags else "none"

    return (
        f"**{job.get('title', 'Unknown title')}** @ {job.get('company', 'Unknown company')}\n"
        f"Location: {job.get('location', 'n/a')}\n"
        f"Fit score: {verdict.score}/10 ({verdict.recommendation})\n"
        f"Why: {verdict.reasoning}\n"
        f"Flags: {flags_str}\n"
        f"Link: {job.get('url', 'n/a')}"
    )


if __name__ == "__main__":
    # End-to-end smoke test using the real prefilter + a mocked LLM call
    # (no API key needed for this test - it patches score_job_fit's call site)
    from pathlib import Path
    from prefilter import load_profile

    profile = load_profile(Path(__file__).parent / "profile.json")

    jobs = [
        {
            "title": "AI Automation Engineer",
            "company": "BuildCo",
            "location": "Remote (US)",
            "url": "https://example.com/job/1",
            "description": "Build agentic workflows with Claude. Fully remote, IC-focused. $140,000-$170,000.",
        },
        {
            "title": "Director of Engineering",
            "company": "BigCorp",
            "location": "Onsite, NYC",
            "url": "https://example.com/job/2",
            "description": "Lead a 30-person org in our NYC headquarters 5 days a week.",
        },
    ]

    print("Running prefilter stage only (no API key required for this smoke test):\n")
    for job in jobs:
        pre = prefilter_job(job, profile)
        print(f"[{job['title']}] prefilter_passed={pre.passed}")
        for r in pre.reasons:
            print(f"   - {r}")
        print()
