# Phase 2: Falcon API Backend - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 adds a Falcon Python Web Framework API backend that exposes dashboard data from the Phase 1 domain/application layer. It must provide health, inventory, product history, retailer averages, price movers, and coverage endpoints for later Streamlit consumption. This phase owns JSON serialization, Falcon resources, request validation, response envelopes, and API smoke verification. It does not refactor Streamlit to call HTTP yet, does not replace CSV storage, and does not add a database/cache service.

</domain>

<decisions>
## Implementation Decisions

### API Contract Shape
- **D-01:** Use REST-ish resource endpoints with query parameters: `/api/health`, `/api/inventory`, `/api/history`, `/api/retailer-averages`, `/api/movers`, and `/api/coverage`.
- **D-02:** Every endpoint response should use a consistent JSON envelope: `{ "data": ..., "meta": ..., "errors": ... }`. This is preferred over bare lists/objects so Streamlit can rely on stable keys and diagnostics can be added without contract churn.
- **D-03:** Dates must serialize as ISO date strings. Pandas/numpy values must be converted to JSON-native `int`, `float`, `str`, `bool`, or `null` values before Falcon returns them.
- **D-04:** Filtered endpoints should accept repeated query params for retailers, e.g. `?retailer=A&retailer=B`, plus `start_date`, `end_date`, and `max_files` where relevant.

### Loading and Cache Behavior
- **D-05:** `/api/inventory` should be cheap and cached. Filtered data endpoints should load history only after filters are resolved, preserving the Phase 1 inventory-first, load-second behavior.
- **D-06:** When filters are omitted, data endpoints should use the Phase 1 CSV adapter defaults: `DEFAULT_RETAILERS` and `DEFAULT_MAX_FILES_PER_RETAILER`, unless query parameters override them.
- **D-07:** Full-history/all-files loading is allowed only through an explicit request such as `max_files=0` or `all_history=true`. Responses should include metadata warning/count information so frontend callers understand the cost.
- **D-08:** Use stdlib caching only, such as `functools.lru_cache` or a small module-level cache keyed by primitive filter arguments. Do not add a dedicated caching dependency in this phase.

### Errors and Empty States
- **D-09:** Invalid filters should return HTTP 400 with envelope `errors`. Valid filters that simply yield no rows should return HTTP 200 with empty `data` and useful `meta`.
- **D-10:** Skipped-file diagnostics should be exposed in coverage and in data endpoint metadata. They are non-fatal unless all selected files fail or no usable data remains because of failures.
- **D-11:** API error payloads may include short, simple English messages suitable for frontend display later. The frontend can decide how to present/translate them in Phase 3.
- **D-12:** `/api/health` should be lightweight: verify app import/basic configuration only, not inventory discovery or CSV sample loading.

### Verification and Service Boundary
- **D-13:** Phase 2 verification should use Falcon testing utilities or direct resource invocation in an ad-hoc temp script. Do not require launching a long-running Falcon server for verification.
- **D-14:** Falcon-specific code should live in a dedicated adapter package/module, such as `inflation_dashboard/api/falcon_app.py`, and should import application use cases rather than duplicating domain/loading logic.
- **D-15:** If implementation imports Falcon, dependency metadata should be updated accordingly, but the user remains responsible for installing/running dependencies with `uv`.
- **D-16:** Verification must check framework boundaries: API modules should not import Streamlit, and domain/core modules should not import Falcon.

### Claude's Discretion
- Endpoint implementation details, helper names, and exact module splits are left to implementation judgment as long as the REST-ish contract, envelope shape, JSON serialization, bounded loading, and framework boundaries above are preserved.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning and Requirements
- `.planning/PROJECT.md` — Locked architecture decisions: Falcon API backend, Streamlit frontend, shared domain/application layer, CSV first adapter, and user-managed `uv` dependency workflow.
- `.planning/REQUIREMENTS.md` — Functional/non-functional requirements for Falcon endpoints, filters, JSON stability, bounded CSV loading, and lightweight verification.
- `.planning/ROADMAP.md` — Phase 2 boundary, success criteria, and planned split between Falcon resources/serialization and smoke/error handling.
- `.planning/STATE.md` — Current project state, blockers, and concerns including missing canonical test suite and large dataset performance risk.
- `.planning/phases/01-hexagonal-core-extraction/01-CONTEXT.md` — Prior decisions that Phase 2 must honor, especially DataFrame-first core APIs and JSON serialization deferred to Falcon.

### Codebase Maps
- `.planning/codebase/STACK.md` — Runtime/dependency facts and manifest inconsistencies relevant to adding Falcon.
- `.planning/codebase/ARCHITECTURE.md` — Existing scraper → CSV → Streamlit flow and absence of an API layer before this phase.
- `.planning/codebase/INTEGRATIONS.md` — Data roots, generated outputs, and secrets/cookie cautions.

### Existing Domain/Application Code
- `inflation_dashboard/adapters/csv_price_repository.py` — CSV inventory, bounded loading, default retailers/file cap, supported retailer allowlist, skipped-file diagnostics.
- `inflation_dashboard/application/use_cases.py` — Existing use-case functions for inventory filters, product history, averages, movers, and coverage.
- `inflation_dashboard/application/chart_specs.py` — Chart/table column specs that help define frontend-facing payload columns.
- `inflation_dashboard/domain/prices.py` — Normalized price-history columns, parsing, price coercion, and product frame normalization.
- `streamlit_app.py` — Current dashboard consumer and later Phase 3 frontend refactor target.
- `pyproject.toml` and `requirements.txt` — Dependency metadata to reconcile if Falcon imports are added.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `inflation_dashboard.adapters.csv_price_repository.discover_csv_inventory()` — Cheap inventory source for `/api/inventory` and default date/retailer metadata.
- `inflation_dashboard.adapters.csv_price_repository.load_price_history()` — Bounded CSV history loader that already accepts selected retailers, date range, and max-files-per-retailer.
- `inflation_dashboard.adapters.csv_price_repository.DEFAULT_RETAILERS` and `DEFAULT_MAX_FILES_PER_RETAILER` — Defaults to use when API filters are omitted.
- `inflation_dashboard.application.use_cases.*` — Existing calculations for product history, retailer averages, movers, coverage summary, coverage over time, and category coverage.
- `inflation_dashboard.application.chart_specs.*` — Existing table-column definitions and chart metadata useful for stable API payloads.

### Established Patterns
- Inventory should be discovered before expensive CSV loading.
- Loading remains bounded by retailers, date range, and max files per retailer.
- Core/application code uses pandas DataFrames internally; API code is responsible for converting them to JSON-safe records.
- CSV diagnostics are represented as skipped-file rows with relative file and reason.
- Framework-specific imports must stay outside domain/application modules.

### Integration Points
- New Falcon adapter code should connect to `inflation_dashboard.application` and `inflation_dashboard.adapters`, not to Streamlit rendering functions.
- Phase 3 Streamlit client should be able to call these endpoints without knowing CSV file paths.
- Verification can exercise the Falcon app/resource layer directly against bounded real CSV data without starting Streamlit.

</code_context>

<specifics>
## Specific Ideas

- Use REST-ish endpoints rather than a single aggregate dashboard payload.
- Use a uniform `{data, meta, errors}` envelope everywhere.
- Preserve all-history as an explicit opt-in, not the default.
- Keep `/api/health` lightweight so health checks do not trigger CSV scans.
- Prefer no new dependencies beyond Falcon itself if Falcon is imported.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---
*Phase: 2-Falcon API Backend*
*Context gathered: 2026-07-16*
