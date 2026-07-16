# Phase 02 Research: Falcon API Backend

**Phase:** 02 - Falcon API Backend  
**Research date:** 2026-07-16  
**Question answered:** What do I need to know to PLAN this phase well?

## Executive summary

Phase 2 should add a dedicated Falcon adapter layer around the Phase 1 `inflation_dashboard` package. The existing repo already has the important reusable pieces:

- `inflation_dashboard/adapters/csv_price_repository.py` discovers supported CSV inventory and loads bounded price history from `Datas/`.
- `inflation_dashboard/application/use_cases.py` computes inventory filter metadata, product history, product summary metrics, retailer average trends, price movers, and coverage data.
- `inflation_dashboard/application/chart_specs.py` defines the stable table/chart column sets used by the Streamlit dashboard.
- `streamlit_app.py` is still the only UI and imports Streamlit/Plotly; Phase 2 API code must not import it.

The planner should treat this as a thin API/resource/serialization phase, not another domain extraction. Create Falcon-specific modules under the existing package, likely `inflation_dashboard/api/`, and keep all CSV scanning/loading behind existing adapter and application functions. Use the agreed response envelope everywhere:

```json
{ "data": ..., "meta": ..., "errors": ... }
```

## Repo facts that constrain the plan

### Planning decisions already locked

From `.planning/phases/02-falcon-api-backend/02-CONTEXT.md`:

- Endpoints: `/api/health`, `/api/inventory`, `/api/history`, `/api/retailer-averages`, `/api/movers`, `/api/coverage`.
- All endpoint responses use `{ "data": ..., "meta": ..., "errors": ... }`.
- Dates serialize as ISO date strings.
- Pandas/numpy values must become JSON-native `int`, `float`, `str`, `bool`, or `null` before Falcon returns them.
- Filtered endpoints accept repeated `retailer` query params, plus `start_date`, `end_date`, and `max_files` where relevant.
- `/api/inventory` should be cheap and cached.
- Filtered data endpoints should preserve the inventory-first, load-second behavior.
- Omitted filters should use `DEFAULT_RETAILERS` and `DEFAULT_MAX_FILES_PER_RETAILER` from the CSV adapter.
- Full history/all files requires explicit opt-in: `max_files=0` or `all_history=true`.
- Invalid filters return HTTP 400 with envelope `errors`; valid empty results return HTTP 200 with empty `data` and useful `meta`.
- `/api/health` must be lightweight and should not scan inventory or load CSVs.
- Verification should use Falcon testing utilities or direct resource invocation, not a required long-running server.
- Falcon code should live in a dedicated adapter package/module and import application use cases, not duplicate domain/loading logic.
- API modules must not import Streamlit; domain/core modules must not import Falcon.

### Current application and adapter surface

Observed files and symbols:

- `inflation_dashboard/adapters/csv_price_repository.py`
  - `discover_csv_inventory(raw_data_root=RAW_DATA_ROOT) -> pd.DataFrame`
    - Returns columns: `path`, `retailer`, `date`, `size_mb`.
    - Filters to `SUPPORTED_RETAILERS` and parses dates from filenames.
  - `load_price_history(selected_retailers, start_date, end_date, max_files_per_retailer, inventory=None, project_root=PROJECT_ROOT) -> tuple[pd.DataFrame, pd.DataFrame]`
    - Returns `(history_df, skipped_df)`.
    - History columns are `date`, `retailer`, `product_id`, `product_name`, `category`, `price`, `source_file`.
    - Skipped diagnostics columns are `file`, `reason`.
    - Uses `pd.read_csv(..., sep=None, engine="python", encoding="utf-8-sig", on_bad_lines="skip")`.
    - Applies the per-retailer cap when `max_files_per_retailer > 0`; `0` means no cap.
  - Constants:
    - `DEFAULT_RETAILERS = ("Markets / Gurmar", "ClothingStores / Vakko", "HomeGoods")`
    - `DEFAULT_MAX_FILES_PER_RETAILER = 45`
    - `SUPPORTED_RETAILERS` contains 10 retailer labels.

