# Phase 03: Streamlit API Frontend - Research

## Scope Summary

Phase 03 should refactor the existing root Streamlit entrypoint, `streamlit_app.py`, so dashboard data is fetched through the Phase 02 Falcon HTTP API rather than by importing the CSV adapter and application use cases directly.

Planning inputs inspected:

- `.planning/phases/03-streamlit-api-frontend/03-CONTEXT.md` — locks the visible sidebar API base URL default, error behavior, cache expectations, endpoint mapping, and no-local-fallback rule.
- `.planning/REQUIREMENTS.md` — Phase 03 covers REQ-03 through REQ-09 and REQ-11; especially AC-02 and AC-03.
- `.planning/ROADMAP.md` — Phase 03 has two plans: `03-01` API client/sidebar/filter flows, then `03-02` four-tab refactor.
- `.planning/STATE.md` — Phase 2 is complete; next plan is `03-01`; no canonical full test suite exists; use focused ad-hoc verification.
- `.planning/phases/02-falcon-api-backend/*` — Phase 2 added `inflation_dashboard/api/` plus `scripts/verify_falcon_api.py`; runtime endpoint smoke remains locally blocked by missing Falcon, but source/boundary checks pass.
- No repo-local `HERMES.md` or `.hermes/HERMES.md` was found.

Phase 03 is not a backend/API expansion phase. It should consume the actual Phase 2 contract now present in code:

- `GET /api/health`
- `GET /api/inventory`
- `GET /api/history`
- `GET /api/retailer-averages`
- `GET /api/movers`
- `GET /api/coverage`

Key implementation requirement for the planner: remove direct tab-data imports/calls from `streamlit_app.py`:

- `inflation_dashboard.adapters.csv_price_repository.discover_csv_inventory`
- `inflation_dashboard.adapters.csv_price_repository.load_price_history`
- `inflation_dashboard.application.use_cases.calculate_*`
- `inflation_dashboard.application.use_cases.get_product_history`
- `inflation_dashboard.application.use_cases.summarize_product_history`

Chart-spec imports from `inflation_dashboard.application.chart_specs` can remain because they are presentation metadata, not data loading/business logic.

## Current Streamlit Data Flow

Current dashboard entrypoint: `streamlit_app.py`.

### Imports and direct backend coupling

`streamlit_app.py:11-16` imports the CSV repository directly:

- `DEFAULT_MAX_FILES_PER_RETAILER`
- `DEFAULT_RETAILERS`
- `discover_csv_inventory as discover_csv_inventory_uncached`
- `load_price_history as load_price_history_uncached`

`streamlit_app.py:26-34` imports application use cases directly:

- `calculate_category_coverage`
- `calculate_coverage_over_time`
- `calculate_coverage_summary`
- `calculate_price_movers`
- `calculate_retailer_average_trends`
- `get_product_history`
- `summarize_product_history`

These imports are the main Phase 03 removal targets. After Phase 03, Streamlit should import its API client layer and rendering/chart helpers only; it must not scan `Datas/` or calculate dashboard tab payloads locally.

### Search/autocorrection controls to preserve

These helpers are Streamlit/UI-owned and should be reused unless the implementation intentionally moves them to a frontend helper module:

- `streamlit_app.py:39` `normalize_search_text(value)` — casefolds, strips accents, normalizes whitespace.
- `streamlit_app.py:46` `rank_search_options(query, options, limit=MAX_AUTOCORRECT_OPTIONS)` — prefixes, contains, fuzzy close matches.
- `streamlit_app.py:68` `autocorrect_selectbox(label, options, key, help_text=None)` — text input plus ranked `st.selectbox`.
- `streamlit_app.py:92` `autocorrect_multiselect(label, options, default, key, help_text=None)` — text input plus ranked `st.multiselect`.

Phase 03 requirements explicitly preserve search/autocorrection behavior (REQ-09 and context D-05/D-09 through D-12). The options should come from API payloads, not local DataFrame scans.

### Current caching to replace

- `streamlit_app.py:118` `discover_csv_inventory()` uses `@st.cache_data(show_spinner=False)` and calls the CSV adapter.
- `streamlit_app.py:123` `load_price_history(...)` uses `@st.cache_data(show_spinner="Loading selected scraped CSV files...")` and calls the CSV adapter.

Phase 03 should replace these with cached HTTP calls keyed by API base URL and query/filter parameters. Context D-13 allows separate cache TTLs for inventory and data requests.

### Current main/sidebar sequence

`streamlit_app.py:284` `main()` currently performs this sequence:

