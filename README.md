# Job Radar

A scheduled automation that monitors company job boards (via their public ATS
APIs) for new AI/automation-related postings and alerts me on Discord —
no scraping, no manual checking.

This is stage 1 of a 3-stage personal project arc exploring AI/workflow
automation, going from plain workflow automation (this repo) → LLM-based
classification/scoring → a tool-using agent with human-in-the-loop approval.

## The problem

Checking job boards manually is repetitive and easy to fall behind on.
Job aggregators exist, but scraping sites like LinkedIn directly violates
their Terms of Service and is brittle (selectors break constantly). Most
companies that use Greenhouse or Lever as their applicant tracking system,
however, expose a **public, unauthenticated JSON API** specifically meant
for displaying their job board elsewhere — so this project uses that
instead of scraping.

## How it works

```
[Greenhouse API] ─┐
                   ├─→ fetch jobs ─→ keyword filter ─→ dedupe vs SQLite ─→ Discord webhook
[Lever API]    ────┘
```

1. **Fetch**: pull every live job posting from a curated list of companies'
   Greenhouse and Lever boards (`companies.json`).
2. **Filter**: keep only postings whose title/description match
   automation/AI-adjacent keywords (broad discovery, not a fixed company
   list — see `companies.json`).
3. **Dedupe**: check each job against a SQLite database of previously-seen
   postings. Only brand-new job IDs are reported — updates to existing
   listings are intentionally ignored (a deliberate scope decision, not an
   oversight).
4. **Notify**: post new matches to a Discord channel via webhook.

Runs on a daily schedule via **GitHub Actions** — no server to host or pay
for. Since Actions runs are ephemeral (a fresh container every time), the
SQLite file is committed back to the repo after each run so "have I seen
this job before" state survives between runs.

## Design decisions worth calling out

- **APIs over scraping.** Greenhouse and Lever both publish official,
  documented, unauthenticated job board APIs. Using them instead of
  scraping a job aggregator avoids ToS violations and brittle HTML
  parsing — a more maintainable and more honest approach.
- **Failure isolation.** Each company fetch is wrapped individually — if
  one company's board 404s or times out, the script logs it and keeps
  going rather than crashing the whole run. A flaky source shouldn't take
  down monitoring for every other source.
- **State externalization on ephemeral compute.** GitHub Actions doesn't
  persist a filesystem between runs, so the dedupe database has to be
  explicitly written back to the repo. This is a small-scale version of a
  problem that shows up constantly in real serverless/scheduled automation.
- **Scoped dedupe semantics.** "New" means "new job ID," not "any change
  to a listing." That's a deliberate, documented choice — re-notifying on
  every description edit would be noisy, but it's worth being explicit
  about the tradeoff rather than leaving it implicit.

## Setup

1. Clone the repo and install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Create a Discord webhook: *Server Settings → Integrations → Webhooks →
   New Webhook*, then copy the URL.
3. Copy `.env.example` to `.env` and paste your webhook URL in.
4. Edit `companies.json` to adjust which companies/keywords to track.
5. Run it:
   ```
   python main.py
   ```

### Deploying the scheduled version

1. Push this repo to GitHub.
2. In repo settings → *Secrets and variables → Actions*, add a secret named
   `DISCORD_WEBHOOK_URL` with your webhook URL.
3. The workflow in `.github/workflows/job-check.yml` runs daily at 13:00 UTC
   and can also be triggered manually from the Actions tab.

## Known limitations / honest caveats

- The company list in `companies.json` is a starting point — some board
  tokens may not match the actual slug a company uses on Greenhouse/Lever.
  The script logs a clear warning for any board that 404s rather than
  failing silently; check the Actions logs after your first run and fix
  any mismatched tokens.
- Keyword matching is a simple case-insensitive substring check. It's
  intentionally crude — stage 2 of this project replaces it with an LLM
  classification step that reads the actual job description and extracts
  structured fields (seniority, tech stack, remote policy, fit score).
- This only covers companies using Greenhouse or Lever. Companies on other
  ATS platforms (or with fully custom career sites) aren't covered — adding
  another source (e.g. Ashby, which also has a public API) would be a
  natural extension.

## Stack

Python 3.12 · `requests` · SQLite · GitHub Actions · Discord webhooks

## What's next (stages 2–3)

- **Stage 2:** add an LLM step that reads each matching job description and
  extracts structured data (salary, seniority, stack, remote policy) and
  scores it against my own resume/criteria using structured output.
- **Stage 3:** an agentic layer that takes the next action on high-fit
  roles (e.g. drafting a tailored outreach note) with a human-approval
  step before anything is ever sent.