- `inflation_dashboard/application/use_cases.py`
  - `list_inventory_filters(inventory)` returns `retailers`, `min_date`, `max_date`, and `file_count`.
  - `get_product_history(history, retailer, product_name)` filters a single retailer/product and sorts by date.
  - `summarize_product_history(product_history)` returns `latest_price`, `cheapest_price`, `cheapest_date`, `change_since_first_pct`.
  - `calculate_retailer_average_trends(history, selected_retailers, aggregation)` accepts aggregation string `"Average"` or `"Median"`.
  - `calculate_price_movers(history, selected_retailer, mover_count)` accepts selected retailer or literal `"All retailers"`; returns `biggest_drops`, `biggest_gains`, and `stats` DataFrames.
  - `calculate_coverage_summary(history, skipped)` returns count/date-range summary.
  - `calculate_coverage_over_time(history)` returns `date`, `retailer`, `tracked_products`.
  - `calculate_category_coverage(history, limit=20)` returns top categories.

- `inflation_dashboard/application/chart_specs.py`
  - Stable column constants useful for API payload shaping:
    - `PRODUCT_HISTORY_COLUMNS = ["date", "price", "category", "source_file"]`
    - `RETAILER_AVERAGE_COLUMNS = ["date", "retailer", "price"]`
    - `BIGGEST_DROPS_COLUMNS = ["retailer", "product_name", "latest_price", "max_price", "savings_vs_peak", "drop_from_peak_pct", "last_seen"]`
    - `BIGGEST_GAINS_COLUMNS = ["retailer", "product_name", "first_price", "latest_price", "change_since_first_pct", "first_seen", "last_seen"]`
    - `SKIPPED_DIAGNOSTICS_COLUMNS = ["file", "reason"]`
    - `COVERAGE_OVER_TIME_COLUMNS = ["date", "retailer", "tracked_products"]`
    - `CATEGORY_COVERAGE_COLUMNS = ["retailer", "category", "products"]`

### Current runtime/dependency state

Observed with `python` from repo root:

```text
falcon: missing
pandas: installed
streamlit: installed
plotly: installed
```

Dependency metadata is inconsistent:

- `pyproject.toml` has `requires-python = ">=3.14"` and `dependencies = []`.
- `requirements.txt` lists scraper dependencies but does not include `pandas`, `streamlit`, `plotly`, or `falcon`.
- `.planning/codebase/STACK.md` already warns that `pyproject.toml`, `requirements.txt`, GitHub Actions, and local runtime are inconsistent.

Planning implication: implementation must update dependency metadata if it imports Falcon, but avoid broad dependency churn. The user manages installation with `uv`; do not assume dependencies are installed during planning.

### Current data scale observed

A live bounded inventory check returned:

```text
inventory_rows 748
default_retailers ('Markets / Gurmar', 'ClothingStores / Vakko', 'HomeGoods')
default_max_files 45
retailer_count 10
min_date 2026-02-21 00:00:00
max_date 2026-07-16 00:00:00
columns ['path', 'retailer', 'date', 'size_mb']
```

Planning implication: keep `/api/health` non-scanning, cache inventory discovery, and make data endpoints explicit about loaded row/file counts.

### Existing repo has no API/test layer yet

A source search found no existing Falcon API module or tests. The only `falcon` references are in planning docs and import-boundary checks from Phase 1 summaries. No `HERMES.md`, `.hermes/skills/`, or `.agents/skills/` exists in the repo.

## Falcon framework facts relevant to implementation

Falcon 4.3.1 docs observed:

- WSGI resources define methods such as `on_get(self, req, resp)`.
- JSON responses can be assigned via `resp.media = {...}` and status via `resp.status = falcon.HTTP_200`.
- Apps are created with `falcon.App()` and routes are registered with `app.add_route(path, Resource())`.
- Query helper `req.get_param_as_list(name, ...)` supports repeated query params such as `?retailer=A&retailer=B`; comma splitting is not automatic unless configured or a delimiter is provided.
- Query helper `req.get_param_as_int(name, min_value=..., max_value=..., default=...)` can validate integer params.
- Query helper `req.get_param_as_date(name, format_string="%Y-%m-%d", ...)` parses date params.
- `falcon.testing.TestClient(app)` can simulate requests with methods like `simulate_get()` and exposes parsed `result.json`.

