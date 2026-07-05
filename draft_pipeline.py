"""
Stage 3 orchestrator. Run this after fit_pipeline.py (Stage 2).

For every job in `seen_jobs` that scored 7+ and does NOT yet have a row in
`drafts`, this:
  1. Generates a tailored resume + cover letter (Claude API)
  2. Posts a Discord message with a preview + the full drafts attached
  3. Adds 👍/👎 reactions to that message (via bot token) so approval is a
     single click for you
  4. Stores everything in `drafts` with status='pending_approval'

Nothing is sent to an employer or committed anywhere permanent at this stage.
Run `check_approvals.py` afterward (on a schedule) to pick up your reaction.

Adjust the SQL below to match your actual seen_jobs column names if they
differ (title, company, description, score are assumed here based on your
Stage 2 llm_classifier.py output).
"""
import os
import sqlite3
import requests

from resume_generator import generate_resume, load_profile_doc
from cover_letter_generator import generate_cover_letter

DB_PATH = "jobs.db"
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
FIT_SCORE_THRESHOLD = 7

THUMBS_UP = "👍"
THUMBS_DOWN = "👎"


def get_jobs_needing_drafts(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        SELECT sj.id, sj.title, sj.company, sj.description
        FROM seen_jobs sj
        LEFT JOIN drafts d ON d.job_id = sj.id
        WHERE sj.fit_score >= ?
          AND d.id IS NULL
    """, (FIT_SCORE_THRESHOLD,))
    return cur.fetchall()


def post_to_discord(job_title: str, company: str, resume_md: str,
                     cover_letter_md: str) -> tuple[str, str]:
    """Posts draft preview to Discord. Returns (message_id, channel_id)."""
    preview = cover_letter_md[:500] + ("..." if len(cover_letter_md) > 500 else "")
    content = (
        f"**Draft ready for approval: {job_title} @ {company}**\n\n"
        f"React {THUMBS_UP} to approve, {THUMBS_DOWN} to reject.\n\n"
        f"**Cover letter preview:**\n```\n{preview}\n```\n"
        f"_Full resume + cover letter stored in drafts table — "
        f"run check_approvals.py after reacting._"
    )

    resp = requests.post(
        f"{DISCORD_WEBHOOK_URL}?wait=true",
        json={"content": content},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["id"], data["channel_id"]


def add_reaction_options(channel_id: str, message_id: str) -> None:
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    for emoji in (THUMBS_UP, THUMBS_DOWN):
        url = (f"https://discord.com/api/v10/channels/{channel_id}"
               f"/messages/{message_id}/reactions/{emoji}/@me")
        r = requests.put(url, headers=headers, timeout=15)
        # 204 on success; don't hard-fail the whole pipeline over a reaction glitch
        if r.status_code not in (200, 204):
            print(f"Warning: failed to add reaction {emoji}: {r.status_code} {r.text}")


def create_draft_row(conn: sqlite3.Connection, job_id: int) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO drafts (job_id, status) VALUES (?, 'pending_generation')",
        (job_id,),
    )
    conn.commit()
    return cur.lastrowid


def finalize_draft_row(conn: sqlite3.Connection, draft_id: int, resume_md: str,
                        cover_letter_md: str, message_id: str, channel_id: str) -> None:
    cur = conn.cursor()
    cur.execute("""
        UPDATE drafts
        SET resume_md = ?, cover_letter_md = ?, discord_message_id = ?,
            discord_channel_id = ?, status = 'pending_approval',
            updated_at = datetime('now')
        WHERE id = ?
    """, (resume_md, cover_letter_md, message_id, channel_id, draft_id))
    conn.commit()


def run() -> None:
    conn = sqlite3.connect(DB_PATH)
    profile_doc = load_profile_doc()  # load once, reuse across jobs this run

    jobs = get_jobs_needing_drafts(conn)
    print(f"Found {len(jobs)} job(s) needing drafts.")

    for job_id, title, company, description in jobs:
        print(f"Generating draft for: {title} @ {company}")
        draft_id = create_draft_row(conn, job_id)

        try:
            resume_md = generate_resume(title, company, description, profile_doc)
            cover_letter_md = generate_cover_letter(
                title, company, description, resume_md, profile_doc
            )
            message_id, channel_id = post_to_discord(
                title, company, resume_md, cover_letter_md
            )
            add_reaction_options(channel_id, message_id)
            finalize_draft_row(
                conn, draft_id, resume_md, cover_letter_md, message_id, channel_id
            )
            print(f"  -> posted to Discord, message_id={message_id}")
        except Exception as e:
            print(f"  -> FAILED for job_id={job_id}: {e}")
            # leave draft row at 'pending_generation' so it's retried next run

    conn.close()


if __name__ == "__main__":
    run()
