"""
Adds a framing_notes column to the existing drafts table (safe to re-run —
checks first). Needed now that resume_generator.py returns framing notes
alongside the tailored resume.

Run:
    python migrate_add_framing_notes.py
"""
import sqlite3

DB_PATH = "jobs.db"


def migrate(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(drafts)")
    columns = {row[1] for row in cur.fetchall()}

    if "framing_notes" in columns:
        print("framing_notes column already exists — nothing to do.")
    else:
        cur.execute("ALTER TABLE drafts ADD COLUMN framing_notes TEXT")
        print("Added framing_notes column to drafts.")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
