"""
migrate_add_fit_scoring.py — one-time schema migration for Stage 2.

Adds columns to your existing jobs table (adjust TABLE_NAME below if yours
is named differently) to persist prefilter and LLM fit results, so you have
a queryable record beyond just the Discord ping.

Run once:
    python migrate_add_fit_scoring.py path/to/your/jobradar.db
"""

import sqlite3
import sys

TABLE_NAME = "seen_jobs"  # matches db.py's schema

NEW_COLUMNS = [
    ("prefilter_passed", "INTEGER"),       # 0/1
    ("prefilter_reasons", "TEXT"),          # JSON-encoded list of strings
    ("llm_score", "INTEGER"),               # 1-10, NULL if not scored
    ("llm_recommendation", "TEXT"),         # strong_match / worth_a_look / marginal / poor_fit / error
    ("llm_reasoning", "TEXT"),
    ("llm_flags", "TEXT"),                  # JSON-encoded list of strings
    ("alerted", "INTEGER DEFAULT 0"),       # whether it was actually sent to Discord
]


def migrate(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(f"PRAGMA table_info({TABLE_NAME})")
    existing_cols = {row[1] for row in cur.fetchall()}

    if not existing_cols:
        print(f"Warning: table '{TABLE_NAME}' not found or has no columns. "
              f"Double check TABLE_NAME matches your existing schema.")
        conn.close()
        return

    added = []
    for col_name, col_type in NEW_COLUMNS:
        if col_name not in existing_cols:
            cur.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {col_name} {col_type}")
            added.append(col_name)

    conn.commit()
    conn.close()

    if added:
        print(f"Added columns to '{TABLE_NAME}': {', '.join(added)}")
    else:
        print(f"No changes needed - all columns already present on '{TABLE_NAME}'.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python migrate_add_fit_scoring.py path/to/jobradar.db")
        sys.exit(1)
    migrate(sys.argv[1])
