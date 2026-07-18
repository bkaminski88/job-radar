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

Queries seen_jobs.llm_score (populated by Stage 2's fit_pipeline.py) and
seen_jobs.description, joined against drafts.job_key.
"""
import os
import sqlite3
import requests
from dotenv import load_dotenv

from resume_generator import generate_resume, load_profile_doc, load_master_resume
from cover_letter_generator import generate_cover_letter

load_dotenv()

DB_PATH = "jobs.db"
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
FIT_SCORE_THRESHOLD = 7

THUMBS_UP = "👍"
THUMBS_DOWN = "👎"


def get_jobs_needing_drafts(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        SELECT sj.job_key, sj.title, sj.company, sj.description
        FROM seen_jobs sj
        LEFT JOIN drafts d ON d.job_key = sj.job_key
        WHERE sj.llm_score >= ?
          AND d.id IS NULL
    """, (FIT_SCORE_THRESHOLD,))
    return cur.fetchall()


def post_to_discord(job_title: str, company: str, resume_md: str,
                     cover_letter_md: str, framing_notes: str) -> tuple[str, str]:
    """Posts draft preview to Discord. Returns (message_id, channel_id)."""
    letter_preview = cover_letter_md[:400] + ("..." if len(cover_letter_md) > 400 else "")
    notes_preview = framing_notes[:300] + ("..." if len(framing_notes) > 300 else "")
    content = (
        f"**Draft ready for approval: {job_title} @ {company}**\n\n"
        f"React {THUMBS_UP} to approve, {THUMBS_DOWN} to reject.\n\n"
        f"**Framing notes:**\n```\n{notes_preview}\n```\n"
        f"**Cover letter preview:**\n```\n{letter_preview}\n```\n"
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
    import time
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    for emoji in (THUMBS_UP, THUMBS_DOWN):
        url = (f"https://discord.com/api/v10/channels/{channel_id}"
               f"/messages/{message_id}/reactions/{emoji}/@me")

        for attempt in range(3):
            r = requests.put(url, headers=headers, timeout=15)
            if r.status_code in (200, 204):
                break
            if r.status_code == 429:
                retry_after = r.json().get("retry_after", 0.5)
                time.sleep(retry_after + 0.1)
                continue
            print(f"Warning: failed to add reaction {emoji}: {r.status_code} {r.text}")
            break


def create_draft_row(conn: sqlite3.Connection, job_key: str) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO drafts (job_key, status) VALUES (?, 'pending_generation')",
        (job_key,),
    )
    conn.commit()
    return cur.lastrowid


def finalize_draft_row(conn: sqlite3.Connection, draft_id: int, resume_md: str,
                        cover_letter_md: str, framing_notes: str,
                        message_id: str, channel_id: str) -> None:
    cur = conn.cursor()
    cur.execute("""
        UPDATE drafts
        SET resume_md = ?, cover_letter_md = ?, framing_notes = ?,
            discord_message_id = ?, discord_channel_id = ?,
            status = 'pending_approval', updated_at = datetime('now')
        WHERE id = ?
    """, (resume_md, cover_letter_md, framing_notes, message_id, channel_id, draft_id))
    conn.commit()


def run() -> None:
    conn = sqlite3.connect(DB_PATH)
    profile_doc = load_profile_doc()  # load once, reuse across jobs this run
    master_resume = load_master_resume()

    jobs = get_jobs_needing_drafts(conn)
    print(f"Found {len(jobs)} job(s) needing drafts.")

    for job_key, title, company, description in jobs:
        print(f"Generating draft for: {title} @ {company}")
        draft_id = create_draft_row(conn, job_key)

        try:
            resume_md, framing_notes = generate_resume(
                title, company, description, profile_doc, master_resume
            )
            cover_letter_md = generate_cover_letter(
                title, company, description, resume_md, framing_notes, profile_doc
            )
            message_id, channel_id = post_to_discord(
                title, company, resume_md, cover_letter_md, framing_notes
            )
            add_reaction_options(channel_id, message_id)
            finalize_draft_row(
                conn, draft_id, resume_md, cover_letter_md, framing_notes,
                message_id, channel_id
            )
            print(f"  -> posted to Discord, message_id={message_id}")
        except Exception as e:
            print(f"  -> FAILED for job_key={job_key}: {e}")
            # leave draft row at 'pending_generation' so it's retried next run

    conn.close()


if __name__ == "__main__":
    run()
