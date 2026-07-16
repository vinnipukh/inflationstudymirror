# Project: Inflation Study Dashboard Deployment

## What This Is

A brownfield Python project that turns scraped Turkish price/rent datasets into a deployable dashboard. The project already contains scrapers, generated raw CSVs, inflation calculators, and a first Streamlit dashboard. The new direction is to make the dashboard production-shaped by separating the frontend from the data/application backend.

The target architecture is a clean hexagonal split:

- **Streamlit frontend**: user-facing charts, tabs, filters, search/autocorrect, and deployment UI.
- **Falcon Python Web Framework API**: the only data source for the dashboard.
- **Domain/application layer**: price history, retailer averages, movers, coverage, parsing, and filtering use cases independent of Streamlit/Falcon.
- **Adapters**: CSV repository for existing `Datas/` files first; database/cache can be added later behind the same ports.

## Core Value

Users can explore scraped product prices quickly and reliably from a Streamlit dashboard whose data access is served through a Falcon API instead of direct frontend CSV scanning.

## Context

This is an existing repository, not a greenfield app. Current capabilities and constraints are documented in `.planning/codebase/`.

Important existing facts:

- Scrapers under `Codes/` write raw daily CSVs into `Datas/`.
- Inflation calculators under `Inflations/Codes/` write processed outputs into `Inflations/Datas/`.
- `streamlit_app.py` currently exists and reads CSVs directly from `Datas/`.
- `streamlit_app.py` already has four dashboard tabs and search/autocorrection helpers.
- The first dashboard version was slow because it loaded many CSVs before UI interaction; current code uses retailer/date/file caps.
- The new architecture must preserve those performance controls while moving data access behind Falcon.
- The user will manage dependency installation with `uv`; implementation should avoid surprise dependency churn unless explicitly requested.

## Requirements

### Validated

- ✓ Raw scraped data exists under `Datas/` — existing.
- ✓ Multiple retailer/domain scrapers exist under `Codes/` — existing.
- ✓ Inflation calculation scripts exist under `Inflations/Codes/` — existing.
- ✓ Generated inflation outputs exist under `Inflations/Datas/` — existing.
- ✓ A Streamlit dashboard entrypoint exists at `streamlit_app.py` — existing.
- ✓ Dashboard search/autocorrection helper behavior exists in `streamlit_app.py` — existing.
- ✓ Domain/application modules independent of Streamlit and Falcon exist under `inflation_dashboard/` — validated in Phase 1.
- ✓ CSV adapter preserves bounded retailer/date/max-files loading for existing `Datas/` files — validated in Phase 1.

### Active

- [ ] Build a Falcon Python Web Framework API that exposes dashboard data from existing CSV files.
- [ ] Refactor Streamlit frontend so all dashboard tabs read from Falcon endpoints, not directly from CSV files.
- [ ] Preserve four dashboard tabs: product price chart/cheapest date, retailer average chart, price movers, and coverage/overview.
- [ ] Preserve performance controls: retailer selection, date filters, max files per retailer, and cached/limited loading.
- [ ] Provide deploy/run documentation for running Falcon API and Streamlit frontend as separate processes.
- [ ] Add focused lightweight verification for domain logic and API-backed dashboard data calls.

### Out of Scope

- Rewriting all scraper scripts — this project focuses on dashboard deployment, not ingestion redesign.
- Replacing CSV storage with a database in v1 — the hexagonal ports should make that possible later, but CSV remains the first adapter.
- Changing the underlying inflation formulas unless needed for dashboard correctness.
- Full visual redesign of the dashboard beyond what is necessary to support API-backed data.
- Installing dependencies or launching long-running services for the user unless requested.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use Falcon for the API | User explicitly requested Falcon Python Web Framework. | Locked |
| Streamlit dashboard reads from Falcon API | Separates frontend from data access and avoids direct CSV scans in Streamlit. | Locked |
| Use hexagonal architecture | Keeps domain logic testable and allows future CSV/database/cache adapter swaps. | Locked |
| Coarse roadmap | User chose 3-5 larger phases. | Locked |
| Parallel execution when independent | User chose parallel plans for independent work. | Locked |
| Commit planning docs | User chose to track GSD planning docs in git. | Locked |
| Research, plan checks, verification, and drift guard enabled | User selected quality gates for future phases. | Locked |
| Model profile inherits current session | User selected current-session model behavior. | Locked |

## Success Criteria

- Streamlit can be run as a frontend that calls a configurable Falcon API base URL.
- Falcon exposes endpoints for retailers/inventory, product history, retailer averages, price movers, and coverage.
- Streamlit no longer imports or calls CSV loading functions directly for dashboard data.
- Shared/domain logic is importable and testable without starting Streamlit or Falcon.
- Default dashboard load is bounded and does not eagerly scan all raw CSV files from the frontend.
- User has clear `uv`-friendly run commands for API and frontend.

## Risks

- CSV schema drift across sources can break generalized API responses.
- Falcon dependency/server choice must be documented without forcing installs prematurely.
- Streamlit visual validation still requires the user to run the UI or approve screenshots.
- Large datasets can still be slow if API endpoints perform uncached full scans.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition**:
1. Requirements invalidated? → Move to Out of Scope with reason.
2. Requirements validated? → Move to Validated with phase reference.
3. New requirements emerged? → Add to Active.
4. Decisions to log? → Add to Key Decisions.
5. "What This Is" still accurate? → Update if drifted.

**After each milestone**:
1. Full review of all sections.
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state.

---
*Last updated: 2026-07-16 after Phase 1 completion*
