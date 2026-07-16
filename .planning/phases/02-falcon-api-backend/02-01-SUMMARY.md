---
phase: 02-falcon-api-backend
plan: 02-01
subsystem: api
tags: [falcon, api, serialization, csv, pandas, filters]

requires:
  - phase: 01-hexagonal-core-extraction
    provides: framework-independent CSV adapter, domain price normalization, and dashboard use cases
provides:
  - Falcon API package with app factory and six locked endpoint routes
  - JSON-safe response envelopes for pandas/numpy/date payloads
  - Cached inventory discovery, query filter parsing, and bounded CSV history loading helpers
  - Happy-path Falcon resources for health, inventory, history, retailer averages, movers, and coverage
affects: [03-streamlit-api-frontend, 04-deployment-verification, api-client, smoke-verification]

tech-stack:
  added: [falcon]
  patterns:
    - Thin Falcon adapter under inflation_dashboard/api
    - Uniform {data, meta, errors} response envelope
    - Inventory-first and bounded load-second CSV access
    - stdlib lru_cache for API inventory discovery

key-files:
  created:
    - inflation_dashboard/api/__init__.py
    - inflation_dashboard/api/falcon_app.py
    - inflation_dashboard/api/serialization.py
    - inflation_dashboard/api/filters.py
    - inflation_dashboard/api/resources.py
  modified:
    - pyproject.toml
    - requirements.txt
    - .planning/STATE.md
    - .planning/ROADMAP.md

key-decisions:
  - "Declared Falcon in both pyproject.toml and requirements.txt because the repository has both metadata surfaces and the user manages installs with uv."
  - "Kept API code as a thin adapter over Phase 1 CSV/use-case functions; no Streamlit, Plotly, database, ORM, or cache-server work was added."
  - "Used Streamlit's existing last-60-days date default and default retailer fallback behavior without importing streamlit_app.py."

patterns-established:
  - "API resources catch ApiFilterError and return HTTP 400 envelopes with concise English messages."
  - "records_from_frame selects existing requested columns and converts every cell through JSON-safe scalar conversion."
  - "parse_common_filters resolves repeated retailer query params, default retailers, ISO dates, max_files, all_history, inventory counts, and warnings before loading history."

requirements-completed: [REQ-01, REQ-02, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-11]

coverage:
  - id: D1
    description: "Falcon dependency metadata declared with minimal manifest churn."
    requirement: "REQ-01"
    verification:
      - kind: other
        ref: "python dependency metadata assertion for pyproject.toml and requirements.txt"
        status: pass
    human_judgment: false
  - id: D2
    description: "API package and create_app() register /api/health, /api/inventory, /api/history, /api/retailer-averages, /api/movers, and /api/coverage."
    requirement: "REQ-01"
    verification:
      - kind: other
        ref: "source assertion over inflation_dashboard/api/falcon_app.py endpoint strings and forbidden imports"
        status: pass
    human_judgment: false
  - id: D3
    description: "JSON-safe envelope and DataFrame serialization helpers convert pandas/numpy/date values without NaN leakage."
    requirement: "REQ-10"
    verification:
      - kind: other
        ref: "python serialization snippet with pd.Timestamp, pd.NA, NaN, numpy scalars, and json.dumps(..., allow_nan=False)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Shared API filters parse repeated retailers, dates, max_files, all_history, defaults, cached inventory, and bounded history loading."
    requirement: "REQ-02"
    verification:
      - kind: other
        ref: "python filters behavior assertions for defaults, max_files=0, unknown retailer, reversed date range, and negative max_files"
        status: pass
    human_judgment: false
  - id: D5
    description: "Falcon resources expose happy-path health, inventory, history, retailer averages, movers, and coverage payloads through shared envelopes."
    requirement: "REQ-05"
    verification:
      - kind: other
        ref: "source assertions for resource classes, use-case calls, skipped_files, resp.media, forbidden imports, and lightweight HealthResource"
        status: pass
    human_judgment: false
  - id: D6
    description: "Runtime Falcon TestClient checks are ready but were not executed because Falcon is not installed in the active environment."
    requirement: "REQ-01"
    verification:
      - kind: other
        ref: "python import falcon check"
        status: fail
    human_judgment: true
    rationale: "The local environment is missing Falcon; dependency metadata is present for the user's uv install workflow, so 02-02 or the user can run runtime smoke checks after installation."

duration: 18 min
completed: 2026-07-16
status: complete
---

# Phase 02 Plan 02-01: Falcon API Backend Summary

**Thin Falcon API adapter with six locked routes, JSON-safe pandas serialization, cached inventory/filter helpers, and happy-path resources over the Phase 1 CSV/use-case layer.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-16T11:05:00Z
- **Completed:** 2026-07-16T11:20:36Z
- **Tasks:** 5 completed
- **Files modified:** 9 including planning metadata

## Accomplishments

