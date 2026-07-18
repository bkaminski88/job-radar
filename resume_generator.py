"""
Generates a tailored resume for a specific job posting by SELECTING AND
REORDERING bullets from a fixed master resume — never inventing new
phrasing. This mirrors a real editorial process: cut what doesn't fit,
keep what does, don't rewrite.

Also produces "framing notes" — a short explanation of what was emphasized,
what was cut, and how any gaps or access boundaries were handled. This gets
stored alongside the resume/cover letter so you can sanity-check the
tailoring logic at a glance before approving.

Source of truth for resume content: brian_kaminski_master_resume_v1_5_1.md
(or whatever MASTER_RESUME_PATH points to). Source of truth for tone/career
context: brian_kaminski_profile.md.
"""
import os
import anthropic

PROFILE_DOC_PATH = "brian_kaminski_profile.md"
MASTER_RESUME_PATH = "brian_kaminski_master_resume_v1_5_1.md"

RESUME_SYSTEM_PROMPT = """You are tailoring a resume for a specific job posting.
You will be given a MASTER RESUME (the only source of resume content) and a
JOB POSTING. Your job is editorial selection, not authorship.

HARD RULES — violating any of these is a failure:

1. SELECTION ONLY, NO REWRITING
   - Reorder and select bullets from the master resume for relevance to this
     posting. Do NOT rewrite bullets into new sentences or invent phrasing
     that isn't in the master resume.
   - Light grammar/flow edits are fine (e.g. fixing a dangling connector
     after removing a clause). Re-authoring a bullet's content is prohibited.
   - Maintain the same depth and specificity as the original bullets —
     don't compress a detailed bullet into a vaguer one.
   - Remove or de-emphasize bullets that don't align with this posting, but
     never add claims that aren't already in the master resume.

2. HONESTY GUARDRAILS
   - Where the master resume describes an access boundary (something the
     candidate was NOT permitted or able to do, e.g. lacking admin-level
     integration permissions), preserve that framing exactly — a boundary,
     not a skills gap. Never reword a stated limitation into an implied
     capability.
   - Never overclaim depth, authorship, or scope beyond the exact language
     already in the master resume.
   - Preserve prototype-vs-production labeling exactly as the master resume
     states it. Never upgrade a "prototype" or "proof of concept" into
     production-sounding language, or vice versa.
   - If a job requirement has no direct match in the master resume, either
     name the closest adjacent experience and explain the bridge, or state
     the gap plainly in the framing notes. Do not paper over it in the
     resume itself by stretching a bullet's meaning.
   - Never hedge in the resume or notes with phrases like "I hope that
     covers it" or similar filler.

3. FRAMING DECISIONS (pick the one that fits this posting, and say which
   in your framing notes)
   - Internal Enablement/Integration (default for enablement-titled roles):
     emphasize adoption, stakeholder translation, organizational impact.
   - Customer Enablement/Success (if the posting emphasizes this):
     highlight training delivery, translating for non-technical audiences,
     documented adoption outcomes.
   - Live Sales Engineering/Solutions Engineering (if the posting requires
     this): in your framing notes, name the two real gaps explicitly —
     (1) live, adaptive demos under sales pressure, (2) vertical domain
     depth. Do not overstate fit via the resume alone; the notes must be
     honest about this even if the resume emphasizes adjacent strengths.

4. OUTPUT FORMAT
   Output must contain exactly two sections, separated by these exact
   markers on their own lines:

   ===RESUME===
   (the tailored resume in Markdown, same overall structure as the master:
   header, Summary, Experience, Key Projects, Skills, Education — with
   bullets selected/reordered per the above rules)

   ===FRAMING_NOTES===
   (a short paragraph or bullet list: which framing decision was used and
   why, what was emphasized, what was cut and why, how any gaps or access
   boundaries were handled — e.g. "emphasized CoWork skills and adoption
   experience; avoided overstating the custom connector work since that's
   a boundary, not a gap")

   No other text outside these two sections.
"""


def load_profile_doc(path: str = PROFILE_DOC_PATH) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_master_resume(path: str = MASTER_RESUME_PATH) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_resume_response(raw_text: str) -> tuple[str, str]:
    """Splits the model's output into (resume_md, framing_notes)."""
    if "===RESUME===" in raw_text and "===FRAMING_NOTES===" in raw_text:
        resume_part = raw_text.split("===RESUME===", 1)[1]
        resume_md, framing_notes = resume_part.split("===FRAMING_NOTES===", 1)
        return resume_md.strip(), framing_notes.strip()

    # Fallback: markers missing — treat the whole thing as the resume and
    # flag it so this doesn't silently ship without framing notes.
    return raw_text.strip(), "[WARNING: model did not return framing notes in the expected format.]"


def generate_resume(job_title: str, company: str, job_description: str,
                     profile_doc: str | None = None,
                     master_resume: str | None = None) -> tuple[str, str]:
    """Returns (tailored_resume_md, framing_notes)."""
    if profile_doc is None:
        profile_doc = load_profile_doc()
    if master_resume is None:
        master_resume = load_master_resume()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_prompt = f"""CANDIDATE PROFILE DOCUMENT (career context, target roles, tone guidance):
{profile_doc}

---

MASTER RESUME (the ONLY source of resume content — select and reorder from this):
{master_resume}

---

JOB POSTING:
Title: {job_title}
Company: {company}
Description:
{job_description}

---

Produce the tailored resume and framing notes now, in the required format."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=3000,
        system=RESUME_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()
    return _parse_resume_response(raw_text)


if __name__ == "__main__":
    # quick manual test — replace with a real posting to dry-run
    resume_md, framing_notes = generate_resume(
        job_title="AI Automation Engineer",
        company="TestCo",
        job_description="We're looking for someone to build agentic workflows "
                         "connecting internal tools, with a focus on human-in-the-loop "
                         "review and no-code/low-code automation platforms. This role "
                         "is internal-facing, supporting our own ops and data teams.",
    )
    print("=== RESUME ===")
    print(resume_md)
    print("\n=== FRAMING NOTES ===")
    print(framing_notes)