1. `st.set_page_config(...)` and static title/caption (`streamlit_app.py:285-288`). Caption still says "Built directly on the scraped CSV files in the repository" and must be changed once API-backed.
2. Calls `inventory = discover_csv_inventory()` (`streamlit_app.py:290`). This is a direct local CSV scan and must become an HTTP `GET /api/inventory` call.
3. Stops if inventory is empty (`streamlit_app.py:291-293`). Equivalent behavior should be driven by empty inventory API payload.
4. Builds `retailer_options` and `default_retailers` from local inventory and `DEFAULT_RETAILERS` (`streamlit_app.py:295-298`). Phase 03 should build from `data.retailers` and either hardcode/centralize equivalent defaults in Streamlit or consume API defaults via metadata if added later. Phase 03 must not import the CSV adapter constants just for this.
5. Renders sidebar retailer selection through `autocorrect_multiselect(...)` (`streamlit_app.py:300-308`). Preserve UI; options come from inventory API.
6. Computes local date bounds/default last-60-days from inventory DataFrame (`streamlit_app.py:310-318`). Phase 2 `parse_common_filters()` already defaults omitted data endpoint dates to last 60 days, but the Streamlit UI still needs explicit date input bounds from `/api/inventory` `data.min_date`/`data.max_date`.
7. Renders max-file slider and all-history checkbox (`streamlit_app.py:320-329`). Preserve labels and effective semantics; send query params instead of local function args.
8. Locally estimates selected inventory files by filtering the inventory DataFrame (`streamlit_app.py:331-339`). API common metadata includes `selected_inventory_file_count`; Streamlit can show this after a data fetch. For pre-fetch estimate, either compute only from richer future inventory metadata if added outside scope or change caption timing to use endpoint `meta` after first API call. Do not reintroduce local `Datas/` scanning.
9. Calls local cached `load_price_history(...)` once (`streamlit_app.py:341-346`), producing one `history` DataFrame and one `skipped` DataFrame used by all tabs.
10. Stops if local history is empty (`streamlit_app.py:348-352`). Under API-backed flow, tabs/endpoints should show tab-specific `st.info`/`st.error` states; context D-15 says HTTP 200 empty data is tab-specific info, while HTTP 400/API errors are `st.error`.
11. Shows loaded dataset summary from `history` columns (`streamlit_app.py:354-362`). Phase 03 should use endpoint `meta.history_row_count`, `meta.filters.selected_retailers`, `meta.filters.start_date/end_date`, `data.summary`, or the bounded history records from `/api/history`, not local loaded CSVs.
12. Creates four tabs and passes the shared local `history`/`skipped` DataFrames to renderers (`streamlit_app.py:364-380`). Phase 03 should change renderers to fetch/receive API payload records and convert them to DataFrames only for Plotly/table rendering.

### Current tab renderers

- `streamlit_app.py:169` `render_product_explorer(history)`:
  - Builds retailer options from `history["retailer"].unique()`.
  - Builds product labels from a local retailer slice.
  - Calls local `get_product_history(history, selected_retailer, selected_product)`.
  - Calls local `summarize_product_history(product_history)`.
  - Renders four metric cards, product price chart, and table.
  - Phase 03 issue: there is no dedicated product-list endpoint. The actual `/api/history` behavior supports omitted product selectors and returns bounded normalized history records, so the frontend can use a bounded `/api/history` call to populate product/retailer options, then call `/api/history` again with `product_name` and `product_retailer` for the selected product-specific history/summary.

- `streamlit_app.py:204` `render_retailer_average(history)`:
  - Builds retailer options from local history.
  - Uses `autocorrect_multiselect` and `st.radio("Aggregation", ["Average", "Median"], horizontal=True)`.
  - Calls `calculate_retailer_average_trends(...)` locally.
  - Phase 03 should call `/api/retailer-averages` with common filters plus `aggregation` and render `data.records` or `data.retailer_averages`.

- `streamlit_app.py:227` `render_price_movers(history)`:
  - Builds scope options from local history plus `"All retailers"`.
  - Uses `autocorrect_selectbox` and `st.slider("Rows to show", min_value=5, max_value=30, value=10)`.
  - Calls `calculate_price_movers(...)` locally.
  - Phase 03 should call `/api/movers` with common filters plus `scope_retailer` and `limit`.

- `streamlit_app.py:258` `render_overview(history, skipped)`:
  - Calls `calculate_coverage_summary`, `calculate_coverage_over_time`, `calculate_category_coverage` locally.
  - Shows skipped file diagnostics from local `skipped` DataFrame.
  - Phase 03 should call `/api/coverage` with common filters plus `category_limit=20` and render `data.summary`, `data.coverage_over_time`, `data.category_coverage`, and `data.skipped_files`.

## Falcon API Contract to Consume

Actual API registration is in `inflation_dashboard/api/falcon_app.py:8-18`:

