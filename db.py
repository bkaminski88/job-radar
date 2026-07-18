"""
db.py — SQLite storage for seen jobs.

We use SQLite because it's a single file with zero setup. Since GitHub
Actions runs in a fresh container every time, the workflow is responsible
for restoring this file before the run and committing it back afterward
(see .github/workflows/job-check.yml). That's what makes state persist
across otherwise-stateless runs.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    job_key TEXT PRIMARY KEY,   -- "{source}:{company}:{job_id}" — globally unique
    source TEXT NOT NULL,       -- "greenhouse" or "lever"
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    url TEXT,
    description TEXT,           -- full job description text, needed by Stage 3 drafting
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    prefilter_passed INTEGER,   -- 0/1, Stage 2 rule-based prefilter result
    prefilter_reasons TEXT,     -- JSON-encoded list of strings
    llm_score INTEGER,          -- 1-10, NULL if never scored (e.g. prefilter rejected)
    llm_recommendation TEXT,    -- strong_match / worth_a_look / marginal / poor_fit / error
    llm_reasoning TEXT,
    llm_flags TEXT,             -- JSON-encoded list of strings
    alerted INTEGER DEFAULT 0   -- whether this job was actually sent to Discord
);
"""
# NOTE: CREATE TABLE IF NOT EXISTS only matters for brand-new databases.
# If you're applying this schema change to an EXISTING jobs.db, this alone
# won't add the new `description` column — run
# migrate_add_description_and_fit_columns.py once against your existing file.


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create the table if it doesn't exist yet. Safe to call every run."""
    with get_conn() as conn:
        conn.execute(SCHEMA)
        conn.commit()


def filter_new_jobs(jobs: list[dict]) -> list[dict]:
    """
    Given a list of normalized job dicts (see sources.py for shape),
    return only the ones we haven't seen before, AND record them as seen.

    We only care about brand-new postings (per the project's design
    decision), so this is a simple "have I seen this job_key before?"
    check — no diffing of descriptions or update timestamps.
    """
    init_db()
    new_jobs = []
    with get_conn() as conn:
        for job in jobs:
            existing = conn.execute(
                "SELECT 1 FROM seen_jobs WHERE job_key = ?", (job["job_key"],)
            ).fetchone()
            if existing is None:
                new_jobs.append(job)
                conn.execute(
                    """INSERT INTO seen_jobs
                       (job_key, source, company, title, location, url, description)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job["job_key"],
                        job["source"],
                        job["company"],
                        job["title"],
                        job.get("location", ""),
                        job.get("url", ""),
                        job.get("description", ""),
                    ),
                )
        conn.commit()
    return new_jobs


def update_fit_result(job_key: str, fit_row: dict) -> None:
    """
    Write Stage 2 fit-scoring results back to the row for an already-inserted
    job (filter_new_jobs already created the row with the base columns; this
    fills in the prefilter/LLM columns afterward).

    fit_row: dict produced by fit_pipeline.evaluation_to_db_row(), expected
    keys: prefilter_passed, prefilter_reasons, llm_score, llm_recommendation,
    llm_reasoning, llm_flags, alerted.
    """
    with get_conn() as conn:
        conn.execute(
            """UPDATE seen_jobs
               SET prefilter_passed = ?,
                   prefilter_reasons = ?,
                   llm_score = ?,
                   llm_recommendation = ?,
                   llm_reasoning = ?,
                   llm_flags = ?,
                   alerted = ?
               WHERE job_key = ?""",
            (
                fit_row["prefilter_passed"],
                fit_row["prefilter_reasons"],
                fit_row["llm_score"],
                fit_row["llm_recommendation"],
                fit_row["llm_reasoning"],
                fit_row["llm_flags"],
                fit_row["alerted"],
                job_key,
            ),
        )
        conn.commit()


def count_seen() -> int:
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()
        return row[0] if row else 0
