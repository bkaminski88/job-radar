"""
Run this on a schedule (e.g. every 30 min via GitHub Actions) after
draft_pipeline.py has posted drafts for approval.

For every draft with status='pending_approval', checks whether YOU
(your Discord user ID, not the bot) reacted with 👍 or 👎, and updates
status to 'approved' or 'rejected' accordingly.

Requires DISCORD_BOT_TOKEN and DISCORD_USER_ID (your own Discord user ID,
found via Discord Developer Mode -> right-click your name -> Copy User ID)
as env vars / repo secrets.
"""
import os
import sqlite3
import requests

DB_PATH = "jobs.db"
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_USER_ID = os.environ["DISCORD_USER_ID"]

THUMBS_UP = "👍"
THUMBS_DOWN = "👎"


def get_pending_drafts(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, discord_channel_id, discord_message_id
        FROM drafts
        WHERE status = 'pending_approval'
    """)
    return cur.fetchall()


def user_reacted(channel_id: str, message_id: str, emoji: str) -> bool:
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    url = (f"https://discord.com/api/v10/channels/{channel_id}"
           f"/messages/{message_id}/reactions/{emoji}")
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        print(f"Warning: reaction lookup failed ({r.status_code}): {r.text}")
        return False
    reactors = r.json()  # list of user objects who reacted with this emoji
    return any(str(u["id"]) == str(DISCORD_USER_ID) for u in reactors)


def update_status(conn: sqlite3.Connection, draft_id: int, status: str) -> None:
    conn.execute(
        "UPDATE drafts SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, draft_id),
    )
    conn.commit()


def run() -> None:
    conn = sqlite3.connect(DB_PATH)
    pending = get_pending_drafts(conn)
    print(f"Checking {len(pending)} pending draft(s) for reactions.")

    for draft_id, channel_id, message_id in pending:
        if user_reacted(channel_id, message_id, THUMBS_UP):
            update_status(conn, draft_id, "approved")
            print(f"  draft {draft_id}: approved")
        elif user_reacted(channel_id, message_id, THUMBS_DOWN):
            update_status(conn, draft_id, "rejected")
            print(f"  draft {draft_id}: rejected")
        else:
            print(f"  draft {draft_id}: still waiting")

    conn.close()


if __name__ == "__main__":
    run()
