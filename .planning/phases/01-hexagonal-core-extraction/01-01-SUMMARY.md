---
phase: 01-hexagonal-core-extraction
plan: 01-01
subsystem: dashboard-core
tags: [pandas, csv, streamlit-boundary, hexagonal-architecture]
requires: []
provides:
  - Framework-independent price normalization domain module
  - CSV repository adapter for inventory discovery and bounded history loading
  - Streamlit cached wrappers around extracted loader functions
affects: [phase-02-falcon-api, phase-03-streamlit-api-frontend]
tech-stack:
  added: []
  patterns:
    - Domain helpers under inflation_dashboard/domain contain pure pandas normalization.
    - CSV storage access lives under inflation_dashboard/adapters with Streamlit caching retained only at the UI boundary.
key-files:
  created:
    - inflation_dashboard/__init__.py
    - inflation_dashboard/domain/__init__.py
    - inflation_dashboard/domain/prices.py
    - inflation_dashboard/adapters/__init__.py
    - inflation_dashboard/adapters/csv_price_repository.py
  modified:
    - streamlit_app.py
key-decisions:
  - "Kept public loader APIs DataFrame-first so Phase 2 can reuse them without JSON coupling."
  - "Kept st.cache_data wrappers in streamlit_app.py instead of importing Streamlit in the adapter."
patterns-established:
  - "Domain module: pure parsing/normalization with no framework imports."
  - "Adapter module: CSV discovery/loading behind bounded selected_retailers/date/max-files filters."
requirements-completed: [REQ-02, REQ-10, REQ-11]
coverage:
  - id: D1
    description: "Price parsing and normalized product rows extracted into inflation_dashboard/domain/prices.py."
    requirement: "REQ-10"
    verification:
      - kind: other
        ref: "python - <<'PY' import/scan/coerce_price check"
        status: pass
    human_judgment: false
  - id: D2
    description: "CSV inventory and bounded history loading extracted into inflation_dashboard/adapters/csv_price_repository.py."
    requirement: "REQ-02"
    verification:
      - kind: integration
        ref: "python - <<'PY' bounded real CSV load with max_files_per_retailer=1"
        status: pass
    human_judgment: false
  - id: D3
    description: "Streamlit entrypoint consumes extracted repository functions through cached UI-boundary wrappers."
    requirement: "REQ-11"
    verification:
      - kind: other
        ref: "python - <<'PY' streamlit_app source assertions and adapter import check"
        status: pass
    human_judgment: false
duration: 0h 45m
completed: 2026-07-16
status: complete
---

# Phase 01 Plan 01-01: CSV Price Loading Core Summary

**Framework-independent pandas price normalization and bounded CSV repository extraction consumed by the existing Streamlit dashboard.**

## Performance

- **Duration:** 45 min
- **Started:** 2026-07-16T09:10:00Z
- **Completed:** 2026-07-16T09:55:00Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Created `inflation_dashboard/domain/prices.py` with the stable normalized history columns and source-specific HousesRent/Watson normalization branches.
- Created `inflation_dashboard/adapters/csv_price_repository.py` with supported-retailer inventory discovery, flexible CSV parsing, per-retailer caps, and skipped-file diagnostics.
- Refactored `streamlit_app.py` to keep Streamlit caching at the UI boundary while delegating CSV discovery/loading to the extracted adapter.

## Task Commits

1. **Tasks 01-01-T1 through 01-01-T3: domain, adapter, and Streamlit loader extraction** - `5a74973` (feat)

## Verification

Command run from repository root:

```bash
python - <<'PY'
# imports domain/adapter modules, scans core package for forbidden Streamlit/Falcon imports,
# discovers real Datas/ inventory, and loads one bounded Markets / Gurmar CSV window
PY
```

Observed output:

```text
inventory_rows 748
loaded Markets / Gurmar 275 skipped 0
PASS 01-01
```

Exit code: 0

## Files Created/Modified

- `inflation_dashboard/__init__.py` - Package marker for extracted dashboard core.
- `inflation_dashboard/domain/__init__.py` - Domain package marker.
- `inflation_dashboard/domain/prices.py` - Pure pandas price/date/product normalization helpers.
- `inflation_dashboard/adapters/__init__.py` - Adapter package marker.
- `inflation_dashboard/adapters/csv_price_repository.py` - CSV inventory and bounded history loader adapter.
- `streamlit_app.py` - Cached wrapper consumer of the extracted adapter.

## Decisions Made

- Kept the adapter DataFrame-first and pandas-native so Falcon serialization can be added later without constraining Phase 1 internals.
- Kept Streamlit caching wrappers in `streamlit_app.py` to preserve current dashboard behavior without framework imports in core modules.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 01-02 can now build application/use-case functions on top of the extracted CSV adapter and domain helpers.

## Self-Check: PASSED

- Key created files exist on disk.
- Core package imports without Streamlit or Falcon imports.
- Bounded real CSV load returned `(history_df, skipped_df)` pandas DataFrames.

---
*Phase: 01-hexagonal-core-extraction*
*Completed: 2026-07-16*
