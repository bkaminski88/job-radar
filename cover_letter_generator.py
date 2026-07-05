"""
Generates a cover letter (Markdown/plain text) based on the tailored resume
produced by resume_generator.py, plus the full profile doc for tone/guideline
rules that don't live in the resume itself (word count, phrases to avoid, etc).

Takes the RESUME as primary input (not just the raw profile) so the letter
stays consistent with whatever was emphasized/reordered for this job.
"""
import os
import anthropic

from resume_generator import load_profile_doc, PROFILE_DOC_PATH

COVER_LETTER_SYSTEM_PROMPT = """You are writing a cover letter for a specific job posting.
You are given the candidate's tailored resume for this exact posting, plus their
full profile document which contains hard tone/content rules. Follow the profile
doc's "Cover Letter Guidelines" section exactly — those rules override any
default instinct you have about cover letter writing.

HARD RULES:
- Under 400 words. Count matters — do not exceed it.
- Confident but not arrogant. No bold closing gimmicks ("only X people applied").
- Be honest about tool/skill gaps rather than glossing over them — frame as
  "newer to X specifically but familiar with the underlying patterns."
- Never claim a title the candidate did not formally hold.
- Never reproduce specific confidential company metrics from the profile doc's
  employer-specific context (numbers tied to the current employer) — it's fine
  to reference accomplishments in general terms if the profile doc itself
  already treats them as usable, verified metrics, but do not invent new ones
  or add employer-confidential specifics beyond what's already in the resume.
- Base every claim on what's in the tailored resume provided — do not pull
  in resume content that was deliberately left out for this posting.
- Frame the reason for leaving positively, per the profile doc's guidance.

Output ONLY the cover letter text. No preamble, no commentary, no subject line.
"""


def generate_cover_letter(job_title: str, company: str, job_description: str,
                           tailored_resume_md: str,
                           profile_doc: str | None = None) -> str:
    if profile_doc is None:
        profile_doc = load_profile_doc(PROFILE_DOC_PATH)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_prompt = f"""CANDIDATE PROFILE DOCUMENT (contains cover letter guidelines):
{profile_doc}

---

TAILORED RESUME FOR THIS POSTING (base the letter on this, not the full profile):
{tailored_resume_md}

---

JOB POSTING:
Title: {job_title}
Company: {company}
Description:
{job_description}

---

Write the cover letter now."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1200,
        system=COVER_LETTER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return response.content[0].text.strip()


if __name__ == "__main__":
    from resume_generator import generate_resume

    resume = generate_resume(
        job_title="AI Automation Engineer",
        company="TestCo",
        job_description="We're looking for someone to build agentic workflows "
                         "connecting internal tools, with a focus on human-in-the-loop "
                         "review and no-code/low-code automation platforms.",
    )
    letter = generate_cover_letter(
        job_title="AI Automation Engineer",
        company="TestCo",
        job_description="We're looking for someone to build agentic workflows "
                         "connecting internal tools, with a focus on human-in-the-loop "
                         "review and no-code/low-code automation platforms.",
        tailored_resume_md=resume,
    )
    print(letter)
