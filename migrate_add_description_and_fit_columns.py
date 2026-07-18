"""
Fixes the gap where migrate_add_fit_scoring.py (referenced in fit_pipeline.py's
docstring) never actually ran against this jobs.db — likely because
CREATE TABLE IF NOT EXISTS silently no-ops when seen_jobs already exists from
Stage 1. This adds the missing columns directly via ALTER TABLE, plus a new
`description` column that was never part of any schema version (job
descriptions were only ever held in-memory at scoring time, never persisted).

Safe to re-run — checks for each column's existence before adding it.

Run:
    python migrate_add_description_and_fit_columns.py
"""
import sqlite3

DB_PATH = "jobs.db"

COLUMNS_TO_ADD = {
    "description": "TEXT",
    "prefilter_passed": "INTEGER",
    "prefilter_reasons": "TEXT",
    "llm_score": "INTEGER",
    "llm_recommendation": "TEXT",
    "llm_reasoning": "TEXT",
    "llm_flags": "TEXT",
    "alerted": "INTEGER DEFAULT 0",
}


def migrate(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(seen_jobs)")
    existing_columns = {row[1] for row in cur.fetchall()}

    for col_name, col_type in COLUMNS_TO_ADD.items():
        if col_name in existing_columns:
            print(f"  {col_name}: already exists, skipping")
            continue
        cur.execute(f"ALTER TABLE seen_jobs ADD COLUMN {col_name} {col_type}")
        print(f"  {col_name}: added")

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    migrate()
