---
phase: 03-streamlit-api-frontend
plan: 03-01
subsystem: frontend
tags: [streamlit, falcon, api-client, filters, verification]

requires:
  - phase: 02-falcon-api-backend
    provides: Falcon endpoint contract with {data, meta, errors} envelopes
provides:
  - Strict Streamlit-to-Falcon frontend API client boundary
  - API-backed sidebar inventory/date/retailer filter setup without local CSV discovery
  - Shared DashboardFilters/common query parameter representation for 03-02 tab calls
  - Focused frontend boundary verifier runnable without a live Falcon server
affects: [03-streamlit-api-frontend, 04-deployment-verification, streamlit-dashboard, api-client]

tech-stack:
  added: []
  patterns:
    - Streamlit-free requests-based Falcon client with explicit short/data timeouts
    - st.cache_data API wrappers keyed by API base URL and endpoint/filter params
    - Repeated query parameter list-of-pairs serialization for retailer filters

key-files:
  created:
    - inflation_dashboard/frontend/__init__.py
    - inflation_dashboard/frontend/api_client.py
    - scripts/verify_streamlit_api_frontend.py
    - .planning/phases/03-streamlit-api-frontend/03-01-SUMMARY.md
  modified:
    - streamlit_app.py

key-decisions:
  - "Kept 03-01 scoped to the API client/sidebar/filter boundary; tab bodies now receive shared API filters and show 03-02 placeholders instead of performing local CSV/use-case loading."
  - "Used the existing requests dependency from requirements.txt for the frontend API client and did not modify dependency manifests."
  - "Backend Falcon smoke verification was run and still reports the existing missing-Falcon runtime blocker after source checks pass."

patterns-established:
  - "Frontend API calls validate exact {data, meta, errors} envelopes and raise ApiClientError for invalid JSON, non-2xx responses, missing keys, and non-empty errors."
  - "DashboardFilters plus build_common_params serializes repeated retailer params and all_history/max_files=0 semantics."
  - "Streamlit sidebar inventory and metadata are sourced from cached fetch_inventory(api_base_url), not local Datas/CSV scanning."

requirements-completed: [REQ-03, REQ-04, REQ-09, REQ-11]

coverage:
  - id: D1
    description: "Strict frontend Falcon client boundary with defaults, timeouts, envelope validation, repeated retailer params, and endpoint wrappers."
    requirement: "REQ-03"
    verification:
      - kind: other
        ref: "python scripts/verify_streamlit_api_frontend.py"
        status: pass
      - kind: other
        ref: "python -m py_compile streamlit_app.py inflation_dashboard/frontend/api_client.py scripts/verify_streamlit_api_frontend.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Streamlit sidebar exposes Falcon API base URL and derives retailer/date setup from /api/inventory without CSV adapter imports or local inventory wrappers."
    requirement: "REQ-03"
    verification:
      - kind: other
        ref: "python scripts/verify_streamlit_api_frontend.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Shared DashboardFilters/common params are constructed in Streamlit and threaded into all four tab renderer calls for 03-02 endpoint refactor."
    requirement: "REQ-11"
    verification:
      - kind: other
        ref: "python scripts/verify_streamlit_api_frontend.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Four tab labels and search/autocorrection helpers remain present."
    requirement: "REQ-04"
    verification:
      - kind: other
        ref: "python scripts/verify_streamlit_api_frontend.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Backend Falcon contract verifier was run as required; source checks pass but runtime smoke is blocked because Falcon is missing in the active Python environment."
    requirement: "REQ-11"
    verification:
      - kind: other
        ref: "python scripts/verify_falcon_api.py"
        status: fail
    human_judgment: true
    rationale: "The required command was run honestly and exited 1 with the existing missing-Falcon dependency message; no endpoint success was fabricated."

# Metrics
duration: 20 min
completed: 2026-07-17
status: complete_with_dependency_blocker
---

# Phase 03 Plan 03-01: Add API client layer and wire sidebar/filter flows to API calls Summary

**Streamlit now has a strict Falcon API boundary, API-backed sidebar inventory/filter setup, shared query filters, and focused verifier coverage without local CSV inventory fallback.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-17T07:18:00Z
- **Completed:** 2026-07-17T07:38:14Z
- **Tasks:** 5 completed
- **Files modified:** 5 including this summary

## Accomplishments