## Recommended module/file design

Create only Falcon/API-specific modules in Phase 2. Recommended shape:

```text
inflation_dashboard/
  api/
    __init__.py
    falcon_app.py          # create_app() and route registration
    resources.py           # Falcon resource classes or handlers
    serialization.py       # JSON-safe envelope/DataFrame conversion helpers
    filters.py             # query parsing and validation helpers
```

This exact split is not mandatory, but the planner should require these responsibilities somewhere:

1. App factory/route registration.
2. Resource methods for endpoint behavior.
3. Shared filter parsing/defaulting/validation.
4. Shared JSON serialization/envelope helpers.
5. Shared data loading orchestration using existing CSV adapter + application use cases.

Avoid modifying `streamlit_app.py` in Phase 2 except if an implementation discovers a hard blocker; Phase 3 owns Streamlit HTTP refactor.

## Endpoint design guidance

### Common response envelope

Use this shape for both successes and errors:

```python
{
    "data": data_payload,
    "meta": {
        "filters": {...},
        "row_count": ...,
        "skipped_file_count": ...,
        "warnings": [...],
    },
    "errors": [],
}
```

For HTTP 400:

```python
{
    "data": None,
    "meta": {"filters": raw_or_partial_filters},
    "errors": [{"code": "invalid_filter", "message": "..."}],
}
```

Use stable keys even when data is empty. Prefer `[]`, `{}`, `None`, and count metadata over omitted keys.

### `/api/health`

Purpose: lightweight import/config check only.

Suggested success payload:

```json
{
  "data": {"status": "ok"},
  "meta": {"service": "inflation-dashboard-api"},
  "errors": []
}
```

Do not call `discover_csv_inventory()` or `load_price_history()`.

### `/api/inventory`

Purpose: expose cheap available-retailer/date/file metadata for frontend controls.

Implementation path:

1. Call cached `discover_csv_inventory()`.
2. Call `list_inventory_filters(inventory)`.
3. Serialize dates as ISO strings.
4. Return retailer options and inventory metadata.

Suggested data/meta split:

- `data.retailers`: sorted retailer labels.
- `data.min_date`, `data.max_date`: ISO dates or `null`.
- `meta.file_count`: total supported inventory rows.
- Optionally include per-retailer counts/date ranges if useful; if added, compute from inventory and serialize safely.

### `/api/history`

Purpose: provide product history data needed by Product explorer.

Filter params:

- `retailer` repeated list: data-loading scope. If absent, use `DEFAULT_RETAILERS` filtered to available inventory retailers.
- `start_date`, `end_date`: optional dates; default from inventory min/max or dashboard-like recent window if the planner chooses. If implementing default recent window, mirror `streamlit_app.py` lines 310-312: `default_start = max(min_date, max_date - 60 days)`.
- `max_files`: optional int; default `DEFAULT_MAX_FILES_PER_RETAILER`; `0` means all files.
- `all_history`: optional bool; if true, treat effective max as `0`.
- Product-specific selectors likely needed for frontend parity even though not named in the phase context: `product_name` and optionally `product_retailer`/single `retailer`. The existing use case `get_product_history(history, retailer, product_name)` requires both retailer and product name. If product filters are omitted, return loaded history records or a product/retailer option list only if the planner explicitly scopes that behavior.

Recommended plan choice: support optional `product_name` and `product_retailer` on `/api/history`; when both are present, return `history` and `summary`. When absent, return the loaded normalized history records with metadata, but warn that payload size depends on filters.

Data shape when product selectors are supplied:

```json
{
  "data": {
    "history": [...records using PRODUCT_HISTORY_COLUMNS...],
    "summary": {
      "latest_price": 12.34,
      "cheapest_price": 10.00,
      "cheapest_date": "2026-07-01",
      "change_since_first_pct": -3.2
    }
  },
  "meta": {...},
  "errors": []
}
```

### `/api/retailer-averages`

Purpose: data for retailer average chart/table.

Filter params:

- Common load filters: repeated `retailer`, `start_date`, `end_date`, `max_files`, `all_history`.
- `aggregation`: accept `Average` or `Median`; default `Average` to match `streamlit_app.py` radio options.