- `create_app() -> falcon.App`
- Routes:
  - `/api/health` -> `HealthResource`
  - `/api/inventory` -> `InventoryResource`
  - `/api/history` -> `HistoryResource`
  - `/api/retailer-averages` -> `RetailerAveragesResource`
  - `/api/movers` -> `MoversResource`
  - `/api/coverage` -> `CoverageResource`

All resources use the response envelope from `inflation_dashboard/api/serialization.py:80`:

```python
{"data": json_safe(data), "meta": json_safe_mapping(meta or {}), "errors": json_safe(list(errors or []))}
```

Error envelopes come from `inflation_dashboard/api/serialization.py:90` and use:

```python
{"data": None, "meta": ..., "errors": [{"code": code, "message": message}]}
```

The Streamlit client should reject or clearly error on responses that do not have top-level `data`, `meta`, and `errors` keys, per Phase 03 context D-04.

### Common filters for data endpoints

Implemented in `inflation_dashboard/api/filters.py:68` `parse_common_filters(req)`:

- Repeated `retailer` query params via `req.get_param_as_list("retailer")` (`filters.py:73`).
- Defaults omitted retailers to `DEFAULT_RETAILERS` intersected with available inventory, then first up to 3 available retailers (`filters.py:84-90`).
- Date params: `start_date`, `end_date`, ISO `YYYY-MM-DD`; omitted date default is last 60 days bounded by inventory min/max (`filters.py:91-104`).
- `all_history` boolean via `parse_bool_param(req, "all_history")` (`filters.py:56-65`, `filters.py:106`).
- `max_files` integer; omitted defaults to `DEFAULT_MAX_FILES_PER_RETAILER`; `0` means uncapped (`filters.py:175-185`).
- Effective uncapped path when `all_history` or `max_files == 0`; sets `all_history=True` and warning `"all_history requested; CSV load is uncapped"` (`filters.py:108-121`).
- Metadata keys (`filters.py:122-133`):
  - `meta.filters.selected_retailers`
  - `meta.filters.start_date`
  - `meta.filters.end_date`
  - `meta.filters.max_files_per_retailer`
  - `meta.filters.all_history`
  - `meta.inventory_file_count`
  - `meta.selected_inventory_file_count`
  - `meta.warnings`

Data loading metadata added by `load_filtered_history(parsed_filters)` at `filters.py:145-162`:

- `meta.history_row_count`
- `meta.skipped_file_count`
- warning `"selected files skipped; no usable rows loaded"` when selected files are skipped and no usable rows load.

Invalid filters raise `ApiFilterError` and resources return HTTP 400 via `_set_filter_error()` (`resources.py:162-164`).

### `/api/health`

`inflation_dashboard/api/resources.py:31-34`:

- Status: HTTP 200.
- Payload: `data={"status": "ok"}`, `meta={"service": "inflation-dashboard-api"}`, `errors=[]`.
- Verification script asserts HealthResource does not reference inventory/history loading helpers.

Potential Phase 03 use: optional client connectivity check; short timeout around 10 seconds per context D-03. Do not require health for every rerun if it adds latency; a visible "Check API" path or cached health check is enough if planner chooses.

### `/api/inventory`

`inflation_dashboard/api/resources.py:37-49`:

- Calls `get_inventory()` and `list_inventory_filters(inventory)`.
- Payload:
  - `data.retailers`: list of retailer labels.
  - `data.min_date`: ISO date string or null after envelope serialization.
  - `data.max_date`: ISO date string or null after envelope serialization.
  - `meta.file_count`
  - `meta.inventory_file_count`

Phase 03 use:

- First call in `main()` after sidebar API base URL is known.
- Source for retailer options and date input bounds.
- Do not call `discover_csv_inventory()` from Streamlit.

### `/api/history`

`inflation_dashboard/api/resources.py:52-74`:

- Common filters: repeated `retailer`, `start_date`, `end_date`, `max_files`, `all_history`.
- Optional product selectors:
  - `product_name`
  - `product_retailer`
- If `product_name` is present:
  - Uses `product_retailer` or requires exactly one selected retailer via `_single_selected_retailer()` (`resources.py:167-174`).
  - Calls `get_product_history(history, retailer, product_name)` and `summarize_product_history(product_history)`.
  - Payload keys:
    - `data.history`: records from `PRODUCT_HISTORY_COLUMNS` = `date`, `price`, `category`, `source_file`.
    - `data.summary`: `latest_price`, `cheapest_price`, `cheapest_date`, `change_since_first_pct`.
  - Metadata also includes `product_name` and `product_retailer`.
- If `product_name` is absent:
  - Payload: `data.history`: bounded normalized history records using `HISTORY_COLUMNS` = `date`, `retailer`, `product_id`, `product_name`, `category`, `price`, `source_file`.
  - Adds warning `"history response may be large"` if all-history or more than 5000 rows.

