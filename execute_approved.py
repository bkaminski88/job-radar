"""
Run this after check_approvals.py.

For every draft with status='approved', writes the resume and cover letter
to outputs/<company>_<job_id>/ as Markdown files and commits them to the
repo. This is the only "action" Stage 3 takes automatically — nothing is
emailed, submitted, or sent to any employer. That step is still on you.

Marks the draft 'completed' once written + committed.
"""
import os
import re
import json
import sqlite3
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "jobs.db"
OUTPUT_ROOT = "outputs"
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


def get_approved_drafts(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.job_id, d.resume_md, d.cover_letter_md,
               sj.title, sj.company
        FROM drafts d
        JOIN seen_jobs sj ON sj.id = d.job_id
        WHERE d.status = 'approved'
    """)
    return cur.fetchall()


def write_files(job_id: int, title: str, company: str,
                 resume_md: str, cover_letter_md: str) -> str:
    folder_name = f"{slugify(company)}_{job_id}"
    folder_path = os.path.join(OUTPUT_ROOT, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    with open(os.path.join(folder_path, "resume.md"), "w", encoding="utf-8") as f:
        f.write(resume_md)

    with open(os.path.join(folder_path, "cover_letter.md"), "w", encoding="utf-8") as f:
        f.write(cover_letter_md)

    resume_docx = convert_to_docx(os.path.join(folder_path, "resume.md"))
    cover_letter_docx = convert_to_docx(os.path.join(folder_path, "cover_letter.md"))

    return folder_path, resume_docx, cover_letter_docx


def convert_to_docx(md_path: str) -> str:
    """Converts a .md file to .docx alongside it via pandoc. Returns the docx path."""
    docx_path = md_path.rsplit(".", 1)[0] + ".docx"
    subprocess.run(["pandoc", md_path, "-o", docx_path], check=True)
    return docx_path


def post_files_to_discord(job_title: str, company: str,
                           resume_docx_path: str, cover_letter_docx_path: str) -> None:
    payload = {"content": f"✅ **Approved — files ready:** {job_title} @ {company}"}
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    with open(resume_docx_path, "rb") as rf, open(cover_letter_docx_path, "rb") as cf:
        files = {
            "files[0]": (os.path.basename(resume_docx_path), rf, docx_mime),
            "files[1]": (os.path.basename(cover_letter_docx_path), cf, docx_mime),
        }
        data = {"payload_json": json.dumps(payload)}
        resp = requests.post(DISCORD_WEBHOOK_URL, data=data, files=files, timeout=30)
        resp.raise_for_status()


def git_commit(paths: list[str], message: str) -> None:
    if not paths:
        return
    subprocess.run(["git", "add"] + paths, check=True)
    # allow-empty avoids failure if nothing actually changed
    subprocess.run(["git", "commit", "-m", message, "--allow-empty"], check=True)
    subprocess.run(["git", "push"], check=True)


def update_status(conn: sqlite3.Connection, draft_id: int) -> None:
    conn.execute(
        "UPDATE drafts SET status = 'completed', updated_at = datetime('now') WHERE id = ?",
        (draft_id,),
    )
    conn.commit()


def run() -> None:
    conn = sqlite3.connect(DB_PATH)
    approved = get_approved_drafts(conn)
    print(f"Found {len(approved)} approved draft(s) to write out.")

    written_paths = []
    for draft_id, job_id, resume_md, cover_letter_md, title, company in approved:
        folder_path, resume_docx, cover_letter_docx = write_files(
            job_id, title, company, resume_md, cover_letter_md
        )
        written_paths.append(folder_path)
        print(f"  wrote {folder_path}")

        try:
            post_files_to_discord(title, company, resume_docx, cover_letter_docx)
            print(f"  posted docx files to Discord")
        except Exception as e:
            # don't block the commit/DB update over a Discord hiccup —
            # files are already safely written and committed regardless
            print(f"  WARNING: failed to post files to Discord: {e}")

        update_status(conn, draft_id)

    if written_paths:
        git_commit(written_paths, "Add approved application drafts [automated]")

    conn.close()


if __name__ == "__main__":
    run()
