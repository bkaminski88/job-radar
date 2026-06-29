"""
sources.py — fetches job postings from public ATS APIs (no auth required).

Greenhouse: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
Lever:      https://api.lever.co/v0/postings/{token}?mode=json

Both are publicly documented, unauthenticated endpoints meant for exactly
this use case (powering external job boards), which is why we use them
instead of scraping a site like LinkedIn or Indeed.

Every fetch function returns a list of "normalized" job dicts with this shape:
{
    "job_key":  str,   # globally unique id we use for dedup: "{source}:{company}:{id}"
    "source":   str,   # "greenhouse" | "lever"
    "company":  str,   # board token, e.g. "anthropic"
    "title":    str,
    "location": str,
    "url":      str,
    "description": str,  # plain-ish text, may contain HTML
}
"""

import requests

GREENHOUSE_BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
LEVER_BASE = "https://api.lever.co/v0/postings/{token}"

REQUEST_TIMEOUT = 15  # seconds — fail fast rather than hang a scheduled run


def fetch_greenhouse_jobs(company_token: str) -> list[dict]:
    """Fetch all live jobs for one company's Greenhouse board."""
    url = GREENHOUSE_BASE.format(token=company_token)
    try:
        resp = requests.get(
            url, params={"content": "true"}, timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 404:
            print(f"  [greenhouse] '{company_token}' not found (404) — check the board token")
            return []
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [greenhouse] failed to fetch '{company_token}': {e}")
        return []

    data = resp.json()
    jobs = []
    for raw in data.get("jobs", []):
        job_id = raw.get("id")
        if job_id is None:
            continue  # skip malformed entries rather than crash the whole run
        jobs.append({
            "job_key": f"greenhouse:{company_token}:{job_id}",
            "source": "greenhouse",
            "company": company_token,
            "title": raw.get("title", "Untitled role"),
            "location": (raw.get("location") or {}).get("name", ""),
            "url": raw.get("absolute_url", ""),
            "description": raw.get("content", ""),
        })
    return jobs


def fetch_lever_jobs(company_token: str) -> list[dict]:
    """Fetch all live jobs for one company's Lever board."""
    url = LEVER_BASE.format(token=company_token)
    try:
        resp = requests.get(url, params={"mode": "json"}, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            print(f"  [lever] '{company_token}' not found (404) — check the company token")
            return []
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [lever] failed to fetch '{company_token}': {e}")
        return []

    data = resp.json()
    jobs = []
    # Lever returns a bare JSON list, not a wrapper object
    for raw in data if isinstance(data, list) else []:
        job_id = raw.get("id")
        if job_id is None:
            continue
        categories = raw.get("categories", {}) or {}
        jobs.append({
            "job_key": f"lever:{company_token}:{job_id}",
            "source": "lever",
            "company": company_token,
            "title": raw.get("text", "Untitled role"),
            "location": categories.get("location", ""),
            "url": raw.get("hostedUrl", ""),
            "description": raw.get("descriptionPlain") or raw.get("description", ""),
        })
    return jobs


def matches_keywords(job: dict, keywords: list[str]) -> bool:
    """
    Broad-discovery filter: does this job's title or description mention
    any of our target keywords? Case-insensitive substring match — simple
    on purpose, since stage 1 is about plumbing, not precision. We'll
    tighten this with an LLM classification step in stage 2.
    """
    haystack = f"{job['title']} {job.get('description', '')}".lower()
    return any(kw.lower() in haystack for kw in keywords)


def fetch_all_jobs(companies: dict) -> list[dict]:
    """
    Fetch jobs from every configured Greenhouse and Lever company,
    then filter down to ones matching our keyword list.
    companies: the parsed companies.json dict.
    """
    all_jobs = []

    print(f"Fetching from {len(companies.get('greenhouse', []))} Greenhouse boards...")
    for token in companies.get("greenhouse", []):
        jobs = fetch_greenhouse_jobs(token)
        print(f"  [greenhouse] {token}: {len(jobs)} jobs")
        all_jobs.extend(jobs)

    print(f"Fetching from {len(companies.get('lever', []))} Lever boards...")
    for token in companies.get("lever", []):
        jobs = fetch_lever_jobs(token)
        print(f"  [lever] {token}: {len(jobs)} jobs")
        all_jobs.extend(jobs)

    keywords = companies.get("keywords", [])
    if keywords:
        filtered = [j for j in all_jobs if matches_keywords(j, keywords)]
        print(f"Keyword filter: {len(all_jobs)} total -> {len(filtered)} matching")
        return filtered

    return all_jobs