Phase 03 use:

- Use omitted-product `/api/history` carefully as the only actual product option source unless a later phase adds a dedicated product-search endpoint. Keep it bounded by sidebar filters and consider a spinner/caption explaining it loads bounded history for product selection.
- Then call product-specific `/api/history?product_retailer=...&product_name=...` for chart/metrics/table.

### `/api/retailer-averages`

`inflation_dashboard/api/resources.py:77-97`:

- Common filters.
- Query param `aggregation`, default `Average`; valid values exactly `Average` or `Median` (`resources.py:80-86`).
- Payload:
  - `data.records`: list of records from `RETAILER_AVERAGE_COLUMNS` = `date`, `retailer`, `price`.
  - `data.retailer_averages`: same list alias.
- Metadata includes common load meta, `aggregation`, and `skipped_file_count`.

Phase 03 use:

- Preserve UI `st.radio("Aggregation", ["Average", "Median"], horizontal=True)`.
- Render `data.records` as a DataFrame with `retailer_average_chart_spec(aggregation)`.

### `/api/movers`

`inflation_dashboard/api/resources.py:100-136`:

- Common filters.
- Query params:
  - `scope_retailer`, default `All retailers`; if not all-retailers, must be in selected retailers (`resources.py:105-111`).
  - `limit`, with `mover_count` alias fallback, integer 5 through 30 (`resources.py:112-118`, `_parse_bounded_int` at `resources.py:177-187`).
- Payload:
  - `data.biggest_drops`: `BIGGEST_DROPS_COLUMNS` records.
  - `data.biggest_gains`: `BIGGEST_GAINS_COLUMNS` records.
- Metadata includes common load meta, `scope_retailer`, `limit`, `eligible_product_count`, `skipped_file_count`.

Phase 03 use:

- Preserve two-column tables and empty-state message for both empty lists.
- Scope options should be `"All retailers"` plus selected/current retailers. Prefer API `meta.filters.selected_retailers` or sidebar selected retailer list; do not infer by local CSV scan.

### `/api/coverage`

`inflation_dashboard/api/resources.py:139-159`:

- Common filters.
- Query param `category_limit`, default `20`, minimum `1` (`resources.py:144`).
- Payload:
  - `data.summary`: mapping from `calculate_coverage_summary`; keys include `retailer_count`, `product_count`, `observation_count`, `date_range`, `skipped_file_count` from use case behavior.
  - `data.coverage_over_time`: `COVERAGE_OVER_TIME_COLUMNS` = `date`, `retailer`, `tracked_products`.
  - `data.category_coverage`: `CATEGORY_COVERAGE_COLUMNS` = `retailer`, `category`, `products`.
  - `data.skipped_files`: `SKIPPED_DIAGNOSTICS_COLUMNS` = `file`, `reason`.
- Metadata includes common load meta, `category_limit`, `skipped_file_count`.

Phase 03 use:

- Preserve overview metric cards, coverage area chart, category bar chart, and skipped-file expander.
- Use endpoint `data.summary` for metric values rather than recomputing.

## Files and Symbols to Read/Modify

### Must read before planning tasks

- `.planning/phases/03-streamlit-api-frontend/03-CONTEXT.md`
  - Key decisions D-01 through D-16.
- `.planning/REQUIREMENTS.md`
  - REQ-03 through REQ-09, REQ-11; AC-02/AC-03/AC-04.
- `.planning/ROADMAP.md`
  - Phase 03 plan split and success criteria.
- `.planning/STATE.md`
  - Phase 2 status, dependency blocker, no canonical suite.
- `.planning/phases/02-falcon-api-backend/02-RESEARCH.md`
  - Endpoint contract rationale and filter/serialization expectations.
- `.planning/phases/02-falcon-api-backend/02-PATTERNS.md`
  - API boundary and verification patterns.
- `.planning/phases/02-falcon-api-backend/02-01-SUMMARY.md`
  - Actual files created and decisions: 60-day default copied into API, flexible `/api/history` behavior.
- `.planning/phases/02-falcon-api-backend/02-02-SUMMARY.md`
  - Stable empty-state keys, `records` alias, smoke verifier, current missing-Falcon runtime blocker.

### Primary frontend file

