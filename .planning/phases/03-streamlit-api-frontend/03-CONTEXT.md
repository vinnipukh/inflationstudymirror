# Phase 3: Streamlit API Frontend - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 refactors the existing Streamlit dashboard so the four user-facing dashboard tabs get their data through the Phase 2 Falcon HTTP API instead of importing CSV adapters or application use cases directly. The phase must preserve current sidebar controls, search/autocorrection behavior, chart/table layout, and bounded loading UX while introducing a configurable API client. It does not add new Falcon endpoints beyond the Phase 2 contract, does not replace CSV storage, does not redesign the dashboard, and does not add database/cache infrastructure.

</domain>

<decisions>
## Implementation Decisions

### API Base URL and Client Error Behavior
- **D-01:** Streamlit should expose the Falcon API base URL as a sidebar text input with default `http://localhost:8000`. This keeps the local-first development path visible and easy to adjust.
- **D-02:** If the Falcon API is unreachable, times out, returns invalid JSON, or returns a payload that cannot be interpreted as the expected envelope, Streamlit should show a clear error and stop rendering affected dashboard data. It must not silently fall back to direct CSV/domain calls.
- **D-03:** The API client should use explicit timeouts: short requests such as `/api/health` and `/api/inventory` around 10 seconds, and data requests around 60 seconds because endpoints are backed by bounded CSV loading.
- **D-04:** The Streamlit client should require the Phase 2 envelope shape `{data, meta, errors}`. It should display API errors and retain `meta` for captions, warnings, selected filter counts, and diagnostics.

### Sidebar and Filter Flow over HTTP
- **D-05:** Streamlit should call `/api/inventory` first, then render retailer and date controls from the returned inventory payload. Sidebar control options must not be derived by scanning `Datas/` or calling `discover_csv_inventory()` directly from Streamlit.
- **D-06:** Sidebar defaults should preserve current behavior: use `DEFAULT_RETAILERS` when available in the inventory response, use the last 60 days as the default date window, and use `DEFAULT_MAX_FILES_PER_RETAILER` for the file cap.
- **D-07:** Selected sidebar filters should be passed to every data endpoint as HTTP query parameters: repeated `retailer` params, `start_date`, `end_date`, `max_files`, and `all_history` where relevant.
- **D-08:** Keep the existing "Load all files in date range" checkbox. When enabled, Streamlit should send `all_history=true` and/or `max_files=0`, and should show the API warning/meta information before or after the load so users understand the cost.

### Tab Payload Mapping
- **D-09:** Product explorer should call `/api/history` with `product_name` and `product_retailer` after the user selects a product. The endpoint-provided `history` records and `summary` should drive the metric cards, chart, and table.
- **D-10:** Retailer averages should call `/api/retailer-averages` and render the returned records directly. Streamlit should only adapt the payload to Plotly/table display and should not recalculate average/median trends locally.
- **D-11:** Price movers should call `/api/movers`, use `biggest_drops` and `biggest_gains`, and preserve the existing two-column tables.
- **D-12:** Coverage overview should call `/api/coverage` and render `summary`, `coverage_over_time`, `category_coverage`, and `skipped_files`, preserving the existing metrics, coverage charts, and skipped-file expander.

### Loading, Caching, Empty States, and Diagnostics
- **D-13:** Streamlit should cache API client calls with `st.cache_data`, keyed by API base URL plus the relevant filters. Inventory and data requests may use separate cache TTLs or cache functions so inventory discovery and expensive data loads are controlled independently.
- **D-14:** Use Streamlit spinners around API fetches and preserve sidebar estimated/loaded dataset summaries from API `meta` where available.
- **D-15:** HTTP 200 responses with empty `data` should produce tab-specific `st.info` messages. HTTP 400/API envelope errors should show `st.error` and stop only the affected section where practical.
- **D-16:** API `meta.warnings` and skipped-file diagnostics should be visible in the sidebar and/or coverage expander. Non-fatal skipped files should not crash the dashboard.

### Claude's Discretion
- Exact helper names, module split, cache TTL values, and internal request wrapper shape are left to implementation judgment as long as the API boundary, envelope enforcement, visible base URL, timeout behavior, and no-direct-CSV rule are preserved.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning and Requirements
- `.planning/PROJECT.md` — Project direction, locked Falcon + Streamlit split, hexagonal architecture target, `uv` workflow, and out-of-scope boundaries.
- `.planning/REQUIREMENTS.md` — Functional and non-functional requirements for API-backed Streamlit, four dashboard tabs, bounded loading, and lightweight verification.
- `.planning/ROADMAP.md` — Phase 3 boundary, dependency on Phase 2, success criteria, and planned split between API client/sidebar flow and tab refactor.
- `.planning/STATE.md` — Current project state, Phase 2 completion notes, large dataset risk, and Phase 3 continuity.

