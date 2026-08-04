"""
send_test_notification.py — fires one synthetic job straight at
send_discord_notification(), bypassing fetch/dedupe/prefilter/LLM entirely.

Use this to isolate "is DISCORD_WEBHOOK_URL wired correctly" from "did
today's run find any new postings" — main.py's normal path sends nothing
at all (silently) when there are zero new jobs or zero jobs clear the fit
threshold, which looks identical to a broken webhook from the outside.

Run locally:
    python send_test_notification.py

Run in CI: see .github/workflows/test-notify.yml (workflow_dispatch)
"""
from dotenv import load_dotenv

from notify import send_discord_notification

load_dotenv()  # no-op in CI; loads DISCORD_WEBHOOK_URL locally

TEST_JOB = {
    "job_key": "manual_test:notify_smoke_test",
    "source": "manual_test",
    "company": "TestCo Notify Smoke Test",
    "title": "Test AI Automation Engineer",
    "location": "Remote (US)",
    "url": "https://example.com/test-job-notify",
    "llm_score": 9,
    "llm_recommendation": "strong_match",
    "llm_reasoning": "Synthetic job used only to confirm Discord delivery is wired correctly.",
    "llm_flags": [],
}


if __name__ == "__main__":
    print("Sending one synthetic job through send_discord_notification()...")
    send_discord_notification([TEST_JOB])
    print("Done. Check Discord for the message (or check the log above if DISCORD_WEBHOOK_URL is unset).")