- `streamlit_app.py`
  - Preserve:
    - `normalize_search_text()` (`streamlit_app.py:39`)
    - `rank_search_options()` (`streamlit_app.py:46`)
    - `autocorrect_selectbox()` (`streamlit_app.py:68`)
    - `autocorrect_multiselect()` (`streamlit_app.py:92`)
    - `format_currency()` (`streamlit_app.py:140`)
    - `render_chart()` (`streamlit_app.py:146`) with a note that Streamlit local docs say `use_container_width` is deprecated in newer Streamlit and should be replaced with `width="stretch"` if changing that call.
    - four tab labels in `main()` (`streamlit_app.py:364-370`).
  - Modify/remove direct data calls:
    - Remove CSV adapter imports at `streamlit_app.py:11-16`.
    - Remove direct use-case imports at `streamlit_app.py:26-34`.
    - Remove/rewrite local cached `discover_csv_inventory()` at `streamlit_app.py:118-120`.
    - Remove/rewrite local cached `load_price_history()` at `streamlit_app.py:123-137`.
    - Rewrite `main()` local inventory/history sequence at `streamlit_app.py:290-346`.
    - Rewrite tab renderers at `streamlit_app.py:169`, `204`, `227`, `258` to consume API payloads.

### API backend contract files

- `inflation_dashboard/api/falcon_app.py`
  - `create_app()` and route strings at lines 8-18.
- `inflation_dashboard/api/resources.py`
  - `HealthResource.on_get()` lines 31-34.
  - `InventoryResource.on_get()` lines 37-49.
  - `HistoryResource.on_get()` lines 52-74.
  - `RetailerAveragesResource.on_get()` lines 77-97.
  - `MoversResource.on_get()` lines 100-136.
  - `CoverageResource.on_get()` lines 139-159.
  - `_single_selected_retailer()` lines 167-174.
  - `_parse_bounded_int()` lines 177-187.
- `inflation_dashboard/api/filters.py`
  - `UNCAPPED_WARNING` line 19.
  - `ApiFilterError` lines 22-29.
  - `ParsedFilters` lines 32-40.
  - `get_inventory()` lines 43-47.
  - `parse_bool_param()` lines 56-65.
  - `parse_common_filters()` lines 68-142.
  - `load_filtered_history()` lines 145-162.
- `inflation_dashboard/api/serialization.py`
  - `records_from_frame()` lines 48-69.
  - `envelope()` lines 80-87.
  - `error_envelope()` lines 90-93.

### Rendering metadata files safe to reuse

- `inflation_dashboard/application/chart_specs.py`
  - `PRODUCT_HISTORY_COLUMNS`, `RETAILER_AVERAGE_COLUMNS`, `BIGGEST_DROPS_COLUMNS`, `BIGGEST_GAINS_COLUMNS`, `SKIPPED_DIAGNOSTICS_COLUMNS`, `COVERAGE_OVER_TIME_COLUMNS`, `CATEGORY_COVERAGE_COLUMNS` lines 3-25.
  - `product_price_chart_spec(title)` lines 28-38.
  - `retailer_average_chart_spec(aggregation)` lines 41-51.
  - `coverage_area_chart_spec()` lines 54-64.
  - `category_coverage_bar_chart_spec()` lines 67-78.

These are presentation specs and can remain imported by Streamlit. Do not call application use-case computation functions from Streamlit.

### Verification/support files

- `scripts/verify_falcon_api.py`
  - Current backend contract verifier.
  - Running it now from repo root produced:
    - `PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource`
    - `PASS source contracts: endpoint routes and stable response keys`
    - `Falcon is missing...`
    - `EXIT_CODE=1`
  - It can be extended or paired with a new frontend contract verifier in Phase 03.
- `requirements.txt`
  - Has `requests==2.32.5` line 6 and `falcon` line 9. A Streamlit API client can use `requests` without introducing a new dependency if the project keeps requirements as runtime metadata.
- `pyproject.toml`
  - Currently declares `falcon` but not `requests`; it also has `requires-python = ">=3.14"`, which planning docs flag as manifest inconsistency. Do not turn Phase 03 into broad dependency cleanup unless verification is blocked.

## Existing Patterns to Reuse

### Streamlit/UI patterns

- Keep function-oriented single-file dashboard structure unless planner chooses a small helper module for API client. The current app is one root `streamlit_app.py`; no multipage app is present.
- Preserve search/autocorrection helpers exactly or near-exactly; they are independent of CSV loading.
- Preserve four tabs and current labels:
  - `Product explorer`
  - `Retailer averages`
  - `Price movers`
  - `Coverage overview`
- Preserve current chart specs and Plotly rendering path, but use API records converted into DataFrames.
- Preserve explicit bounded-load UI:
  - Retailer multiselect.
  - Date range input.
  - Max CSV files per retailer slider.
  - `Load all files in date range` checkbox.
- Use `st.cache_data` for HTTP calls, keyed by base URL and filter params. Streamlit skill guidance supports caching expensive data-loading calls with TTL/max entries.

### Suggested API client pattern

