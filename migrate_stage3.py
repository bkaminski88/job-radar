"""
Stage 3 migration: creates the `drafts` table, keyed on seen_jobs.job_key
(TEXT) since that's the real primary key — not an integer id.

If an earlier version of this table exists with the wrong schema (job_id
INTEGER instead of job_key TEXT) and has no rows in it yet, this drops and
recreates it. If it already has rows, it stops and warns you instead of
silently discarding data.

Run:
    python migrate_stage3.py
"""
import sqlite3
import sys

DB_PATH = "jobs.db"


def migrate(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='drafts'")
    table_exists = cur.fetchone() is not None

    if table_exists:
        cur.execute("PRAGMA table_info(drafts)")
        columns = {row[1] for row in cur.fetchall()}

        if "job_key" in columns:
            print("drafts table already has the correct schema — nothing to do.")
            conn.close()
            return

        cur.execute("SELECT COUNT(*) FROM drafts")
        row_count = cur.fetchone()[0]

        if row_count > 0:
            print(f"drafts table exists with the OLD schema and has {row_count} row(s). "
                  f"Refusing to drop it automatically — back up and migrate manually.")
            conn.close()
            sys.exit(1)

        print("drafts table exists with the old (incorrect) schema and no rows — "
              "dropping and recreating with job_key.")
        cur.execute("DROP TABLE drafts")

    cur.execute("""
        CREATE TABLE drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_key TEXT NOT NULL,
            resume_md TEXT,
            cover_letter_md TEXT,
            discord_message_id TEXT,
            discord_channel_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending_generation',
            -- status flow: pending_generation -> pending_approval
            --              -> approved | rejected -> completed
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (job_key) REFERENCES seen_jobs(job_key)
        )
    """)
    conn.commit()
    conn.close()
    print("Created `drafts` table with job_key schema.")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    migrate(db_path)
