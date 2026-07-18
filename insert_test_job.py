"""
Inserts a single fake job into `seen_jobs` with llm_score=8, so you can run
the full Stage 3 chain (draft_pipeline -> check_approvals -> execute_approved)
without waiting for a real posting to score 7+.

Requires migrate_add_description_and_fit_columns.py to have already been run
against jobs.db, since it writes to the description/llm_score/etc. columns.

Run:
    python insert_test_job.py

Then run the normal chain:
    python draft_pipeline.py
    (react 👍 in Discord)
    python check_approvals.py
    python execute_approved.py

Safe to run multiple times — job_key includes a timestamp so each run
inserts a distinct row.
"""
import sqlite3
import time

DB_PATH = "jobs.db"


def insert_test_job(conn: sqlite3.Connection) -> str:
    job_key = f"manual_test:teststage3:{int(time.time())}"

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO seen_jobs
            (job_key, source, company, title, location, url, description,
             prefilter_passed, prefilter_reasons,
             llm_score, llm_recommendation, llm_reasoning, llm_flags, alerted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_key,
        "manual_test",
        "TestCo Stage3 Validation",
        "Test AI Automation Engineer",
        "Remote (US)",
        "https://example.com/test-job-stage3",
        "We're looking for someone to build agentic workflows connecting "
        "internal tools, with a focus on human-in-the-loop review and "
        "low-code automation platforms. Remote-first, IC-focused role.",
        1,
        '["passed all prefilter checks - test data"]',
        8,
        "strong_match",
        "Inserted manually for Stage 3 smoke testing.",
        "[]",
        0,
    ))
    conn.commit()
    return job_key


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    job_key = insert_test_job(conn)
    print(f"Inserted test job with job_key = {job_key}")
    print("Now run: python draft_pipeline.py")
    conn.close()