Implementation path:

1. Resolve/load bounded history.
2. Call `calculate_retailer_average_trends(history, selected_retailers, aggregation)`.
3. Serialize records using `RETAILER_AVERAGE_COLUMNS`.

Invalid aggregation should return 400.

### `/api/movers`

Purpose: biggest drops/gains for the price movers tab.

Filter params:

- Common load filters.
- `scope_retailer`: optional selected retailer for mover calculation; default `All retailers`.
- `limit` or `mover_count`: default 10, constrained to the Streamlit slider range observed in `streamlit_app.py` (`5..30`) unless the planner wants a different API-only range.

Implementation path:

1. Resolve/load bounded history.
2. Call `calculate_price_movers(history, selected_retailer, mover_count)`.
3. Return `biggest_drops` and `biggest_gains`, using `BIGGEST_DROPS_COLUMNS` and `BIGGEST_GAINS_COLUMNS` when columns exist.
4. Include `stats_count` or `eligible_product_count` in `meta` if helpful.

Valid no-repeat observations should be HTTP 200 with empty lists, matching Streamlit's current empty-state message.

### `/api/coverage`

Purpose: coverage overview, row counts, date/retailer/category coverage, skipped diagnostics.

Filter params:

- Common load filters.
- Optional `category_limit` for `calculate_category_coverage(history, limit=20)`, default `20`.

Implementation path:

1. Resolve/load bounded history and skipped diagnostics.
2. Call:
   - `calculate_coverage_summary(history, skipped)`
   - `calculate_coverage_over_time(history)`
   - `calculate_category_coverage(history, limit=category_limit)`
3. Return:

```json
{
  "data": {
    "summary": {...},
    "coverage_over_time": [...],
    "category_coverage": [...],
    "skipped_files": [...]
  },
  "meta": {...},
  "errors": []
}
```

Include skipped-file diagnostics both in `data.skipped_files` and count metadata.

## Filter parsing and loading architecture

Plan a small shared filter object/dict rather than duplicating query parsing in every resource.

Recommended behavior:

1. Cached inventory first:
   - `inventory = get_inventory()` where `get_inventory` wraps `discover_csv_inventory()` with `functools.lru_cache(maxsize=1)` or an equivalent module cache.
2. Determine available retailers from `list_inventory_filters(inventory)`.
3. Parse repeated `retailer` params with Falcon `req.get_param_as_list("retailer")`.
4. If `retailer` absent, use `DEFAULT_RETAILERS` intersected with available retailers; if that intersection is empty, use first few available retailers just as `streamlit_app.py` does for defaults.
5. Validate selected retailers are in inventory; unknown values should return HTTP 400.
6. Parse `start_date`/`end_date` as ISO dates. If absent, use inventory min/max or the current Streamlit default recent window.
7. Reject `start_date > end_date` with HTTP 400.
8. Parse `all_history` bool and `max_files` int.
9. Effective max files:
   - `0` if `all_history=true`.
   - Otherwise `max_files` if provided.
   - Otherwise `DEFAULT_MAX_FILES_PER_RETAILER`.
10. Reject negative `max_files`.
11. Call `load_price_history(tuple(selected_retailers), start_date, end_date, effective_limit, inventory=inventory)` only for endpoints that need data.

Metadata should include enough diagnostics for the frontend:

- `selected_retailers`
- `start_date`
- `end_date`
- `max_files_per_retailer`
- `all_history`
- `inventory_file_count`
- `selected_inventory_file_count` or `estimated_loaded_files`
- `history_row_count`
- `skipped_file_count`
- warnings such as `"all_history requested; CSV load is uncapped"`

## Serialization conventions

Phase 2 must own JSON serialization because Phase 1 intentionally kept pandas-native DataFrame APIs.

Plan explicit helpers in `serialization.py`, for example:

- `to_json_value(value)`:
  - `pd.Timestamp`, `datetime.date`, `datetime.datetime` -> ISO string.
  - `pd.NA`, `NaN`, `NaT`, `numpy.nan` -> `None`.
  - numpy scalar values -> `.item()`.
  - floats/ints/bools/strings remain native.