Planner should create either in `streamlit_app.py` or a new focused module such as `inflation_dashboard/frontend/api_client.py` / `inflation_dashboard/streamlit_api_client.py`. If creating a module, keep it frontend-only and free of Streamlit if practical, so it can be tested independently.

Recommended client responsibilities:

- Normalize base URL by stripping trailing slash.
- Build query params with repeated `retailer` keys. With `requests`, pass a list of pairs:
  - `[('retailer', 'Markets / Gurmar'), ('retailer', 'HomeGoods'), ('start_date', 'YYYY-MM-DD'), ...]`
- Use explicit timeouts:
  - `10` seconds for `/api/health` and `/api/inventory`.
  - `60` seconds for `/api/history`, `/api/retailer-averages`, `/api/movers`, `/api/coverage`.
- Parse JSON and enforce envelope keys exactly enough for frontend safety: `data`, `meta`, `errors` must exist.
- Treat non-2xx status and non-empty `errors` as displayable API errors. Context D-02 forbids silent fallback to CSV/domain calls.
- Return a small object/dict containing `data`, `meta`, and `errors`, or raise a frontend `ApiClientError` with a short message plus optional response metadata.
- Make cached Streamlit wrappers call the client, e.g. `fetch_inventory(api_base_url)`, `fetch_history(api_base_url, filters, product_name=None, product_retailer=None)`, etc.

### DataFrame conversion pattern

API returns JSON-native lists of records. Streamlit can convert lists to DataFrames for chart/table display:

- Product history: `pd.DataFrame(payload["data"].get("history", []))`
- Retailer averages: `pd.DataFrame(payload["data"].get("records", payload["data"].get("retailer_averages", [])))`
- Movers drops/gains: `pd.DataFrame(payload["data"].get("biggest_drops", []))`, `pd.DataFrame(payload["data"].get("biggest_gains", []))`
- Coverage over time/category/skipped: `pd.DataFrame(...)`

Date strings may need `pd.to_datetime(df["date"])` for smooth Plotly behavior. For product summary, `cheapest_date` is already a string/null, so current metric formatting must be adapted from `.strftime()` to direct string display.

### Backend verification pattern

Reuse `scripts/verify_falcon_api.py` as the backend contract gate. It does not launch a server; it uses Falcon `TestClient` if Falcon is installed and otherwise reports the missing dependency honestly. Phase 03 frontend verification should not rely on an always-running server unless the plan includes an explicit bounded local server step.

## Plan Boundaries

### 03-01: Add API client layer and wire sidebar/filter flows to API calls

Recommended scope:

- Add the configurable Falcon API base URL to the Streamlit sidebar, default `http://localhost:8000` per context D-01.
- Introduce an API client layer/wrapper with:
  - base URL normalization,
  - query param construction with repeated `retailer`,
  - explicit timeouts,
  - JSON/envelope validation,
  - error conversion for Streamlit display,
  - no local CSV/domain fallback.
- Replace `streamlit_app.py` inventory discovery flow with `/api/inventory`:
  - Retailer options from `data.retailers`.
  - Date bounds from `data.min_date`/`data.max_date`.
  - Inventory count from `meta.file_count`/`meta.inventory_file_count`.
- Keep sidebar controls and defaults equivalent:
  - Default selected retailers should prefer `Markets / Gurmar`, `ClothingStores / Vakko`, `HomeGoods` if present. Since Streamlit must stop importing CSV adapter constants, define frontend defaults locally or in a frontend config constant.
  - Date default should remain last 60 days bounded by inventory min/max.
  - Max files default should remain `45` without importing `DEFAULT_MAX_FILES_PER_RETAILER`; define a frontend constant or use API metadata if added later.
  - `Load all files in date range` sends `all_history=true` and/or `max_files=0`.
- Add shared filter/query representation for tab calls:
  - `retailer` repeated values,
  - `start_date`,
  - `end_date`,
  - `max_files`,
  - `all_history`.
- Add sidebar display for API warnings/meta when available.
- Acceptance criteria to encode:
  - `streamlit_app.py` no longer calls `discover_csv_inventory()` or imports `inflation_dashboard.adapters.csv_price_repository` for inventory/sidebar setup.
  - Inventory controls render solely from `/api/inventory` payload.
  - API base URL is visible and used in cache keys.
  - API client errors display `st.error` and stop affected rendering without local fallback.
  - Repeated retailer query serialization is covered by a focused unit/source check.

Suggested `<read_first>` for 03-01 tasks:

- `streamlit_app.py` lines 11-16, 118-137, 284-346.
- `inflation_dashboard/api/resources.py` `InventoryResource` and `HistoryResource`.
- `inflation_dashboard/api/filters.py` `parse_common_filters()` metadata keys.
- `.planning/phases/03-streamlit-api-frontend/03-CONTEXT.md` decisions D-01 through D-08 and D-13 through D-16.
- `requirements.txt` and `pyproject.toml` dependency state before choosing `requests` or stdlib `urllib`.

