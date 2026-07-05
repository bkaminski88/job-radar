"""
prefilter.py — Stage A of job-radar's fit pipeline.

Cheap, rule-based filtering against profile.json BEFORE any LLM call.
Goal: cut a daily batch of (deduped, new) jobs down to a small shortlist
that's actually worth spending API tokens on.

This module is intentionally conservative: when a check is ambiguous
(e.g. salary not posted, hybrid policy unclear), it does NOT reject.
Stage B (the LLM) is better suited to nuanced judgment calls; Stage A's
job is just to kill obvious non-fits cheaply.

Usage:
    from prefilter import prefilter_job

    result = prefilter_job(job, profile)
    if result.passed:
        # send to Stage B (LLM)
    else:
        # log result.reasons, skip
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PrefilterResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)  # why rejected, or notes if passed


def load_profile(path: str | Path = "profile.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _contains_any(text: str, phrases: list[str]) -> list[str]:
    """Return the subset of phrases found in text (case-insensitive)."""
    text_lower = text.lower()
    return [p for p in phrases if p.lower() in text_lower]


def _extract_salary_numbers(text: str) -> list[int]:
    """
    Pull plausible annual salary figures out of free text.
    Looks for patterns like $120,000 / $120k / 120,000 - 150,000 / $120K-$150K.
    Returns a list of ints found (in dollars). Best-effort, not exhaustive.
    """
    numbers = []

    # $120,000 or $120000
    for m in re.finditer(r"\$\s?(\d{2,3}(?:,\d{3})|\d{5,6})\b", text):
        raw = m.group(1).replace(",", "")
        numbers.append(int(raw))

    # $120k or 120K
    for m in re.finditer(r"\$?\s?(\d{2,3})\s?[kK]\b", text):
        numbers.append(int(m.group(1)) * 1000)

    return numbers


def prefilter_job(job: dict, profile: dict) -> PrefilterResult:
    """
    job: dict expected to have at least:
        - "title": str
        - "description": str (full text, HTML stripped or not, either is fine)
        - "location": str (optional)
    profile: loaded from profile.json

    Returns PrefilterResult(passed=bool, reasons=[...])
    Rejection is OR'd across hard-fail checks. Multiple reasons can be
    logged even though only one is technically needed to reject -
    this makes the reject log more useful for tuning the filter later.
    """
    title = job.get("title", "") or ""
    description = job.get("description", "") or ""
    location = job.get("location", "") or ""
    full_text = f"{title}\n{location}\n{description}"

    reasons: list[str] = []
    hard_fail = False

    # --- 1. Remote check ---
    if profile.get("remote_required"):
        found_reject_phrases = _contains_any(full_text, profile.get("remote_reject_phrases", []))
        if found_reject_phrases:
            allow_areas = profile.get("remote_allow_if_hybrid_in_area", [])
            is_allowed_area = bool(_contains_any(full_text, allow_areas)) if allow_areas else False
            if not is_allowed_area:
                hard_fail = True
                reasons.append(f"Non-remote signal found: {found_reject_phrases}")
            else:
                reasons.append(
                    f"Hybrid/onsite language found ({found_reject_phrases}) but matches allowed area; not auto-rejected"
                )

    # --- 2. Title/keyword relevance ---
    target_title_hits = _contains_any(title, profile.get("target_titles", []))
    keyword_hits = _contains_any(full_text, profile.get("required_keywords_any", []))

    if not target_title_hits and not keyword_hits:
        hard_fail = True
        reasons.append("No target title or required keyword match in title/description")

    # --- 3. Avoid-title check (e.g. Director, VP, people-manager-heavy roles) ---
    avoid_hits = _contains_any(title, profile.get("avoid_title_keywords", []))
    if avoid_hits:
        hard_fail = True
        reasons.append(f"Title contains avoid-list term(s): {avoid_hits}")

    # --- 4. Red flag culture phrases ---
    red_flags = _contains_any(full_text, profile.get("red_flag_phrases", []))
    if red_flags:
        # Soft signal only - don't hard fail, but record it so it can influence
        # logging / be passed to the LLM as a flag. Multiple red flags could be
        # escalated to hard_fail if you want to tune this later.
        reasons.append(f"Red flag phrase(s) present (soft signal): {red_flags}")

    # --- 5. Salary floor (only if a number is actually posted) ---
    salary_floor = profile.get("salary_floor")
    if salary_floor:
        found_salaries = _extract_salary_numbers(full_text)
        if found_salaries:
            max_found = max(found_salaries)
            if max_found < salary_floor:
                hard_fail = True
                reasons.append(
                    f"Posted salary figure(s) {found_salaries} all below floor ${salary_floor:,}"
                )
        # else: no salary posted -> don't reject, note nothing (ambiguous case)

    passed = not hard_fail
    if passed and not reasons:
        reasons.append("Passed prefilter: matched target title/keywords, no hard-fail signals")

    return PrefilterResult(passed=passed, reasons=reasons)


if __name__ == "__main__":
    # Quick manual smoke test
    profile = load_profile(Path(__file__).parent / "profile.json")

    sample_jobs = [
        {
            "title": "AI Automation Engineer",
            "location": "Remote (US)",
            "description": "We're looking for a fast-paced builder to design agentic workflows using Claude and LLM tooling. $130,000 - $160,000.",
        },
        {
            "title": "VP of Engineering",
            "location": "New York, NY (onsite)",
            "description": "Lead our engineering org in office 5 days a week.",
        },
        {
            "title": "Senior AI Enablement Specialist",
            "location": "Remote",
            "description": "Help teams adopt AI tools and automation across the org. Salary not disclosed.",
        },
    ]

    for j in sample_jobs:
        result = prefilter_job(j, profile)
        print(f"\n[{j['title']}] passed={result.passed}")
        for r in result.reasons:
            print(f"  - {r}")