- `records_from_frame(frame, columns=None)`:
  - Select existing columns in requested order.
  - Convert each cell through `to_json_value`.
  - Return `[]` for empty frames.
- `json_safe_mapping(mapping)` for summaries/meta.
- `envelope(data, meta=None, errors=None)`.

Important pitfall: `DataFrame.to_dict("records")` alone will leave `Timestamp`, `NaN`, and possibly numpy scalar values that are not stable JSON-native values. The API should convert before assigning `resp.media`.

## Caching guidance

Use stdlib-only caching per context decision D-08.

Minimum viable cache:

- `@lru_cache(maxsize=1)` around inventory discovery.

Optional bounded history cache:

- Keyed by primitive tuple `(selected_retailers_tuple, start_date_iso, end_date_iso, max_files_per_retailer)`.
- Be careful returning mutable DataFrames from cache. If caching history, either treat returned frames as read-only or return `.copy()` before use-case mutations. Existing use cases mostly copy/filter but not all outputs are immutable.

Do not add Redis, database, disk cache, or background worker in Phase 2.

## Error and empty-state planning

Expected 400 cases:

- Unknown retailer filter.
- Bad date format.
- `start_date > end_date`.
- Negative `max_files`.
- Unsupported `aggregation` for retailer averages.
- Invalid mover/category limits if outside chosen bounds.

Expected 200 empty cases:

- Inventory exists but selected date window has no files.
- CSV files load successfully but history has no usable rows.
- Movers have no products with at least two observations.
- Product history selector is valid but no rows match.

For CSV skipped files:

- Non-fatal skipped rows should be included in `meta.skipped_file_count` and coverage diagnostics.
- If all selected files fail and no usable data remains, context says diagnostics are non-fatal unless all selected files fail or no usable data remains because of failures. The planner should decide whether that becomes 500 or a 200 empty data payload with an `errors` warning; D-10 suggests treating all-fail as fatal enough to surface clearly.

## Plan split recommendation

The roadmap already splits Phase 2 into two plans:

### 02-01: Add Falcon app/resources and response serialization

Focus:

- Add Falcon dependency metadata minimally.
- Create `inflation_dashboard/api/` package.
- Implement app factory and route registration.
- Implement endpoint resource skeletons and successful happy paths.
- Implement envelope and JSON-safe serialization helpers.
- Implement common filter parsing/defaults.
- Verify import and happy-path requests with Falcon testing if Falcon is installed, or provide a clear dependency-missing note if not.

Suggested completion check:

- `create_app()` imports successfully when Falcon is available.
- `falcon.testing.TestClient(create_app()).simulate_get('/api/health')` returns JSON envelope.
- A bounded `/api/inventory` and one data endpoint return JSON-native envelopes.

### 02-02: Add API smoke verification and error/empty-state handling

Focus:

- Complete all endpoints if any were skeletonized.
- Add 400 handling for invalid filters.
- Add 200 empty-state behavior.
- Add source/import boundary verification:
  - API imports Falcon but not Streamlit.
  - Domain/application/adapters do not import Falcon or Streamlit.
- Add or run an ad-hoc temp verification script using `falcon.testing.TestClient` against bounded real CSV data.
- Verify no long-running server is required.

Suggested smoke endpoints:

- `GET /api/health`
- `GET /api/inventory`
- `GET /api/retailer-averages?retailer=Markets%20/%20Gurmar&max_files=1`
- `GET /api/movers?retailer=Markets%20/%20Gurmar&max_files=1&limit=5`
- `GET /api/coverage?retailer=Markets%20/%20Gurmar&max_files=1`
- An invalid retailer request returns 400 with `errors`.

## Verification strategy for the planner

Because there is no canonical test suite, plan focused ad-hoc verification and make it explicit.

Recommended temp script behavior:

1. Add repo root to `sys.path` if the script lives outside the repo. Phase 1 hit this exact issue when running a temp script from `C:/Users/arhan/AppData/Local/Temp/...`.
2. Import `inflation_dashboard.api.falcon_app.create_app`.
3. Use `falcon.testing.TestClient(create_app())`.
4. Exercise health and inventory.
5. Exercise bounded data endpoints with `Markets / Gurmar` and `max_files=1` to avoid large loads.
6. Assert every response has `data`, `meta`, `errors` keys.
7. Assert JSON date strings, no raw pandas `Timestamp`/NaN values, and expected list/dict shapes.
8. Assert invalid filters return HTTP 400.
9. Scan source files for forbidden imports.

