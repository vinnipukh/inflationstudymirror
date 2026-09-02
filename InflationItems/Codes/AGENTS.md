# AGENTS.md

Project instructions for coding agents (pi, Claude Code, Codex, Cursor, etc.).

## Mandatory reading before touching scrapers

> **Any agent that will modify, refactor, or modernize anything under
> `InflationItems/Codes/` MUST first read the local scraping knowledge base:
> `docs/scraping-wiki/` (README.md + relevant entity/concept pages).**

This applies to every file under `InflationItems/Codes/` — scrapers, parsers, browser
drivers, anti-bot code, and related scripts. The wiki snapshot contains
hard-won, tested findings (mouse-movement emulation, cookie factory
patterns, CDP detection, hybrid scraping, driver risk assessments) that
directly govern the correctness of these scrapers.

Related references:

- `docs/TECH-STACK-SEARCH.md` — tech-stack search registry, skill registry, resource evaluations, and the
  modernization plan for `InflationItems/Codes/HousesRent/` (check before starting work).
- The wiki is a dated snapshot; if the work depends on current anti-bot
  behavior, refresh it from
  https://github.com/TheWebScrapingClub/scraping-wiki before relying on it.

## Repository shape

| Path | Role |
|---|---|
| `InflationItems/Codes/` | Source-specific scraper scripts that collect raw retailer/service data |
| `InflationItems/Datas/` | Tracked raw CSV data consumed by calculators, the dashboard, and the API |
| `Inflations/` | Inflation calculation scripts and TUIK-style category/weight configuration |
| `inflation_dashboard/` | Domain, adapters, application use cases, Falcon API, Streamlit frontend |
| `streamlit_app.py` | Dashboard frontend that reads data from the Falcon API |
| `scripts/` | Verification/smoke-test scripts (`verify_*.py`) |
| `docs/` | Project documentation (see docs/ for API, config, testing guides) |
| `docs/APPROACH.md` | **Recommended data-acquisition flow** — per-blocker anti-bot strategy, architecture, recon (§7), decision gates, milestones (start here before touching `InflationItems/Codes/`) |
| `docs/TECH-STACK-SEARCH.md` | Tech-stack + skill search registry — tool catalog, install set, integration blueprint, doc map |
| `docs/RESEARCH-PROMPT.md` | Deep-research agent prompt for validating the approach (gap hunt) |
| `docs/RESEARCH-REPORT-2026-08-16.md` | Deep-research validation report — corrections, B0 compliance gate, revised gates G0–G4 |

## Conventions

- Scraper data lands in `InflationItems/Datas/` — never commit scraped output that is
  transient or regenerable without checking the repo's gitignore policy.
- `docs/TECH-STACK-SEARCH.md` and `docs/scraping-wiki/` are living documents:
  add findings and resource evaluations there rather than scattering
  analysis in chat logs.
- When adding or changing scraper behavior, update the relevant docs
  (this file, TECH-STACK-SEARCH.md) so the next agent inherits the context.

## Testing principle

- **No unit tests or smoke tests for scrapers.** The way to test a scraper is
  to *use* it: bounded runs against the live site (`--limit`, `--start-url`
  scoped runs), scheduled/full runs, and the CSVs/checkpoints/logs they
  produce. Do not add unit tests, mocks, or synthetic HTML fixtures for
  scraper code under `InflationItems/Codes/` (`tests/test_houses_rent_scrapers.py` was
  removed 2026-09-02 for this reason). This also applies to scripts — verify
  scrapers by running them, not with one-off verify scripts where avoidable.