- Added `inflation_dashboard/frontend/api_client.py`, a Streamlit-free requests client with `ApiClientError`, `ApiEnvelope`, `DashboardFilters`, frontend defaults, short/data timeouts, exact envelope validation, repeated retailer params, and wrappers for all six Falcon endpoints.
- Reworked `streamlit_app.py` sidebar setup to expose `Falcon API base URL`, fetch `/api/inventory` through cached `fetch_inventory(api_base_url)`, derive retailer/date options from the API payload, preserve default retailers/last-60-day window/default max files 45/all-history semantics, and display API metadata/warnings.
- Removed Streamlit imports/calls for the CSV repository and direct application use cases; no local inventory/history fallback remains in the frontend.
- Threaded one `DashboardFilters` object and prepared common query params into all four tab renderer calls, leaving 03-02 to connect full endpoint payload rendering.
- Added `scripts/verify_streamlit_api_frontend.py`, which source-scans the Streamlit boundary and imports/tests client params, envelope validation, `ApiClientError`, and timeout behavior without a live Falcon server.

## Task Commits

Each implementation/verifier task was committed atomically where practical:

1. **Tasks 03-01-T1 through T5: API client, sidebar/filter integration, shared params, verifier, and verification run** - `30af06e` (`feat`)

**Plan metadata:** this summary is committed separately as the docs closeout commit.

## Files Created/Modified

- `inflation_dashboard/frontend/__init__.py` - Side-effect-free frontend package marker.
- `inflation_dashboard/frontend/api_client.py` - Strict Falcon HTTP client boundary and shared filter/query helpers.
- `streamlit_app.py` - API-backed sidebar inventory/filter flow and shared filters passed to tab renderers.
- `scripts/verify_streamlit_api_frontend.py` - Focused 03-01 source/client verifier.
- `.planning/phases/03-streamlit-api-frontend/03-01-SUMMARY.md` - This execution summary.

## Decisions Made

- Used `requests` because it is already declared in `requirements.txt`; no dependency manifests were modified.
- Kept 03-01 scoped to boundary/sidebar/filter work: tab renderers now receive `api_base_url` and `DashboardFilters` and show clear 03-02 placeholder info instead of using local history/use-case computations.
- Did not install Falcon or change `pyproject.toml`/`uv.lock`; the backend verifier's missing-Falcon runtime blocker is reported exactly.

## Deviations from Plan

None - plan executed within the intended 03-01 boundary.

**Total deviations:** 0 auto-fixed.  
**Impact on plan:** No scope creep into backend contracts, dependency manifests, notebooks, data files, or 03-02 tab payload rendering.

## Issues Encountered

- `python scripts/verify_falcon_api.py` exits non-zero because `falcon` is not installed in the active Python environment, matching the known Phase 2 blocker. Source checks pass before the blocker:

```text
PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource
PASS source contracts: endpoint routes and stable response keys
Falcon is missing. Install project dependency metadata with the user's uv workflow (for example: uv sync or uv pip install -r requirements.txt), then rerun python scripts/verify_falcon_api.py.
EXIT_CODE=1
```

## Verification Results

```text
$ python -m py_compile streamlit_app.py inflation_dashboard/frontend/api_client.py scripts/verify_streamlit_api_frontend.py; code=$?; echo EXIT_CODE=$code
EXIT_CODE=0
```

```text
$ python scripts/verify_streamlit_api_frontend.py; code=$?; echo EXIT_CODE=$code
PASS source: no application use-case imports remain in streamlit_app.py
PASS source: Streamlit sidebar/API boundary assertions
PASS source: frontend API client boundary assertions
PASS behavior: client params, envelope validation, ApiClientError, timeouts
PASS 03-01 Streamlit API frontend verifier
EXIT_CODE=0
```

```text
$ python scripts/verify_falcon_api.py; code=$?; echo EXIT_CODE=$code
PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource
PASS source contracts: endpoint routes and stable response keys
Falcon is missing. Install project dependency metadata with the user's uv workflow (for example: uv sync or uv pip install -r requirements.txt), then rerun python scripts/verify_falcon_api.py.
EXIT_CODE=1
```

## Self-Check: PASSED WITH DOCUMENTED DEPENDENCY BLOCKER

- All five 03-01 tasks were executed.
- Frontend compile and focused verifier passed.
- Backend verifier was run and its dependency blocker was reported without fabricating endpoint success.
- Final plan diff was limited to the intended frontend/client/verifier files plus this summary; pre-existing dirty/untracked user files were not staged.

## User Setup Required

None for this plan. To clear the existing backend runtime smoke blocker, install dependencies with the user's preferred `uv` workflow and rerun:

```bash
uv sync
# or: uv pip install -r requirements.txt
python scripts/verify_falcon_api.py
```

## Next Phase Readiness

Ready for Plan 03-02 to replace the four tab placeholders with calls to `/api/history`, `/api/retailer-averages`, `/api/movers`, and `/api/coverage` using the `api_base_url`, `DashboardFilters`, and common query params established here.

---
*Phase: 03-streamlit-api-frontend*  
*Completed: 2026-07-17*
