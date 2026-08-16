# AGENTS.md

Project instructions for coding agents (pi, Claude Code, Codex, Cursor, etc.).

## Mandatory reading before touching scrapers

> **Any agent that will modify, refactor, or modernize anything under
> `Codes/` MUST first read the local scraping knowledge base:
> `docs/scraping-wiki/` (README.md + relevant entity/concept pages).**

This applies to every file under `Codes/` — scrapers, parsers, browser
drivers, anti-bot code, and related scripts. The wiki snapshot contains
hard-won, tested findings (mouse-movement emulation, cookie factory
patterns, CDP detection, hybrid scraping, driver risk assessments) that
directly govern the correctness of these scrapers.

Related references:

- `docs/TECH-STACK-SEARCH.md` — tech-stack search registry, skill registry, resource evaluations, and the
  modernization plan for `Codes/HousesRent/` (check before starting work).
- The wiki is a dated snapshot; if the work depends on current anti-bot
  behavior, refresh it from
  https://github.com/TheWebScrapingClub/scraping-wiki before relying on it.

## Repository shape

| Path | Role |
|---|---|
| `Codes/` | Source-specific scraper scripts that collect raw retailer/service data |
| `Datas/` | Tracked raw CSV data consumed by calculators, the dashboard, and the API |
| `Inflations/` | Inflation calculation scripts and TUIK-style category/weight configuration |
| `inflation_dashboard/` | Domain, adapters, application use cases, Falcon API, Streamlit frontend |
| `streamlit_app.py` | Dashboard frontend that reads data from the Falcon API |
| `scripts/` | Verification/smoke-test scripts (`verify_*.py`) |
| `docs/` | Project documentation (see docs/ for API, config, testing guides) |
| `docs/APPROACH.md` | **Recommended data-acquisition flow** — per-blocker anti-bot strategy, architecture, recon (§7), decision gates, milestones (start here before touching `Codes/`) |
| `docs/TECH-STACK-SEARCH.md` | Tech-stack + skill search registry — tool catalog, install set, integration blueprint, doc map |
| `docs/RESEARCH-PROMPT.md` | Deep-research agent prompt for validating the approach (gap hunt) |
| `docs/RESEARCH-REPORT-2026-08-16.md` | Deep-research validation report — corrections, B0 compliance gate, revised gates G0–G4 |

## Conventions

- Scraper data lands in `Datas/` — never commit scraped output that is
  transient or regenerable without checking the repo's gitignore policy.
- `docs/TECH-STACK-SEARCH.md` and `docs/scraping-wiki/` are living documents:
  add findings and resource evaluations there rather than scattering
  analysis in chat logs.
- When adding or changing scraper behavior, update the relevant docs
  (this file, TECH-STACK-SEARCH.md) so the next agent inherits the context.