If Falcon is not installed in the active environment, implementation can still write code and dependency metadata, but final verification should either install via user-approved `uv` workflow or report the missing dependency as a blocker. For a normal executor with install permission, `uv` should be preferred over ad hoc `pip` based on project decisions.

## Risks and pitfalls

- **Falcon missing locally:** observed `falcon: missing`. Plans should include dependency metadata and verification assumptions.
- **Dependency manifests are inconsistent:** `pyproject.toml` says Python `>=3.14` and has no deps; `requirements.txt` lacks dashboard/API deps. Avoid a broad manifest overhaul unless the plan explicitly owns it.
- **Large CSV loads:** inventory has 748 supported CSV files. Do not default to all-history loads; keep caps and warn in metadata when uncapped.
- **Repeated query params:** Falcon's generic `get_param()` returns only one value when a parameter repeats. Use `get_param_as_list("retailer")` for repeated retailer filters.
- **Date/numeric JSON issues:** pandas `Timestamp`, `NaN`, `NaT`, and numpy scalar values must be converted before setting `resp.media`.
- **Mutable DataFrames and caching:** cached DataFrames can be accidentally mutated. Copy or treat as read-only.
- **Boundary drift:** API modules may import Falcon; `inflation_dashboard/domain`, `inflation_dashboard/application`, and existing CSV adapter should remain framework-independent and must not import Falcon or Streamlit.
- **Do not refactor Streamlit in Phase 2:** Phase 3 owns Streamlit HTTP client work.
- **Product history ambiguity:** the endpoint list says `/api/history`, while the current use case requires `retailer` and `product_name`. The plan should explicitly define optional `product_name`/single-retailer selectors or provide a clear all-history payload contract for Phase 3.
- **Skipped diagnostics:** skipped CSV files are normal and should not automatically fail a request, but all-fail/no-usable-data cases need clear metadata/errors.
- **No repo-local Hermes/agent instructions:** no `HERMES.md`, `.hermes/skills/`, or `.agents/skills/` were found.

## Concrete files likely to change in Phase 2

Likely created:

- `inflation_dashboard/api/__init__.py`
- `inflation_dashboard/api/falcon_app.py`
- `inflation_dashboard/api/resources.py`
- `inflation_dashboard/api/serialization.py`
- `inflation_dashboard/api/filters.py`

Likely modified:

- `pyproject.toml` and/or `requirements.txt` to declare Falcon and possibly existing dashboard/data dependencies if the implementation plan chooses to reconcile metadata enough for API verification.

Avoid modifying in Phase 2 unless necessary:

- `streamlit_app.py` — Phase 3 owns frontend HTTP calls.
- Domain/application modules — only change if API planning uncovers a reusable core bug; otherwise keep Phase 2 as adapter code.
- Scraper or data files under `Codes/`, `Datas/`, `Inflations/`.

## Planner checklist

Before writing the implementation plan, decide explicitly:

- Which exact files in `inflation_dashboard/api/` own app factory, resources, filters, and serialization.
- Whether `/api/history` requires `product_name` + selected retailer for product-specific payloads or returns loaded history records when omitted.
- Date defaults: full inventory min/max versus Streamlit's current 60-day default window.
- Parameter names for mover scope and count: e.g. `scope_retailer` + `limit` versus `selected_retailer` + `mover_count`.
- Whether to cache only inventory or also bounded history loads.
- How dependency metadata will be updated without broad manifest churn.
- The exact Falcon TestClient smoke script and boundary scan assertions.

## Research conclusion

Phase 2 is ready to plan. The safest plan is a thin Falcon adapter package that reuses Phase 1 DataFrame-first adapter/use-case functions, adds strict filter parsing/defaults, converts every pandas result into JSON-safe envelopes, and verifies via Falcon `TestClient` against bounded real CSV data. The main planning risks are dependency metadata inconsistency, missing local Falcon install, response-shape ambiguity for `/api/history`, and accidental large CSV scans.
