"""
Stage 3 migration: adds `drafts` table to track resume/cover letter
generation and approval status for jobs that scored 7+ in Stage 2.

Run once against your existing job-radar SQLite DB:
    python migrate_stage3.py

Safe to re-run — checks for table existence first.
"""
import sqlite3
import sys

DB_PATH = "jobs.db"  # adjust if your db file has a different name/path


def migrate(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='drafts'
    """)
    if cur.fetchone():
        print("drafts table already exists — nothing to do.")
        conn.close()
        return

    cur.execute("""
        CREATE TABLE drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            resume_md TEXT,
            cover_letter_md TEXT,
            discord_message_id TEXT,
            discord_channel_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending_generation',
            -- status flow: pending_generation -> pending_approval
            --              -> approved | rejected -> completed
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (job_id) REFERENCES seen_jobs(id)
        )
    """)
    conn.commit()
    conn.close()
    print("Created `drafts` table.")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    migrate(db_path)
