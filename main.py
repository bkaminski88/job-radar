"""
main.py — orchestrates the job radar pipeline:

    fetch (Greenhouse + Lever) -> filter by keyword -> dedupe vs DB -> notify Discord

Run locally:
    python main.py

Run in CI: see .github/workflows/job-check.yml
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

from db import filter_new_jobs, count_seen, update_fit_result
from fit_pipeline import evaluate_job, evaluation_to_db_row
from notify import send_discord_notification
from prefilter import load_profile
from sources import fetch_all_jobs

load_dotenv()  # no-op in CI (no .env file there); loads DISCORD_WEBHOOK_URL / ANTHROPIC_API_KEY locally

COMPANIES_PATH = Path(__file__).parent / "companies.json"
PROFILE_PATH = Path(__file__).parent / "profile.json"


def load_companies() -> dict:
    if not COMPANIES_PATH.exists():
        print(f"ERROR: {COMPANIES_PATH} not found.", file=sys.stderr)
        sys.exit(1)
    with open(COMPANIES_PATH) as f:
        return json.load(f)


def score_and_filter(new_jobs: list[dict]) -> list[dict]:
    """
    Stage 2: runs each new job through the prefilter (free) and, for
    survivors, the LLM fit scorer (costs tokens). Persists results to the
    DB regardless of verdict. Returns only the jobs that should actually
    be alerted on Discord, enriched with fit fields for notify.py to render.
    """
    profile = load_profile(PROFILE_PATH)
    anthropic_client = Anthropic()  # reads ANTHROPIC_API_KEY from env

    to_alert = []
    for job in new_jobs:
        evaluation = evaluate_job(job, profile, anthropic_client)

        row = evaluation_to_db_row(evaluation)
        update_fit_result(job["job_key"], row)

        reasons_preview = "; ".join(evaluation.prefilter_result.reasons)
        if evaluation.llm_verdict is None:
            print(f"  [prefilter reject] {job['title']} @ {job['company']} — {reasons_preview}")
            continue

        verdict = evaluation.llm_verdict
        print(
            f"  [scored] {job['title']} @ {job['company']} — "
            f"{verdict.score}/10 ({verdict.recommendation})"
        )
        if evaluation.should_alert:
            job = {
                **job,
                "llm_score": verdict.score,
                "llm_recommendation": verdict.recommendation,
                "llm_reasoning": verdict.reasoning,
                "llm_flags": verdict.flags,
            }
            to_alert.append(job)

    return to_alert


def main():
    companies = load_companies()

    print("=" * 60)
    print("Job Radar — fetching postings")
    print("=" * 60)

    all_matching_jobs = fetch_all_jobs(companies)

    print()
    print(f"Total matching jobs this run: {len(all_matching_jobs)}")

    new_jobs = filter_new_jobs(all_matching_jobs)
    print(f"New jobs (not seen before): {len(new_jobs)}")
    print(f"Total jobs ever seen: {count_seen()}")

    print()
    print("Scoring new jobs against fit profile...")
    jobs_to_alert = score_and_filter(new_jobs)
    print(f"Jobs clearing fit threshold: {len(jobs_to_alert)}")

    print()
    send_discord_notification(jobs_to_alert)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
