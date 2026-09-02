---
phase: 01-hexagonal-core-extraction
plan: 01-02
subsystem: dashboard-application
tags: [pandas, use-cases, chart-specs, streamlit-boundary]
requires:
  - phase: 01-01
    provides: CSV repository and normalized history DataFrame contract
provides:
  - Framework-independent dashboard use-case functions
  - Plotly-ready chart specification dictionaries without Plotly imports
  - Streamlit renderers wired to application functions
affects: [phase-02-falcon-api, phase-03-streamlit-api-frontend]
tech-stack:
  added: []
  patterns:
    - Application use cases receive/return pandas DataFrames and simple dictionaries.
    - Chart-spec helpers return metadata dictionaries while Streamlit remains the Plotly rendering boundary.
key-files:
  created:
    - inflation_dashboard/application/__init__.py
    - inflation_dashboard/application/use_cases.py
    - inflation_dashboard/application/chart_specs.py
  modified:
    - streamlit_app.py
key-decisions:
  - "Kept chart specs as dictionaries rather than Plotly figures so core code remains framework-independent."
  - "Kept Streamlit control labels and tab structure unchanged while moving calculations into application functions."
patterns-established:
  - "Application functions own product history, retailer averages, movers, and coverage calculations."
  - "Streamlit renderers convert chart specs to Plotly figures at the UI boundary."
requirements-completed: [REQ-02, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-11]
coverage:
  - id: D1
    description: "Dashboard application use cases extracted for product history, averages, movers, and coverage."
    requirement: "REQ-05"
    verification:
      - kind: other
        ref: "python - <<'PY' in-memory use-case checks"
        status: pass
    human_judgment: false
  - id: D2
    description: "Chart specs return Plotly-ready dictionaries without Plotly, Streamlit, or Falcon imports."
    requirement: "REQ-10"
    verification:
      - kind: other
        ref: "python - <<'PY' chart spec key/no-to_plotly_json assertions"
        status: pass
    human_judgment: false
  - id: D3
    description: "Streamlit renderers use extracted use cases and chart specs while preserving the four dashboard tabs."
    requirement: "REQ-08"
    verification:
      - kind: other
        ref: "python - <<'PY' streamlit wiring source assertions"
        status: pass
    human_judgment: false
  - id: D4
    description: "Focused temp verification script exercises imports, forbidden import scans, in-memory use cases, and bounded real CSV loading."
    requirement: "REQ-11"
    verification:
      - kind: integration
        ref: "python C:/Users/arhan/AppData/Local/Temp/hermes-verify-inflation-dashboard-core.py"
        status: pass
    human_judgment: false
duration: 0h 35m
completed: 2026-07-16
status: complete
---

# Phase 01 Plan 01-02: Dashboard Use Cases and Chart Specs Summary

**Pandas dashboard calculations and Plotly-ready chart metadata extracted into framework-independent application modules.**

## Performance

- **Duration:** 35 min
- **Started:** 2026-07-16T09:56:00Z
- **Completed:** 2026-07-16T10:31:00Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments

- Created `inflation_dashboard/application/use_cases.py` with inventory filter metadata, product history summaries, retailer average trends, price movers, and coverage calculations.
- Created `inflation_dashboard/application/chart_specs.py` with dictionary specs and table column constants for the existing dashboard views.
- Refactored `streamlit_app.py` renderers to call extracted application functions and convert chart specs to Plotly figures only at the Streamlit boundary.
- Added and ran a temp OS verification script at `C:/Users/arhan/AppData/Local/Temp/hermes-verify-inflation-dashboard-core.py`.

## Task Commits

1. **Tasks 01-02-T1 through 01-02-T4: use cases, chart specs, Streamlit wiring, and verification** - `6a1e3c0` (feat)

## Verification

Commands run from repository root:

```bash
python - <<'PY'
# in-memory use-case and chart-spec checks
PY
```

Observed output:

```text
PASS 01-02 in-memory
```

```bash
python - <<'PY'
# streamlit_app wiring and application forbidden-import source assertions
PY
```

Observed output:

```text
PASS streamlit wiring source assertions
```

```bash
python C:/Users/arhan/AppData/Local/Temp/hermes-verify-inflation-dashboard-core.py
```

Observed output:

```text
inventory_rows=748
real_csv_load=loaded retailer='Markets / Gurmar' history_rows=275 skipped_rows=0
PASS hermes-verify-inflation-dashboard-core
```

Exit code: 0

```bash
python - <<'PY'
# ast.parse changed Python files
PY
```

Observed output:

```text
PASS syntax parse changed Python files
```

## Files Created/Modified

- `inflation_dashboard/application/__init__.py` - Application package marker.
- `inflation_dashboard/application/use_cases.py` - Framework-independent dashboard calculation functions.
- `inflation_dashboard/application/chart_specs.py` - Chart spec dictionaries and table column constants.
- `streamlit_app.py` - Uses application functions and chart specs for dashboard rendering.

## Decisions Made

- Kept pandas DataFrames internal for Phase 1; JSON serialization remains a Phase 2 API concern.
- Used chart spec dictionaries as a thin boundary contract rather than adding Plotly to core modules.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The first run of the temp verification script could not import `inflation_dashboard` because executing a script outside the repository puts the temp directory on `sys.path`. Fixed by adding the repository root (`Path.cwd()`) to `sys.path` at the top of the temp script, then reran successfully.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 2 can consume `inflation_dashboard.adapters.csv_price_repository` and `inflation_dashboard.application.use_cases` from Falcon resources without importing Streamlit.

## Self-Check: PASSED

- Key created files exist on disk.
- Application modules contain no Streamlit, Falcon, or Plotly imports/text.
- Streamlit retains the four dashboard renderers and imports Plotly only at the UI boundary.
- Temp verification script exited 0 against bounded real CSV data.

---
*Phase: 01-hexagonal-core-extraction*
*Completed: 2026-07-16*
