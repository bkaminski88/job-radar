# Job Radar

A scheduled automation that monitors company job boards (via their public ATS
APIs) for new AI/automation-related postings and alerts me on Discord —
no scraping, no manual checking.

This is a 3-stage personal project arc exploring AI/workflow automation, going
from plain workflow automation → LLM-based classification/scoring → a
tool-using agent with human-in-the-loop approval. All three stages are built;
see [Pipeline stages](#pipeline-stages) for what's automated vs. run by hand.

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

## Pipeline stages

| Stage | What it does | Automation |
|---|---|---|
| **1 — Fetch/filter/dedupe/notify** | Described above: `sources.py` → `prefilter.py` → `db.py` → `notify.py` | Runs daily via `job-check.yml` |
| **2 — LLM scoring** | `llm_classifier.py` sends each new posting to Claude for structured scoring (1–10, recommendation, reasoning, flags); `fit_pipeline.py` combines it with Stage 1's rule-based prefilter and decides whether to alert | Wired into `main.py`, so it also runs daily via `job-check.yml` |
| **3 — Agentic drafting** | `draft_pipeline.py` generates a tailored resume + cover letter for postings that score 7+, posts them to Discord with 👍/👎 reactions for approval; `check_approvals.py` polls for the reaction; `execute_approved.py` writes approved drafts to `outputs/` | Standalone scripts, run manually — not wired into any scheduled workflow |

Nothing is ever emailed, submitted, or sent to an employer automatically —
Stage 3 stops at "drafted and approved," the actual application is still a
human action.

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
3. Copy `.env.example` to `.env` and fill in your webhook URL, `ANTHROPIC_API_KEY`,
   and `SALARY_FLOOR`.
4. Edit `companies.json` to adjust which companies/keywords to track.
5. Edit `profile.json` to set your target titles, red flags, and avoid-list.
6. Run it:
   ```
   python main.py
   ```

### Why the salary floor is an env var

`profile.json` is committed, and your compensation floor is personal — so it is read
from `SALARY_FLOOR` instead, the same way API keys are. `load_profile()` overlays it
onto the loaded profile, so nothing downstream changes.

If `SALARY_FLOOR` is unset the key is simply absent and salary filtering is skipped —
no crash, no silent `$0` floor. Postings with no salary listed are never rejected on
this basis either way; only a posting whose highest posted figure falls below the
floor is cut. Accepts `115000`, `115,000` or `$115,000`.

### Personal documents (Stage 3 only)

Stage 3 drafting reads two documents that hold personal data — your career profile
and your master resume. Both are **gitignored and never committed**. Copy the
templates and fill them in:

```
cp profile.example.md profile.md
cp master_resume.example.md master_resume.md
```

`main.py` (the scheduled fetch/score/notify run) does not need these — it only reads
`profile.json`. Only the Stage 3 drafting scripts do.

Paths can be overridden with the `PROFILE_DOC_PATH` and `MASTER_RESUME_PATH`
environment variables.

### Deploying the scheduled version

1. Push this repo to GitHub.
2. In repo settings → *Secrets and variables → Actions*, add these secrets:

   | Secret | Needed for |
   |---|---|
   | `DISCORD_WEBHOOK_URL` | notifications |
   | `ANTHROPIC_API_KEY` | Stage 2 LLM scoring |
   | `SALARY_FLOOR` | salary filtering (optional — skipped if unset) |
   | `PROFILE_DOC` | Stage 3 drafting |
   | `MASTER_RESUME` | Stage 3 drafting |

3. The workflow in `.github/workflows/job-check.yml` runs daily at 13:00 UTC
   and can also be triggered manually from the Actions tab.

To run Stage 3 drafting in Actions, the personal documents have to reach the runner
without being in the repo. Add two more repository secrets — `PROFILE_DOC` and
`MASTER_RESUME` — pasting the full contents of `profile.md` and `master_resume.md` as
the values (Actions secrets accept multiline values). The *Materialize personal
documents* workflow step writes them to disk before the run, and skips silently if
they aren't set. Because both filenames are gitignored, the *Persist database* step
cannot commit them back by accident.

## Known limitations / honest caveats

- The company list in `companies.json` is a starting point — some board
  tokens may not match the actual slug a company uses on Greenhouse/Lever.
  The script logs a clear warning for any board that 404s rather than
  failing silently; check the Actions logs after your first run and fix
  any mismatched tokens.
- Stage 1's keyword filter is a simple case-insensitive substring check.
  That's intentional, not a placeholder — it's a cheap gate that runs before
  every posting reaches Stage 2's LLM call, not a substitute for it.
- This only covers companies using Greenhouse or Lever. Companies on other
  ATS platforms (or with fully custom career sites) aren't covered — adding
  another source (e.g. Ashby, which also has a public API) would be a
  natural extension.

## Stack

Python 3.12 · `requests` · SQLite · Anthropic Claude · GitHub Actions · Discord
webhooks (+ bot API for Stage 3 reaction polling)

## Known gap

`execute_approved.py` writes approved drafts to `outputs/` and git-commits
them — that commit step is currently a no-op, because `outputs/` is
gitignored (it previously held test fixtures with personal data that didn't
belong in a public repo). Real approved drafts need a storage location that
isn't "auto-committed into a public repository," which hasn't been decided
yet — this is a known, open gap, not a regression to work around silently.
