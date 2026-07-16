---
phase: 02-falcon-api-backend
plan: 02-02
subsystem: api
tags: [falcon, api, smoke-verification, filters, json, boundaries]

requires:
  - phase: 02-falcon-api-backend
    provides: Falcon API app/resources, JSON envelopes, and dependency metadata from 02-01
provides:
  - Hardened invalid-filter validation with HTTP 400 error envelopes
  - Stable HTTP 200 empty-state payloads for history, averages, movers, and coverage endpoints
  - Bounded Falcon TestClient smoke verification script with missing-Falcon blocker handling
  - Source boundary checks for API/core imports, response contracts, JSON-native payloads, and lightweight health behavior
affects: [03-streamlit-api-frontend, 04-deployment-verification, api-client, smoke-verification]

tech-stack:
  added: []
  patterns:
    - In-process Falcon TestClient smoke verification without persistent server
    - Source-first boundary checks that run before Falcon dependency import
    - Empty-state response aliases for stable frontend consumption

key-files:
  created:
    - scripts/verify_falcon_api.py
    - .planning/phases/02-falcon-api-backend/02-02-SUMMARY.md
  modified:
    - inflation_dashboard/api/filters.py
    - inflation_dashboard/api/resources.py
    - .planning/STATE.md
    - .planning/ROADMAP.md

key-decisions:
  - "Runtime Falcon endpoint requests remain blocked in the active environment because Falcon is declared but not installed; the verifier exits non-zero with a uv-friendly install message rather than fabricating success."
  - "Boundary/source contract checks run before importing Falcon so missing dependencies do not hide import-boundary regressions."
  - "Retailer averages now expose both records and retailer_averages keys to provide a stable generic list key while preserving the earlier endpoint-specific key."

patterns-established:
  - "scripts/verify_falcon_api.py first scans import boundaries and source contracts, then uses falcon.testing.TestClient(create_app()) when Falcon is installed."
  - "Mover limit parsing accepts limit or mover_count and enforces the planned 5..30 range."
  - "All skipped-file/no-usable-row empty states preserve HTTP 200 and add metadata warnings."

requirements-completed: [REQ-01, REQ-02, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-11]

coverage:
  - id: D1
    description: "Invalid filter inputs return HTTP 400 envelopes with short invalid_filter errors."
    requirement: "REQ-02"
    verification:
      - kind: other
        ref: "python source assertions for unknown retailer, bad/reversed dates, max_files, aggregation, mover limit, all_history, and error_envelope handling"
        status: pass
    human_judgment: false
  - id: D2
    description: "Valid no-data and skipped-file cases keep HTTP 200 stable empty payload shapes and useful metadata."
    requirement: "REQ-05"
    verification:
      - kind: other
        ref: "python source assertions over resources.py/filter.py empty history, product summary, averages records, movers lists, coverage diagnostics, history_row_count, skipped_file_count"
        status: pass
    human_judgment: false
  - id: D3
    description: "Reusable smoke script covers all six endpoints, invalid-filter 400, envelope keys, strict JSON-native payloads, and missing-Falcon blocker behavior."
    requirement: "REQ-01"
    verification:
      - kind: other
        ref: "python scripts/verify_falcon_api.py (exit 1 locally after boundary/source checks because Falcon is missing)"
        status: fail
    human_judgment: true
    rationale: "The script is committed and correctly reports the missing Falcon dependency; endpoint TestClient requests require installing dependencies with the user's uv workflow."
  - id: D4
    description: "Import-boundary verification rejects Streamlit/Plotly in API modules and Falcon/Streamlit/Plotly in domain/application/CSV adapter modules."
    requirement: "REQ-10"
    verification:
      - kind: other
        ref: "python scripts/verify_falcon_api.py boundary/source phase output: PASS boundary checks; PASS source contracts"
        status: pass
    human_judgment: false
  - id: D5
    description: "Final verification uses no persistent server, keeps bounded max_files=1 smoke requests, and leaves streamlit_app.py untouched."
    requirement: "REQ-11"
    verification:
      - kind: other
        ref: "python scripts/verify_falcon_api.py source plus git status -- streamlit_app.py"
        status: pass
    human_judgment: false

# Metrics
duration: 15 min
completed: 2026-07-16
status: complete_with_dependency_blocker
---

# Phase 02 Plan 02-02: Add API smoke verification and error/empty-state handling Summary

**Bounded Falcon API smoke verifier plus hardened invalid-filter, empty-state, skipped-diagnostic, JSON-native, and import-boundary checks for the six API endpoints.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-16T11:20:36Z
- **Completed:** 2026-07-16T11:35:01Z
- **Tasks:** 5 completed
- **Files modified:** 6 including planning metadata

## Accomplishments

- Enforced planned invalid-filter handling for mover limits (`limit`/`mover_count` must be 5..30) while preserving existing unknown-retailer, date, max-file, all-history, aggregation, and category-limit validation branches.
- Stabilized empty-state payloads and diagnostics: product history summaries keep all four summary keys, retailer averages expose a `records` list, movers keep `biggest_drops`/`biggest_gains`, and skipped-file/no-usable-row cases add metadata warnings.
- Added `scripts/verify_falcon_api.py`, a reusable ad-hoc smoke verifier using `falcon.testing.TestClient(create_app())` when Falcon is installed and a clear non-zero missing-Falcon blocker when it is not.
- Extended the smoke verifier with source boundary checks for forbidden imports, lightweight `HealthResource`, route registration, response-contract keys, strict envelope keys, `json.dumps(..., allow_nan=False)`, and JSON-native scalar validation.
- Ran final bounded verification without launching a server and confirmed `streamlit_app.py` was not modified.