### Prior Phase Decisions
- `.planning/phases/01-hexagonal-core-extraction/01-CONTEXT.md` — DataFrame-first core APIs, chart-spec boundaries, stable normalized columns, and current Streamlit behavior preservation.
- `.planning/phases/02-falcon-api-backend/02-CONTEXT.md` — REST-ish endpoint contract, `{data, meta, errors}` envelope, query parameter filters, JSON serialization, bounded loading, and API error behavior.

### Codebase Maps
- `.planning/codebase/CONVENTIONS.md` — Streamlit function-oriented dashboard conventions, tab renderer names, search helper purity, and CSV handling conventions.
- `.planning/codebase/STRUCTURE.md` — Repository layout, large generated CSV/log data warning, and `streamlit_app.py` as the dashboard entrypoint.
- `.planning/codebase/STACK.md` — Streamlit/Plotly dependencies, manifest inconsistency, and dependency workflow cautions.

### Streamlit Frontend and API Contract Code
- `streamlit_app.py` — Current sidebar controls, search/autocorrection helpers, caching, four tab renderers, chart rendering, and direct domain/CSV imports to replace.
- `inflation_dashboard/api/falcon_app.py` — Registered Falcon routes: `/api/health`, `/api/inventory`, `/api/history`, `/api/retailer-averages`, `/api/movers`, `/api/coverage`.
- `inflation_dashboard/api/resources.py` — Response payload shapes for inventory, history/product summary, retailer averages, movers, coverage, and HTTP 400 error handling.
- `inflation_dashboard/api/filters.py` — Query parameter parsing, defaults, `all_history`, selected inventory counts, warnings, and bounded loading metadata.
- `inflation_dashboard/api/serialization.py` — Envelope helpers and JSON-safe conversion behavior that Streamlit must consume.
- `inflation_dashboard/application/use_cases.py` — Backend-owned calculations that Streamlit should stop calling directly for dashboard tab data.
- `inflation_dashboard/application/chart_specs.py` — Existing chart/table column specs that Streamlit can continue using for rendering if they do not require direct data loading.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `streamlit_app.py:39` `normalize_search_text()` and `streamlit_app.py:46` `rank_search_options()` — Keep these pure search/autocorrection helpers for Streamlit selection controls.
- `streamlit_app.py:68` `autocorrect_selectbox()` and `streamlit_app.py:92` `autocorrect_multiselect()` — Reuse for retailer/product controls after options come from API payloads.
- `streamlit_app.py:146` `render_chart()` — Reuse for Plotly rendering of API-returned records converted to DataFrames.
- `streamlit_app.py:169`, `streamlit_app.py:204`, `streamlit_app.py:227`, `streamlit_app.py:258` — Current tab renderers define the behavior and layout to preserve while replacing data sources.
- `inflation_dashboard.api.serialization.envelope()` and `error_envelope()` — Define the response contract the Streamlit client should enforce.
- `inflation_dashboard.api.filters.parse_common_filters()` — Defines supported query params and metadata that the Streamlit client should send/read.

### Established Patterns
- The dashboard currently resolves sidebar controls before expensive data loading; Phase 3 should preserve that by calling `/api/inventory` before data endpoints.
- Current dashboard loading is bounded by selected retailers, date range, and max files per retailer; Phase 3 should pass those constraints through HTTP rather than bypassing them.
- Streamlit uses `st.cache_data`; Phase 3 should keep caching at the frontend boundary but cache HTTP calls instead of direct CSV/domain calls.
- Plotly rendering remains Streamlit-owned; data loading and aggregation should become API-owned.
- API payloads use JSON-native records and metadata; Streamlit may convert records back into DataFrames for charts/tables.

### Integration Points
- Replace `streamlit_app.py` imports from `inflation_dashboard.adapters.csv_price_repository` and direct `inflation_dashboard.application.use_cases` data calls with an API client module/function set.
- Keep chart-spec imports only if they remain rendering metadata rather than data-loading/business-logic dependencies.
- Sidebar API base URL input should feed every client call and should be part of cache keys.
- Verification should assert Streamlit no longer imports CSV repository/use-case data functions for dashboard tab data and can exercise API client parsing without launching a long-running UI.

</code_context>

<specifics>
## Specific Ideas

- Default API base URL: `http://localhost:8000`.
- Short request timeout: about 10 seconds for health/inventory.
- Data request timeout: about 60 seconds for CSV-backed endpoints.
- API errors should be visible and should not trigger local CSV fallback.
- Preserve current four tabs, metric cards, chart/table patterns, sidebar load settings, all-history checkbox, and skipped-file diagnostics.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---
*Phase: 3-Streamlit API Frontend*
*Context gathered: 2026-07-17*