### 03-02: Refactor all four tabs to use API payloads and preserve existing UX behavior

Recommended scope:

- Refactor `render_product_explorer`:
  - Use API-backed bounded history records to populate retailer/product options, or another actual API payload if implementation introduces no new backend endpoint.
  - Preserve autocorrect selectboxes.
  - Call product-specific `/api/history` with `product_name` and `product_retailer` for selected product.
  - Render API `data.summary` metric cards and API `data.history` chart/table.
- Refactor `render_retailer_average`:
  - Preserve retailer multiselect and aggregation radio.
  - Call `/api/retailer-averages` with common filters and `aggregation`.
  - Render `data.records` or `data.retailer_averages`.
- Refactor `render_price_movers`:
  - Preserve scope selectbox and rows slider.
  - Call `/api/movers` with common filters, `scope_retailer`, and `limit`.
  - Render `data.biggest_drops` and `data.biggest_gains` two-column tables.
- Refactor `render_overview`:
  - Call `/api/coverage` with common filters and `category_limit=20`.
  - Render `data.summary`, `data.coverage_over_time`, `data.category_coverage`, and `data.skipped_files`.
- Remove local shared `history, skipped = load_price_history(...)` dependency from `main()`.
- Acceptance criteria to encode:
  - All four tab renderers get their tab data from API responses.
  - `streamlit_app.py` no longer imports direct application use-case functions for tab data.
  - Empty API data uses tab-specific `st.info`; HTTP/API errors show `st.error`.
  - Search/autocorrection controls remain present in product, retailer averages, and movers flows.
  - No direct `Datas/` scan remains in Streamlit.

Suggested `<read_first>` for 03-02 tasks:

- `streamlit_app.py` lines 169-280 and 364-380.
- `inflation_dashboard/api/resources.py` all endpoint resource response shapes.
- `inflation_dashboard/application/chart_specs.py` full file.
- `scripts/verify_falcon_api.py` endpoint-shape assertions.
- `.planning/phases/03-streamlit-api-frontend/03-CONTEXT.md` decisions D-09 through D-16.

## Verification Strategy

Because no canonical frontend test suite exists, plan focused ad-hoc verification with source assertions plus import/runtime checks where dependencies are available.

### Backend contract gate

Run from repo root:

```bash
python scripts/verify_falcon_api.py
```

Current observed local output during research:

```text
PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource
PASS source contracts: endpoint routes and stable response keys
Falcon is missing. Install project dependency metadata with the user's uv workflow (for example: uv sync or uv pip install -r requirements.txt), then rerun python scripts/verify_falcon_api.py.
EXIT_CODE=1
```

Planner should treat this as a known dependency blocker for runtime endpoint smoke, not a failing API contract source check. If the executor can install dependencies through the approved `uv` workflow, rerun until endpoint smoke passes.

### Source assertions for no direct CSV/domain tab data

Add or run a Python source assertion after 03-01/03-02 edits. It should fail if `streamlit_app.py` contains any of these imports/calls:

- `inflation_dashboard.adapters.csv_price_repository`
- `discover_csv_inventory_uncached`
- `load_price_history_uncached`
- `discover_csv_inventory()` as local CSV scan wrapper
- `load_price_history()` as local CSV load wrapper
- `from inflation_dashboard.application.use_cases import`
- Direct calls to:
  - `calculate_retailer_average_trends(`
  - `calculate_price_movers(`
  - `calculate_coverage_summary(`
  - `calculate_coverage_over_time(`
  - `calculate_category_coverage(`
  - `get_product_history(`
  - `summarize_product_history(`

Allow imports from `inflation_dashboard.application.chart_specs`.

### API client behavior assertions

If an API client module is introduced, add a lightweight script/snippet that:

- Constructs a request for multiple retailers and asserts query params preserve repeated `retailer` entries rather than comma-joining accidentally.
- Validates good envelope shape `{data, meta, errors}`.
- Rejects missing/invalid envelope shape.
- Converts HTTP 400-style envelope errors into displayable client errors.
- Confirms timeout values are explicit: around 10 seconds for health/inventory and around 60 seconds for data endpoints.

This can be implemented without a live server by monkeypatching/mocking `requests.get` or the selected HTTP function.

### Streamlit smoke/import check

At minimum, run from repo root after edits:

```bash
python -m py_compile streamlit_app.py
```

If dependencies and runtime allow, run a non-interactive import guard or short Streamlit launch. Because a persistent browser UI is not required for plan verification, prefer compile/source/client tests unless executor has time to run a bounded Streamlit process.

