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

from db import filter_new_jobs, count_seen
from notify import send_discord_notification
from sources import fetch_all_jobs

load_dotenv()  # no-op in CI (no .env file there); loads DISCORD_WEBHOOK_URL locally

COMPANIES_PATH = Path(__file__).parent / "companies.json"


def load_companies() -> dict:
    if not COMPANIES_PATH.exists():
        print(f"ERROR: {COMPANIES_PATH} not found.", file=sys.stderr)
        sys.exit(1)
    with open(COMPANIES_PATH) as f:
        return json.load(f)


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
    send_discord_notification(new_jobs)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
