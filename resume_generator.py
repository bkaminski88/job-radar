"""
Generates a tailored resume (Markdown) for a job that scored 7+ in Stage 2.

Reads the candidate profile from profile_doc.md (your full profile doc,
not the Stage 2 profile.json) and the job's title/company/description,
then asks Claude to produce a tailored resume that:
  - only uses accomplishments/metrics actually present in the profile doc
  - never fabricates numbers, titles, or dates
  - reorders/emphasizes relevant experience for this specific posting

This does NOT send or save anywhere permanent — it returns Markdown text
for draft_pipeline.py to store in the `drafts` table pending approval.
"""
import os
import anthropic

PROFILE_DOC_PATH = "brian_kaminski_profile.md"

RESUME_SYSTEM_PROMPT = """You are helping tailor a resume for a specific job posting.

HARD RULES — violating any of these is a failure:
- Only use accomplishments, metrics, titles, and dates that appear in the
  candidate profile document provided. Never invent or round up numbers.
- Never claim a formal title the candidate did not hold. Check the profile
  doc's notes on this (e.g. "AI Enablement" was not a formal title).
- Do not say "past several years" of AI experience — the profile doc
  specifies the actual duration; use that.
- Keep formatting clean, ATS-friendly Markdown: contact line, summary,
  experience (reverse chronological), skills, education.
- Reorder and re-emphasize existing bullets to match the job posting's
  language and priorities. Do not add new claims to do this.
- If the posting wants a skill the candidate is only "currently learning,"
  it is fine to list it under skills, but do not claim proficiency beyond
  what the profile doc supports.

Output ONLY the resume in Markdown. No preamble, no commentary.
"""


def load_profile_doc(path: str = PROFILE_DOC_PATH) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def generate_resume(job_title: str, company: str, job_description: str,
                     profile_doc: str | None = None) -> str:
    """Returns tailored resume as a Markdown string."""
    if profile_doc is None:
        profile_doc = load_profile_doc()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_prompt = f"""CANDIDATE PROFILE DOCUMENT:
{profile_doc}

---

JOB POSTING:
Title: {job_title}
Company: {company}
Description:
{job_description}

---

Generate the tailored resume now."""

    response = client.messages.create(
        model="claude-sonnet-4-5",  # tailoring quality matters more than cost here
        max_tokens=2000,
        system=RESUME_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return response.content[0].text.strip()


if __name__ == "__main__":
    # quick manual test — replace with a real posting to dry-run
    test_resume = generate_resume(
        job_title="AI Automation Engineer",
        company="TestCo",
        job_description="We're looking for someone to build agentic workflows "
                         "connecting internal tools, with a focus on human-in-the-loop "
                         "review and no-code/low-code automation platforms.",
    )
    print(test_resume)