### Manual/source assertions for UX preservation

Verify source still contains:

- `autocorrect_selectbox(` in product explorer and movers flows.
- `autocorrect_multiselect(` in sidebar and retailer average flow.
- `st.tabs(["Product explorer", "Retailer averages", "Price movers", "Coverage overview"])` or equivalent labels.
- `st.sidebar.text_input` or equivalent visible API base URL control with default `http://localhost:8000`.
- Query params for `/api/retailer-averages`, `/api/movers`, `/api/coverage`, and `/api/history` include common filters.

### Full local verification when dependencies/server are available

If Falcon is installed and a local server can be started safely:

1. Start the Falcon API with the documented/available app command from Phase 4 docs if present; otherwise do not invent a persistent deployment path in Phase 03.
2. Run Streamlit:
   ```bash
   streamlit run streamlit_app.py
   ```
3. In the UI, set API base URL to `http://localhost:8000`.
4. Confirm each tab renders with bounded defaults and no direct CSV fallback.

Do not make this the only verification gate because Phase 03 planning context expects focused ad-hoc verification and Phase 4 owns deployment/run docs.

## Risks and Landmines

- **Product list endpoint gap:** There is no dedicated `/api/products` endpoint. The current actual workaround is `/api/history` without `product_name`, which returns bounded normalized history records including `product_name`. This can be large if users request all history. Plan product selector carefully and keep it bounded/cached.
- **No silent fallback:** Context D-02 explicitly forbids falling back to direct CSV/domain calls when the API is down, invalid, or times out. Error handling must stop affected rendering with visible `st.error`.
- **Missing Falcon locally:** Research reran `python scripts/verify_falcon_api.py`; source checks pass but endpoint smoke is blocked by `ModuleNotFoundError: No module named 'falcon'`. Use `uv` workflow if installing; do not fabricate endpoint success.
- **Dependency metadata inconsistency:** `requirements.txt` includes `requests==2.32.5`, but `pyproject.toml` does not. `pyproject.toml` also says `requires-python = ">=3.14"`. Avoid broad dependency cleanup unless the chosen API client cannot be verified.
- **Repeated query params:** API expects repeated `retailer` params. Do not comma-join retailer labels unless backend is changed to parse that, which is out of Phase 03 scope.
- **All tabs currently compute eagerly inside `st.tabs`:** Streamlit computes tab bodies even when hidden. If each tab fetches independently, a rerun may make several expensive API requests. Use `st.cache_data`, bounded filters, spinners, and possibly shared cached `/api/history` for product options only. Do not accidentally call all-history in multiple tabs.
- **Current chart helper uses `use_container_width=True`:** Local Streamlit skill notes this is deprecated in newer Streamlit; if touching chart calls, prefer `width="stretch"` where supported. This is not core Phase 03 scope but is a safe modernization if verified.
- **Date parsing/formatting differences:** API dates are strings/null. Current product metric code expects a pandas timestamp and calls `.strftime()`. Convert/adapt summary dates safely.
- **Empty DataFrame/table columns:** API empty lists convert to DataFrames with no columns. Before slicing by chart/table columns, ensure missing columns are handled gracefully or create DataFrames with expected columns.
- **Sidebar loaded summary source:** Current summary comes from local `history`. Replace with API `meta` and/or coverage summary; do not recompute from local CSV. Be clear which endpoint owns which summary.
- **Existing uncommitted repo changes:** `git status --short` showed unrelated modified/untracked files (`.planning/config.json`, `forecasting/forecastingtest.ipynb`, `pyproject.toml`, `uv.lock`, Gurmar data CSVs). Phase 03 executors should avoid overwriting unrelated work and should inspect diffs before committing.
- **Do not modify backend contract unless blocked:** Phase 03 should consume Phase 2 endpoints as-is. Adding new API endpoints would expand scope and affect roadmap separation.

## Research Complete

Phase 03 is ready to plan. The planner should split work exactly along the roadmap:

- `03-01` creates/uses a strict HTTP API client, exposes a configurable sidebar API base URL, and moves inventory/sidebar/filter flow to `/api/inventory` plus shared query params.
- `03-02` refactors the four tab renderers to consume `/api/history`, `/api/retailer-averages`, `/api/movers`, and `/api/coverage` payloads while preserving search/autocorrection and chart/table UX.

Most important planning guardrails:

1. Do not import CSV adapter or application use-case calculation functions from Streamlit after this phase.
2. Preserve bounded loading by passing selected retailers/date/max-files/all-history through HTTP.
3. Enforce API envelope/error handling and show visible Streamlit errors without local fallback.
4. Use source assertions and the Phase 2 smoke verifier as concrete verification gates.
