"""
One-off inspection script: lists every table in jobs.db and its columns,
so we can see the real schema before wiring Stage 3 queries against it.

Run:
    python inspect_db.py
"""
import sqlite3

DB_PATH = "jobs.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cur.fetchall()]

for table in tables:
    print(f"\n=== {table} ===")
    cur.execute(f"PRAGMA table_info({table})")
    for cid, name, coltype, notnull, default, pk in cur.fetchall():
        pk_marker = " [PK]" if pk else ""
        print(f"  {name} ({coltype}){pk_marker}")

    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"  -> {count} row(s)")

conn.close()