- Added Falcon dependency metadata to both runtime manifests without broad dependency reconciliation.
- Created `inflation_dashboard/api/` with side-effect-free package marker and `create_app()` route registration for all six required endpoints.
- Added JSON-safe serialization helpers that normalize pandas timestamps, pd.NA, NaN, numpy scalars, mappings, lists, and DataFrame rows into stable envelope payloads.
- Added cached inventory discovery, repeated retailer parsing, date/max-file/all-history validation, default retailer/date behavior, and bounded history loading metadata.
- Added Falcon resource classes for health, inventory, history, retailer averages, movers, and coverage that reuse Phase 1 use cases and avoid Streamlit/Plotly/raw CSV parsing.

## Task Commits

Each task was committed atomically:

1. **Task 02-01-T1: Declare Falcon dependency with minimal manifest churn** - `e943fa5` (`chore`)
2. **Task 02-01-T2: Create API package, app factory, and route registration** - `1058416` (`feat`)
3. **Task 02-01-T3: Add JSON-safe envelope and DataFrame serialization helpers** - `b86815e` (`feat`)
4. **Task 02-01-T4: Add shared Falcon query parsing, defaults, cached inventory, and bounded loading helpers** - `c17f3b0` (`feat`)
5. **Task 02-01-T5: Add happy-path Falcon resources for health, inventory, history, averages, movers, and coverage** - `b856c94` (`feat`)

**Plan metadata:** committed in the docs/tracking commit that adds this summary.

## Files Created/Modified

- `pyproject.toml` - Added `falcon` to `[project].dependencies`.
- `requirements.txt` - Added plain `falcon` line without unrelated package churn.
- `inflation_dashboard/api/__init__.py` - Side-effect-free API package marker.
- `inflation_dashboard/api/falcon_app.py` - Falcon `create_app()` factory and locked route registration.
- `inflation_dashboard/api/serialization.py` - JSON-safe scalar, DataFrame, mapping, envelope, and error envelope helpers.
- `inflation_dashboard/api/filters.py` - Cached inventory, filter parsing/defaulting, validation errors, and bounded history load orchestration.
- `inflation_dashboard/api/resources.py` - Falcon resources for health, inventory, history, retailer averages, movers, and coverage.
- `.planning/STATE.md` - Updated current position/progress for completion of plan 02-01.
- `.planning/ROADMAP.md` - Marked 02-01 complete and Phase 2 in progress.

## Decisions Made

- Added Falcon to both manifests because this repository currently has both `pyproject.toml` and `requirements.txt` and dependency installation remains user-managed via `uv`.
- Chose Streamlit's current 60-day default date window and default retailer fallback behavior for API filters, copied into API helpers rather than importing Streamlit.
- Kept `/api/history` flexible: with `product_name` and either `product_retailer` or one selected retailer, it returns product history plus summary; without product selectors, it returns bounded normalized history records.
- Did not add database, ORM, schema migration, Redis, disk cache, or server process work.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.  
**Impact on plan:** No scope creep; implementation stayed within Falcon/API adapter and dependency metadata boundaries.

## Issues Encountered

- Falcon is not installed in the active local Python environment. Verification honestly reported `ModuleNotFoundError: No module named 'falcon'`. Dependency metadata is now present; runtime Falcon `TestClient` smoke checks should run after `uv` installs dependencies.
- `gsd-tools` could not parse the existing `STATE.md` current-plan text for automatic `state.advance-plan`, and `requirements.mark-complete` did not find checklist-style requirement IDs in the current requirements file. STATE/ROADMAP were updated manually; requirements completed are recorded in this summary frontmatter.

## Verification Results

- `python` dependency metadata assertions: PASS (`pyproject.toml` contains `"falcon"`; `requirements.txt` contains `falcon`).
- Falcon import check: BLOCKED/SKIPPED locally because Falcon is not installed.
- `falcon_app.py` source assertions: PASS (six endpoint strings, `def create_app(`, no Streamlit/Plotly/discovery/loading imports).
- `serialization.py` behavior assertions: PASS (`pd.Timestamp`, `pd.NA`, `NaN`, numpy scalars serialize through `json.dumps(..., allow_nan=False)`).
- `filters.py` source and behavior assertions: PASS (required imports/helpers/cache, repeated retailer parsing, default filters, uncapped warning, invalid filters).
- `resources.py` source assertions: PASS (six resource classes with `on_get`, expected use-case calls, skipped diagnostics, envelope assignment, no Streamlit/Plotly/raw CSV parsing, lightweight health handler).
- Plan-level AST/source/import-boundary/serialization checks: PASS.
- Falcon `TestClient` `/api/health` and `/api/inventory`: SKIPPED locally because Falcon is missing.

## Self-Check: PASSED

- All five plan tasks completed and committed atomically.
- All source-level acceptance criteria passed.
- Runtime Falcon smoke verification was not fabricated; missing dependency is documented as a blocker for local `TestClient` execution.
- API modules contain no Streamlit, Plotly, or raw `pd.read_csv` use.
- Domain/application/adapters remain Falcon-independent.
- Summary created with copied plan requirements and coverage metadata.

## User Setup Required

None - no external service configuration required. Install dependencies with the user's preferred `uv` workflow before runtime Falcon smoke checks.

## Next Phase Readiness

Ready for `02-02` to install/verify Falcon if available, run bounded `TestClient` smoke checks, and harden error/empty-state behavior.

---
*Phase: 02-falcon-api-backend*  
*Completed: 2026-07-16*