## Task Commits

Each task was committed atomically:

1. **Task 02-02-T1: Complete invalid-filter validation and HTTP 400 envelope handling** - `9ca8116` (`fix`)
2. **Task 02-02-T2: Stabilize valid empty-state payloads and skipped diagnostics** - `45edb30` (`fix`)
3. **Task 02-02-T3: Add reusable Falcon TestClient smoke verification script** - `f6ee6b4` (`test`)
4. **Task 02-02-T4: Add import-boundary and response-contract assertions to smoke verification** - `be8fc3a` (`test`)
5. **Task 02-02-T5: Run final bounded API smoke verification and document blockers precisely** - `87b1b0d` (`test`, empty verification-record commit)

**Plan metadata:** committed in the docs/tracking commit that adds this summary.

## Files Created/Modified

- `scripts/verify_falcon_api.py` - Reusable Falcon TestClient smoke verifier, missing-Falcon blocker, JSON-native/envelope checks, source contracts, and import-boundary scans.
- `inflation_dashboard/api/resources.py` - Mover bounds validation, `mover_count` alias support, `records` alias for retailer averages, and stable response keys.
- `inflation_dashboard/api/filters.py` - Warning metadata when selected files are skipped and no usable rows load.
- `.planning/STATE.md` - Advanced project state to Phase 3 readiness and recorded Phase 2 completion/blocker context.
- `.planning/ROADMAP.md` - Marked Phase 2 and 02-02 complete.
- `.planning/phases/02-falcon-api-backend/02-02-SUMMARY.md` - This execution summary.

## Decisions Made

- Kept runtime Falcon endpoint verification blocked rather than installing dependencies or fabricating success; dependency metadata already declares `falcon`, and the script tells users to use the project/user `uv` workflow.
- Ran boundary/source checks before importing Falcon so import-contract regressions remain visible even in the current missing-Falcon environment.
- Used a `records` alias in `/api/retailer-averages` to satisfy the stable generic list-key contract while retaining the earlier `retailer_averages` key.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.  
**Impact on plan:** No scope creep; implementation stayed within API modules, the smoke script, and planning metadata.

## Issues Encountered

- Falcon is still not installed in the active local Python environment. Final command output:

```text
$ python scripts/verify_falcon_api.py; code=$?; echo EXIT_CODE=$code
PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource
PASS source contracts: endpoint routes and stable response keys
Falcon is missing. Install project dependency metadata with the user's uv workflow (for example: uv sync or uv pip install -r requirements.txt), then rerun python scripts/verify_falcon_api.py.
EXIT_CODE=1
```

- `gsd-tools.cjs` exists under the Windows Hermes path, but invoking it through MSYS `$HOME` produced a `C:\c\Users\...` module path and failed. STATE/ROADMAP were updated manually instead.

## Verification Results

- T1 source validation command: PASS — invalid-filter branches and 400 `error_envelope` handling are present; runtime TestClient invalid-filter checks blocked by missing Falcon.
- T2 source validation command: PASS — stable empty-state response keys, skipped diagnostics, `history_row_count`, and `skipped_file_count` are present; runtime TestClient empty-state checks blocked by missing Falcon.
- T3 script command: `python scripts/verify_falcon_api.py` exited 1 with the explicit missing-Falcon/uv workflow message; source acceptance checks passed.
- T4 script command: PASS for boundary/source checks before the missing-Falcon blocker; script contains endpoint-specific contract assertions and concise success lines.
- T5 final command: `python scripts/verify_falcon_api.py` exited 1 after boundary/source PASS lines because Falcon is missing; `pyproject.toml` and `requirements.txt` both declare Falcon; `streamlit_app.py` remains unmodified.

## Self-Check: PASSED WITH DOCUMENTED DEPENDENCY BLOCKER

- All five plan tasks were executed and committed atomically.
- `scripts/verify_falcon_api.py` exists and is committed.
- Smoke requests in the script are bounded with `max_files=1` and use TestClient only; no persistent server is launched.
- API modules remain free of Streamlit/Plotly imports; domain/application/CSV adapter remain free of Falcon/Streamlit/Plotly imports according to source checks.
- Runtime endpoint smoke success was not fabricated; the missing Falcon dependency remains a real blocker and is documented here.
- `streamlit_app.py` was not modified.

## User Setup Required

None - no external service configuration required. To complete runtime endpoint smoke verification, install dependencies with the user's preferred `uv` workflow, for example:

```bash
uv sync
# or, if using the requirements workflow:
uv pip install -r requirements.txt
python scripts/verify_falcon_api.py
```

## Next Phase Readiness

Phase 2 is functionally complete with a documented local dependency blocker for runtime Falcon smoke requests. Phase 3 can proceed to `03-01` Streamlit API client work using the stable endpoint contracts and the smoke verifier as the backend contract check once dependencies are installed.

---
*Phase: 02-falcon-api-backend*  
*Completed: 2026-07-16*
