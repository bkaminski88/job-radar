"""
Generates a cover letter based on the tailored resume + framing notes
produced by resume_generator.py, so the letter stays consistent with
whatever framing decision was made for this specific posting.
"""
import os
import anthropic

from resume_generator import load_profile_doc, load_master_resume, PROFILE_DOC_PATH

COVER_LETTER_SYSTEM_PROMPT = """You are writing a cover letter for a specific job posting.
You are given: the candidate's tailored resume for this posting, the framing
notes explaining what was emphasized and why, the candidate's profile
document (career context and additional tone guardrails), and the job
posting itself.

HARD RULES — violating any of these is a failure:

1. FORMAT
   - Maximum one page (roughly 350-450 words — err shorter, not longer).
   - No em dashes, no en dashes, no contractions (write "do not" not "don't",
     "I am" not "I'm").
   - Professional grammar throughout.

2. CONTENT
   - Lead with the core differentiator when it fits naturally, e.g. framing
     around building AI solutions AND driving real adoption of them —
     pull the actual differentiator from the profile doc / resume rather
     than inventing one.
   - Tailor the framing to match whatever framing decision is documented in
     the framing notes (internal enablement vs. customer-facing vs. sales
     engineering, etc.) — stay consistent with the resume, don't introduce
     a different angle.
   - Use specific evidence pulled from the tailored resume to support every
     claim. Do not introduce new facts, metrics, or claims that aren't in
     the resume or profile doc.
   - Never hedge with filler like "I hope this covers it" or similar.
   - Never claim a title the candidate did not formally hold.
   - Never say "the past several years" for AI experience — use accurate
     duration per the profile doc.
   - Be honest about any tool or experience gaps named in the framing notes
     rather than glossing over them — frame as familiarity with underlying
     patterns where that's true, or acknowledge the gap plainly where it
     isn't.
   - Never reproduce specific confidential employer metrics beyond what's
     already treated as usable/verified in the resume and profile doc.
   - Frame the reason for seeking a new role positively, per the profile
     doc's guidance (seeking an IC-focused role centered on building and
     teaching).

Output ONLY the cover letter text. No preamble, no commentary, no subject
line, no markdown headers.
"""


def generate_cover_letter(job_title: str, company: str, job_description: str,
                           tailored_resume_md: str, framing_notes: str,
                           profile_doc: str | None = None) -> str:
    if profile_doc is None:
        profile_doc = load_profile_doc(PROFILE_DOC_PATH)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_prompt = f"""CANDIDATE PROFILE DOCUMENT:
{profile_doc}

---

TAILORED RESUME FOR THIS POSTING:
{tailored_resume_md}

---

FRAMING NOTES (stay consistent with this framing decision):
{framing_notes}

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

    resume_md, framing_notes = generate_resume(
        job_title="AI Automation Engineer",
        company="TestCo",
        job_description="We're looking for someone to build agentic workflows "
                         "connecting internal tools, with a focus on human-in-the-loop "
                         "review and no-code/low-code automation platforms. This role "
                         "is internal-facing, supporting our own ops and data teams.",
    )
    letter = generate_cover_letter(
        job_title="AI Automation Engineer",
        company="TestCo",
        job_description="We're looking for someone to build agentic workflows "
                         "connecting internal tools, with a focus on human-in-the-loop "
                         "review and no-code/low-code automation platforms. This role "
                         "is internal-facing, supporting our own ops and data teams.",
        tailored_resume_md=resume_md,
        framing_notes=framing_notes,
    )
    print(letter)
