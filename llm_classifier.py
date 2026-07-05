"""
llm_classifier.py — Stage B of job-radar's fit pipeline.

Calls the Anthropic API (Claude Haiku by default — cheap, fast, good
enough for a classification task like this) to score job fit against
Brian's candidate profile, ONLY for jobs that survived prefilter.py.

Requires:
    pip install anthropic --break-system-packages   (or in your venv)
    ANTHROPIC_API_KEY set in environment (.env, GitHub Actions secret, etc.)

Usage:
    from llm_classifier import score_job_fit

    verdict = score_job_fit(job, profile)
    # verdict.score (1-10), verdict.recommendation, verdict.reasoning, verdict.flags
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"  # cheap/fast - fine for classification
MAX_TOKENS = 600

SYSTEM_PROMPT = """You are a job-fit classifier helping a candidate triage job postings.
You will be given a condensed candidate profile and a single job posting.
Score how well the job fits the candidate's stated targets and constraints.

Respond ONLY with valid JSON, no markdown fences, no preamble. Schema:
{
  "score": <integer 1-10, 10 = excellent fit>,
  "recommendation": "<one of: strong_match, worth_a_look, marginal, poor_fit>",
  "reasoning": "<2-3 sentences, specific to this job and this candidate>",
  "flags": ["<short flag strings, e.g. 'salary below floor', 'hybrid required', 'IC-focused - good sign'>"]
}

Score generously for roles matching the candidate's target titles, IC-focused
AI/automation/enablement work, and remote-first culture. Score down for
heavy people-management scope, unclear remote policy combined with a
non-Atlanta location, salary clearly below the floor, or red-flag culture
language. If information is missing (e.g. salary not posted), do not
penalize heavily - just note it as a flag."""


@dataclass
class FitVerdict:
    score: int
    recommendation: str
    reasoning: str
    flags: list[str] = field(default_factory=list)
    raw_error: str | None = None  # populated if parsing/API failed


def _condensed_profile_text(profile: dict) -> str:
    """Build a compact text block from profile.json for the prompt."""
    return (
        f"Target titles: {', '.join(profile.get('target_titles', []))}\n"
        f"Must be remote: {profile.get('remote_required')}\n"
        f"Salary floor: ${profile.get('salary_floor', 0):,}\n"
        f"Avoid titles containing: {', '.join(profile.get('avoid_title_keywords', []))}\n"
        f"Red flag culture phrases to watch for: {', '.join(profile.get('red_flag_phrases', []))}\n"
        "Candidate background: builder and teacher; ~2 years hands-on AI enablement, "
        "agentic systems, and workflow automation experience (Claude/CoWork power user, "
        "built 20+ production AI skills, designed AI enablement curricula for execs). "
        "Seeking IC-focused roles, not people-management-heavy roles."
    )


def score_job_fit(job: dict, profile: dict, client: Anthropic | None = None) -> FitVerdict:
    """
    job: dict with at least "title", "description", "location", "company" (optional)
    profile: loaded from profile.json
    client: optional pre-built Anthropic client (so callers can reuse one
            client across many calls instead of constructing it each time)
    """
    if client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return FitVerdict(
                score=0,
                recommendation="error",
                reasoning="ANTHROPIC_API_KEY not set in environment",
                raw_error="missing_api_key",
            )
        client = Anthropic(api_key=api_key)

    user_prompt = (
        f"CANDIDATE PROFILE:\n{_condensed_profile_text(profile)}\n\n"
        f"JOB POSTING:\n"
        f"Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', 'unknown')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Description:\n{job.get('description', '')[:6000]}\n"
        "(description may be truncated)\n\n"
        "Score this job's fit per the schema in your instructions."
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        return FitVerdict(
            score=0,
            recommendation="error",
            reasoning=f"API call failed: {e}",
            raw_error=str(e),
        )

    # Extract text content from the response
    text_blocks = [block.text for block in response.content if block.type == "text"]
    raw_text = "\n".join(text_blocks).strip()

    # Defensive cleanup in case the model wraps in markdown fences anyway
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(cleaned)
        return FitVerdict(
            score=int(data.get("score", 0)),
            recommendation=data.get("recommendation", "unknown"),
            reasoning=data.get("reasoning", ""),
            flags=data.get("flags", []),
        )
    except (json.JSONDecodeError, ValueError) as e:
        return FitVerdict(
            score=0,
            recommendation="error",
            reasoning="Failed to parse LLM response as JSON",
            raw_error=f"{e}; raw_text={raw_text[:300]}",
        )


if __name__ == "__main__":
    # Quick manual smoke test - requires ANTHROPIC_API_KEY in env
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from prefilter import load_profile

    profile = load_profile(Path(__file__).parent / "profile.json")

    sample_job = {
        "title": "AI Automation Engineer",
        "company": "ExampleCo",
        "location": "Remote (US)",
        "description": (
            "We're hiring an IC-focused AI Automation Engineer to build agentic "
            "workflows using Claude and LangChain. You'll design and ship internal "
            "AI tooling that helps teams adopt automation. Fully remote, flexible hours. "
            "$130,000 - $160,000."
        ),
    }

    verdict = score_job_fit(sample_job, profile)
    print(json.dumps(verdict.__dict__, indent=2))
