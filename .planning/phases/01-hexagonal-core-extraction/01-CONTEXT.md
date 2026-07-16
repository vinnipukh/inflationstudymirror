# Phase 1: Hexagonal Core Extraction - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 extracts the data parsing, CSV inventory/loading, dashboard use cases, and chart-spec preparation currently embedded in `streamlit_app.py` into framework-independent modules. The phase must preserve current Streamlit behavior while creating a clean core boundary for later Falcon API work. It does not add Falcon endpoints, does not refactor Streamlit to HTTP calls, and does not replace CSV storage.

</domain>

<decisions>
## Implementation Decisions

### Module Boundary
- **D-01:** Implementation may choose the final package shape based on repository fit, but it must preserve a clear hexagonal boundary suitable for later Falcon work.
- **D-02:** Public core interfaces should start as thin functions returning pandas DataFrames, matching the current dashboard data model and minimizing extraction risk.
- **D-03:** Core code may produce chart-spec dictionaries, but it must not import Streamlit or Falcon.
- **D-04:** Phase 1 should refactor `streamlit_app.py` to import and use the new core while preserving the current UI behavior. Extraction should be proven by actual use from the existing dashboard entrypoint.

### Plotly Boundary
- **D-05:** Core should return Plotly-ready dictionary specs, not Plotly `Figure` objects.
- **D-06:** Chart specs are bounded to the existing four dashboard views: product explorer, retailer averages, price movers, and coverage overview.
- **D-07:** Chart specs should include chart type, x/y/color columns, titles, axis labels, and table column lists.
- **D-08:** Core must not import Plotly. Streamlit remains responsible for converting chart specs into Plotly figures.

### Data Contract
- **D-09:** The stable normalized price-history DataFrame columns are `date`, `retailer`, `product_id`, `product_name`, `category`, `price`, and `source_file`.
- **D-10:** Loader functions should preserve the current return shape: `(history_df, skipped_df)`.
- **D-11:** Public application/use-case calls should be separate functions for inventory, product history slice, retailer averages, price movers, and coverage.
- **D-12:** Phase 1 should preserve pandas dtypes internally. JSON serialization is a Phase 2 Falcon API responsibility.

### CSV Diagnostics and Parsing Behavior
- **D-13:** Preserve skipped-file diagnostics as rows with relative file path and reason.
- **D-14:** Preserve flexible CSV loading with `sep=None` and `engine="python"` to tolerate delimiter drift across scraped source files.
- **D-15:** Preserve the current supported-retailer allowlist in the CSV adapter to avoid surprise slow or invalid loads.
- **D-16:** Preserve existing source-specific normalization branches, including HousesRent and Watson behavior, unless verification proves a simplification is safe.

### Verification
- **D-17:** Phase 1 verification should use an ad-hoc Python script under the OS temp directory that imports the extracted core and exercises inventory, loading, and aggregation functions against bounded real CSV data.
- **D-18:** Verification must assert core modules do not import Streamlit or Falcon.
- **D-19:** Verification must assert expected columns and non-empty outputs for a small selected retailer/date/file-cap load.
- **D-20:** A separate `python -m py_compile` requirement is not needed if the ad-hoc script imports and exercises the changed code.

### Claude's Discretion
- The exact package name and directory layout are left to implementation judgment, as long as the boundary is clear and downstream Falcon integration is not blocked.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning and Requirements
- `.planning/PROJECT.md` — Project direction, locked decisions, scope, success criteria, and deployment architecture target.
- `.planning/REQUIREMENTS.md` — Functional/non-functional requirements and acceptance criteria for the API-backed dashboard architecture.
- `.planning/ROADMAP.md` — Phase boundary, Phase 1 goal, success criteria, and plan split.
- `.planning/STATE.md` — Current project state, active blockers, and session continuity.

### Existing Dashboard Code
- `streamlit_app.py` — Source of current CSV loading, normalization, search/autocorrection, four dashboard tabs, and performance controls to preserve during extraction.

### Codebase Maps
- `.planning/codebase/STACK.md` — Current Python/runtime/dependency facts and manifest inconsistencies.
- `.planning/codebase/ARCHITECTURE.md` — Existing scraper → CSV → Streamlit architecture and monolithic dashboard boundary.
- `.planning/codebase/INTEGRATIONS.md` — Source data roots, generated outputs, and secrets/cookie cautions.
- `.planning/codebase/CONVENTIONS.md` — Existing conventions if implementation needs style guidance.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `streamlit_app.py:33` `parse_date_from_name()` — Date extraction behavior for dated CSV filenames.
- `streamlit_app.py:40` `normalize_search_text()` and `streamlit_app.py:47` `rank_search_options()` — Search/autocorrection helpers that should remain usable by Streamlit; only data/core extraction is in Phase 1.
- `streamlit_app.py:119` `coerce_price()` — Existing price normalization behavior to preserve.
- `streamlit_app.py:161` `detect_retailer()` — Current path-to-retailer detection logic.
- `streamlit_app.py:195` `discover_csv_inventory()` — Current lazy inventory pattern.
- `streamlit_app.py:229` `build_product_frame()` — Current source-specific normalization logic.
- `streamlit_app.py:275` `load_price_history()` — Current bounded CSV loading and skipped-file diagnostics.
- `streamlit_app.py:367`, `streamlit_app.py:404`, `streamlit_app.py:430`, `streamlit_app.py:501` — Existing four tab rendering paths whose data logic should become core use cases.

### Established Patterns
- Sidebar controls are resolved before expensive CSV loading.
- Default data scope is bounded by selected retailers, date range, and max files per retailer.
- CSV loading currently uses pandas and returns normalized DataFrames; preserving this reduces risk.
- Current charting is Streamlit + Plotly-specific and should stay outside the extracted core, with the core returning chart specs instead.

### Integration Points
- `streamlit_app.py` should become the first consumer of the extracted core in Phase 1.
- Later Falcon endpoints should consume the same core use-case functions rather than re-implementing loading/aggregation.
- Existing CSV data under `Datas/` remains the first adapter/storage backend.

</code_context>

<specifics>
## Specific Ideas

- Chart specs should be dictionaries that are easy for Streamlit now and Falcon later, but they should not be full Plotly figure payloads.
- Keep Phase 1 pragmatic: DataFrame-first APIs and current behavior preservation matter more than perfect abstraction.
- The existing four dashboard views define the chart-spec scope; do not generalize for unknown future charts in this phase.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---
*Phase: 1-Hexagonal Core Extraction*
*Context gathered: 2026-07-16*
