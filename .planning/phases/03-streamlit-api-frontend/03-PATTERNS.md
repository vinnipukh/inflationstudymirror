# Phase 03: Streamlit API Frontend - Patterns

## Files to Create or Modify

### Primary modification target: `streamlit_app.py`

**Role:** Streamlit UI entrypoint and dashboard renderer. After Phase 03 it should be a frontend/API consumer only.

**Current data flow to replace:**

- `streamlit_app.py:11-16` imports CSV repository constants/functions directly:
  - `DEFAULT_MAX_FILES_PER_RETAILER`
  - `DEFAULT_RETAILERS`
  - `discover_csv_inventory as discover_csv_inventory_uncached`
  - `load_price_history as load_price_history_uncached`
- `streamlit_app.py:26-34` imports application use-case calculations directly:
  - `calculate_category_coverage`
  - `calculate_coverage_over_time`
  - `calculate_coverage_summary`
  - `calculate_price_movers`
  - `calculate_retailer_average_trends`
  - `get_product_history`
  - `summarize_product_history`
- `streamlit_app.py:118-137` wraps direct CSV inventory/history loading in `st.cache_data`.
- `streamlit_app.py:290-346` scans inventory and loads shared local history before rendering tabs.
- `streamlit_app.py:169-280` renders all four tabs from local `history`/`skipped` DataFrames and local calculation functions.

**Required end-state:**

- No import from `inflation_dashboard.adapters.csv_price_repository` in Streamlit.
- No import from `inflation_dashboard.application.use_cases` in Streamlit.
- Chart-spec imports from `inflation_dashboard.application.chart_specs` may remain because they are rendering metadata.
- `main()` obtains sidebar options from `/api/inventory` and passes common filter query params to tab renderers/API fetchers.
- Four tabs fetch or receive API payloads from `/api/history`, `/api/retailer-averages`, `/api/movers`, and `/api/coverage`.

**Existing UI helpers to preserve:**

- `streamlit_app.py:39-43` `normalize_search_text()`.
- `streamlit_app.py:46-65` `rank_search_options()`.
- `streamlit_app.py:68-89` `autocorrect_selectbox()`.
- `streamlit_app.py:92-115` `autocorrect_multiselect()`.
- `streamlit_app.py:140-143` `format_currency()`.
- `streamlit_app.py:146-166` `render_chart()`.
- `streamlit_app.py:364-370` tab labels:
  - `Product explorer`
  - `Retailer averages`
  - `Price movers`
  - `Coverage overview`

### New or focused API client module

**Likely file to create:** one of:

- `inflation_dashboard/frontend/api_client.py`, or
- `inflation_dashboard/streamlit_api_client.py`, or
- a small client section inside `streamlit_app.py` if the planner keeps the current one-file dashboard style.

**Role:** Frontend HTTP boundary for Falcon endpoints. Prefer a Streamlit-free module for testability, with `st.cache_data` wrappers kept in `streamlit_app.py`.

**Responsibilities:**

- Normalize API base URL by stripping trailing slashes.
- Build query parameters with repeated `retailer` entries.
- Use explicit timeouts: around `10` seconds for `/api/health` and `/api/inventory`, around `60` seconds for data endpoints.
- Parse JSON.
- Require top-level envelope keys exactly enough for safety: `data`, `meta`, `errors`.
- Convert non-2xx, invalid JSON, missing envelope keys, and non-empty `errors` into displayable frontend errors.
- Never fall back to CSV/domain calls.

### Verification script additions

**Likely file to create or modify:**

- Add a new focused verifier such as `scripts/verify_streamlit_api_frontend.py`, or extend the implementation plan to run a source assertion snippet.
- Keep `scripts/verify_falcon_api.py` as the existing backend contract gate.

**Role:** Lightweight source/client contract verification without requiring a long-running Streamlit UI.

**Assertions to cover:**

- `streamlit_app.py` no longer imports CSV repository or use-case calculation functions.
- Repeated `retailer` query serialization is preserved.
- API envelope validation accepts `{data, meta, errors}` and rejects missing/invalid shapes.
- HTTP/API errors are represented as visible frontend errors.
- Cache keys include API base URL and filters through cached function parameters.

### Files to read but not modify for contract/reference

- `inflation_dashboard/api/resources.py` — source of endpoint payload shapes.
- `inflation_dashboard/api/filters.py` — source of common query params, defaults, warnings, and metadata.
- `inflation_dashboard/api/serialization.py` — source of envelope/error shape.
- `inflation_dashboard/application/chart_specs.py` — reusable chart/table columns and chart specs.
- `scripts/verify_falcon_api.py` — existing verifier/source assertion style.

No repo-local `HERMES.md` or `.hermes/HERMES.md` was found during research/pattern mapping.

## API Client Pattern

### Closest existing analogs

The backend already defines the contract the frontend client must enforce:

- `inflation_dashboard/api/serialization.py:80-87`:
  ```python
  def envelope(data: object, meta: Mapping[object, object] | None = None, errors: Sequence[object] | None = None) -> dict[str, object]:
      return {
          "data": json_safe(data),
          "meta": json_safe_mapping(meta or {}),
          "errors": json_safe(list(errors or [])),
      }
  ```
- `inflation_dashboard/api/serialization.py:90-93`:
  ```python
  def error_envelope(code: str, message: str, *, meta: Mapping[object, object] | None = None) -> dict[str, object]:
      return envelope(None, meta=meta or {}, errors=[{"code": code, "message": message}])
  ```
- `scripts/verify_falcon_api.py:135-148` validates backend envelopes and JSON-native payloads:
  ```python
  def _assert_envelope(payload: dict[str, Any], label: str) -> None:
      assert set(payload.keys()) == ENVELOPE_KEYS, f"{label} envelope keys were {set(payload.keys())}"
      json.dumps(payload, allow_nan=False)
      _assert_json_native(payload, label)
      assert isinstance(payload["errors"], list), f"{label} errors must be a list"
  ```

### Client behavior to plan

Use a small request wrapper with this shape, adapted to the implementation style:

```python
ENVELOPE_KEYS = {"data", "meta", "errors"}
SHORT_TIMEOUT_SECONDS = 10
DATA_TIMEOUT_SECONDS = 60

class ApiClientError(RuntimeError):
    def __init__(self, message: str, *, meta: dict[str, object] | None = None):
        super().__init__(message)
        self.meta = meta or {}


def normalize_api_base_url(api_base_url: str) -> str:
    return api_base_url.rstrip("/")


def build_common_params(filters: DashboardFilters) -> list[tuple[str, object]]:
    params: list[tuple[str, object]] = []
    for retailer in filters.selected_retailers:
        params.append(("retailer", retailer))
    params.extend(
        [
            ("start_date", filters.start_date.isoformat()),
            ("end_date", filters.end_date.isoformat()),
            ("max_files", 0 if filters.all_history else filters.max_files),
            ("all_history", str(filters.all_history).lower()),
        ]
    )
    return params
```

Important: repeated `retailer` params must be list-of-pairs style, not comma-joined. The backend reads them with `req.get_param_as_list("retailer")` in `inflation_dashboard/api/filters.py:73`.

Suggested endpoint methods/wrappers:

- `fetch_health(api_base_url)` -> `GET /api/health`, timeout `10`.
- `fetch_inventory(api_base_url)` -> `GET /api/inventory`, timeout `10`.
- `fetch_history(api_base_url, filters, product_name=None, product_retailer=None)` -> `GET /api/history`, timeout `60`.
- `fetch_retailer_averages(api_base_url, filters, aggregation)` -> `GET /api/retailer-averages`, timeout `60`.
- `fetch_movers(api_base_url, filters, scope_retailer, limit)` -> `GET /api/movers`, timeout `60`.
- `fetch_coverage(api_base_url, filters, category_limit=20)` -> `GET /api/coverage`, timeout `60`.

Failure handling pattern:

- Invalid JSON: raise/display `ApiClientError("API returned invalid JSON")`.
- Missing envelope keys: raise/display `ApiClientError("API response was not a valid envelope")`.
- Non-2xx with envelope errors: use the first error `message` if present.
- 2xx with non-empty `errors`: treat as an API error and show via `st.error`.
- Network timeout/connection error: show a clear Streamlit error and stop the affected section; do not fall back locally.

## Streamlit Sidebar and Cache Pattern

### Current sidebar flow to preserve visually

Current `main()` sequence in `streamlit_app.py:284-380`:

- Page config/title/caption at `285-288`.
- Direct inventory scan at `290`.
- Retailer multiselect at `300-308`.
- Date range input at `313-318`.
- Max files slider at `320-327`.
- `Load all files in date range` checkbox at `328`.
- Estimated files caption at `331-339`.
- Loaded dataset summary at `354-362`.
- Four tabs at `364-380`.

### Refactored API-backed sidebar flow

Plan `03-01` around this data flow:

1. `st.sidebar.text_input("Falcon API base URL", value="http://localhost:8000")` before inventory fetch.
2. `fetch_inventory(api_base_url)` inside `st.cache_data`, with API base URL as an explicit parameter/key.
3. Build `retailer_options` from `/api/inventory` `data.retailers`.
4. Keep frontend-local defaults equivalent to old `DEFAULT_RETAILERS` without importing the CSV adapter:
   - `Markets / Gurmar`
   - `ClothingStores / Vakko`
   - `HomeGoods`
   Fall back to first up to 3 retailers if none are available.
5. Build date input bounds from `/api/inventory` `data.min_date` and `data.max_date`.
6. Preserve last-60-days default bounded by min/max date.
7. Keep slider default equivalent to old `DEFAULT_MAX_FILES_PER_RETAILER` (`45`) without importing CSV adapter constants.
8. If all-history checkbox is enabled, send `all_history=true` and `max_files=0`.
9. Display API `meta.warnings`, `meta.inventory_file_count`, `meta.selected_inventory_file_count`, `meta.history_row_count`, and `meta.skipped_file_count` when available from endpoint responses.

### Cache pattern

Current cache analogs:

- `streamlit_app.py:118-120`:
  ```python
  @st.cache_data(show_spinner=False)
  def discover_csv_inventory() -> pd.DataFrame:
      return discover_csv_inventory_uncached()
  ```
- `streamlit_app.py:123-137`:
  ```python
  @st.cache_data(show_spinner="Loading selected scraped CSV files...")
  def load_price_history(...):
      ...
      return load_price_history_uncached(...)
  ```

Replace with cached HTTP wrappers:

```python
@st.cache_data(show_spinner=False, ttl=300)
def cached_fetch_inventory(api_base_url: str) -> dict[str, object]:
    return fetch_inventory(api_base_url)

@st.cache_data(show_spinner="Loading API data...", ttl=120)
def cached_fetch_endpoint(api_base_url: str, endpoint: str, params: tuple[tuple[str, object], ...]) -> dict[str, object]:
    return fetch_endpoint(api_base_url, endpoint, list(params), timeout=DATA_TIMEOUT_SECONDS)
```

Cache keys must include:

- API base URL.
- Endpoint path.
- Repeated retailer params as ordered tuples.
- `start_date`, `end_date`, `max_files`, `all_history`.
- Endpoint-specific params such as `aggregation`, `scope_retailer`, `limit`, `category_limit`, `product_name`, `product_retailer`.

## Endpoint Payload to DataFrame Pattern

### Envelope source shape

All endpoint responses must be consumed as:

```python
{
    "data": ..., 
    "meta": ..., 
    "errors": ...,
}
```

This is defined by `inflation_dashboard/api/serialization.py:80-87` and is checked in `scripts/verify_falcon_api.py:135-148`.

### Common filter/query metadata

`inflation_dashboard/api/filters.py:68-142` defines common filters and metadata:

- Repeated retailers: `req.get_param_as_list("retailer")` at `filters.py:73`.
- Date params: `start_date`, `end_date`.
- `all_history` via `parse_bool_param()` at `filters.py:56-65` and `filters.py:106`.
- `max_files`; `0` means uncapped via `_parse_max_files()` at `filters.py:175-185`.
- Warning for uncapped load: `UNCAPPED_WARNING = "all_history requested; CSV load is uncapped"` at `filters.py:19`.
- Metadata keys at `filters.py:122-133`:
  - `meta.filters.selected_retailers`
  - `meta.filters.start_date`
  - `meta.filters.end_date`
  - `meta.filters.max_files_per_retailer`
  - `meta.filters.all_history`
  - `meta.inventory_file_count`
  - `meta.selected_inventory_file_count`
  - `meta.warnings`
- Data loading metadata at `filters.py:145-162`:
  - `meta.history_row_count`
  - `meta.skipped_file_count`

### Endpoint payload mappings

#### `/api/inventory`

Source: `inflation_dashboard/api/resources.py:37-49`.

Payload:

- `data.retailers`
- `data.min_date`
- `data.max_date`
- `meta.file_count`
- `meta.inventory_file_count`

Frontend use:

- Sidebar retailer options.
- Date input bounds.
- Inventory count caption.
- Do not call `discover_csv_inventory()`.

#### `/api/history` without product selectors

Source: `inflation_dashboard/api/resources.py:52-74`.

Payload when `product_name` is absent:

- `data.history`: records with `date`, `retailer`, `product_id`, `product_name`, `category`, `price`, `source_file`.
- May add warning `history response may be large` when all-history or >5000 rows.

Frontend use:

- This is the only current API source for product options.
- Keep bounded/cached with current sidebar filters.
- Convert `data.history` to a DataFrame to derive product/retailer selectbox options only.

#### `/api/history` with product selectors

Payload when `product_name` is present:

- `data.history`: records from `PRODUCT_HISTORY_COLUMNS` = `date`, `price`, `category`, `source_file`.
- `data.summary`: `latest_price`, `cheapest_price`, `cheapest_date`, `change_since_first_pct`.
- `meta.product_name`, `meta.product_retailer`.

Frontend conversion:

```python
records = payload["data"].get("history", [])
product_history = pd.DataFrame(records)
if "date" in product_history:
    product_history["date"] = pd.to_datetime(product_history["date"])
summary = payload["data"].get("summary", {})
```

Landmine: `summary["cheapest_date"]` is a string/null after JSON serialization, not necessarily a pandas timestamp. Replace current `.strftime()` assumption from `streamlit_app.py:195`.

#### `/api/retailer-averages`

Source: `inflation_dashboard/api/resources.py:77-97`.

Payload:

- `data.records`
- `data.retailer_averages` alias
- `meta.aggregation`
- `meta.skipped_file_count`

Frontend conversion:

```python
records = payload["data"].get("records") or payload["data"].get("retailer_averages", [])
averages = pd.DataFrame(records)
if "date" in averages:
    averages["date"] = pd.to_datetime(averages["date"])
```

#### `/api/movers`

Source: `inflation_dashboard/api/resources.py:100-136`.

Payload:

- `data.biggest_drops`
- `data.biggest_gains`
- `meta.scope_retailer`
- `meta.limit`
- `meta.eligible_product_count`
- `meta.skipped_file_count`

Frontend conversion:

```python
biggest_drops = pd.DataFrame(payload["data"].get("biggest_drops", []))
biggest_gains = pd.DataFrame(payload["data"].get("biggest_gains", []))
```

Before selecting chart-spec/table columns, guard for empty DataFrames and missing columns.

#### `/api/coverage`

Source: `inflation_dashboard/api/resources.py:139-159`.

Payload:

- `data.summary`
- `data.coverage_over_time`
- `data.category_coverage`
- `data.skipped_files`
- `meta.category_limit`
- `meta.skipped_file_count`

Frontend conversion:

```python
summary = payload["data"].get("summary", {})
coverage = pd.DataFrame(payload["data"].get("coverage_over_time", []))
categories = pd.DataFrame(payload["data"].get("category_coverage", []))
skipped = pd.DataFrame(payload["data"].get("skipped_files", []))
```

## Tab Renderer Refactor Patterns

### Product explorer

Current source: `streamlit_app.py:169-200`.

Current local flow:

- Retailer options from `history["retailer"].unique()` at `171`.
- Product options from local retailer slice at `179-180`.
- Local `get_product_history()` at `188`.
- Local `summarize_product_history()` at `189`.
- Metric cards at `191-196`.
- Product chart/table at `198-200`.

API-backed flow:

1. Use cached bounded `/api/history` without `product_name` to get product option records.
2. Build retailer options from sidebar-selected retailers and/or returned `history` records.
3. Preserve `autocorrect_selectbox()` for retailer and product controls.
4. Fetch product-specific `/api/history` with common filters plus:
   - `product_retailer=<selected_retailer>`
   - `product_name=<selected_product>`
5. Render metrics from `data.summary`.
6. Render chart/table from `data.history` using `product_price_chart_spec()`.
7. If `data.history` is empty on HTTP 200, show tab-specific `st.info` rather than a global stop.
8. If the endpoint returns HTTP 400/envelope errors, show `st.error` and stop only this tab where practical.

### Retailer averages

Current source: `streamlit_app.py:204-223`.

Current local flow:

- Retailer options from local `history` at `206`.
- `autocorrect_multiselect()` at `207-213`.
- `st.radio("Aggregation", ["Average", "Median"], horizontal=True)` at `214`.
- Local `calculate_retailer_average_trends()` at `216`.

API-backed flow:

1. Retailer options should come from sidebar/inventory/API metadata, not local history scan.
2. Preserve `autocorrect_multiselect()` and aggregation radio.
3. Fetch `/api/retailer-averages` with common filters plus `aggregation`.
4. Render `data.records` using `retailer_average_chart_spec(aggregation)`.
5. Empty `records` -> `st.info("Select at least one retailer." or endpoint-specific empty message)`.

### Price movers

Current source: `streamlit_app.py:227-255`.

Current local flow:

- Scope options from `history` plus `"All retailers"` at `229`.
- `autocorrect_selectbox()` at `230`.
- Rows slider at `231`.
- Local `calculate_price_movers()` at `233`.
- Two-column tables at `240-255`.

API-backed flow:

1. Scope options should be `"All retailers"` plus selected/current retailers from sidebar or `meta.filters.selected_retailers`.
2. Preserve rows slider range `5..30` and default `10`.
3. Fetch `/api/movers` with common filters plus:
   - `scope_retailer`
   - `limit`
4. Render `data.biggest_drops` and `data.biggest_gains` using `BIGGEST_DROPS_COLUMNS` and `BIGGEST_GAINS_COLUMNS`.
5. If both lists are empty, preserve the existing empty-state intent: `Not enough repeated product observations for this selection.`

### Coverage overview

Current source: `streamlit_app.py:258-280`.

Current local flow:

- Local `calculate_coverage_summary()` at `260`.
- Metrics at `262-266`.
- Local `calculate_coverage_over_time()` at `270`.
- Local `calculate_category_coverage()` at `274`.
- Skipped-file expander at `277-280`.

API-backed flow:

1. Fetch `/api/coverage` with common filters plus `category_limit=20`.
2. Render metric cards from `data.summary`.
3. Convert `data.coverage_over_time` and render with `coverage_area_chart_spec()`.
4. Convert `data.category_coverage` and render with `category_coverage_bar_chart_spec()`.
5. Convert `data.skipped_files` and preserve skipped-file expander using `SKIPPED_DIAGNOSTICS_COLUMNS`.
6. Show `meta.warnings`/skipped diagnostics visibly; non-fatal skipped files should not crash the dashboard.

## Verification Patterns

### Existing backend contract verifier

`scripts/verify_falcon_api.py` is the closest analog for source-contract checks.

Relevant patterns:

- `scripts/verify_falcon_api.py:23` defines `ENVELOPE_KEYS = {"data", "meta", "errors"}`.
- `scripts/verify_falcon_api.py:45-72` performs source import boundary checks.
- `scripts/verify_falcon_api.py:75-97` checks route and response-key source contracts.
- `scripts/verify_falcon_api.py:135-148` validates envelope shape.
- `scripts/verify_falcon_api.py:173-206` exercises endpoints through Falcon `TestClient` if Falcon is installed.

Known current verifier behavior from research:

```text
PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource
PASS source contracts: endpoint routes and stable response keys
Falcon is missing. Install project dependency metadata with the user's uv workflow (for example: uv sync or uv pip install -r requirements.txt), then rerun python scripts/verify_falcon_api.py.
EXIT_CODE=1
```

Treat missing Falcon as a dependency/runtime blocker, not as evidence the source contract failed.

### Frontend source assertion pattern

Add or run a focused source verifier after Phase 03 edits. It should fail if `streamlit_app.py` contains any forbidden direct data boundary:

```python
FORBIDDEN_TOKENS = [
    "inflation_dashboard.adapters.csv_price_repository",
    "discover_csv_inventory_uncached",
    "load_price_history_uncached",
    "from inflation_dashboard.application.use_cases import",
    "calculate_retailer_average_trends(",
    "calculate_price_movers(",
    "calculate_coverage_summary(",
    "calculate_coverage_over_time(",
    "calculate_category_coverage(",
    "get_product_history(",
    "summarize_product_history(",
]
```

Allow:

- `from inflation_dashboard.application.chart_specs import ...`
- UI helpers and Plotly rendering.

Also assert source contains/keeps:

- Visible API base URL control with default `http://localhost:8000`.
- `autocorrect_selectbox(` in product/movers flows.
- `autocorrect_multiselect(` in sidebar/retailer average flows.
- Four tab labels.
- Endpoint strings or client methods for `/api/inventory`, `/api/history`, `/api/retailer-averages`, `/api/movers`, `/api/coverage`.

### API client unit/source assertions

If a client module is introduced, test without a live server by monkeypatching the selected HTTP call:

- Multiple selected retailers produce repeated params:
  ```python
  [("retailer", "Markets / Gurmar"), ("retailer", "HomeGoods")]
  ```
  not `{"retailer": "Markets / Gurmar,HomeGoods"}`.
- Good envelope is accepted.
- Missing `data`, `meta`, or `errors` is rejected.
- Non-empty `errors` is converted into displayable `ApiClientError`.
- Non-2xx response with an error envelope is converted into displayable `ApiClientError`.
- Timeout constants are explicit and endpoint-appropriate.

### Minimal runtime checks

After edits, run at least:

```bash
python -m py_compile streamlit_app.py
python scripts/verify_falcon_api.py
```

If a new client module or verifier is created, compile/run it too. Use the project `uv` workflow if dependencies need installation; do not fabricate endpoint success when Falcon or Streamlit dependencies are missing.

## Landmines for Planner

- **Roadmap split is expected:** plan as `03-01` API client/sidebar/filter flow and `03-02` four-tab refactor.
- **No local fallback:** if API is down, times out, returns invalid JSON, or returns an invalid/error envelope, Streamlit must show an error and stop affected rendering. It must not call CSV adapters or use cases directly.
- **Forbidden Streamlit imports after phase:** `inflation_dashboard.adapters.csv_price_repository` and `inflation_dashboard.application.use_cases` must be gone from `streamlit_app.py`.
- **Chart specs may remain:** `inflation_dashboard.application.chart_specs` is presentation metadata and is safe to import.
- **Repeated retailer params:** backend expects repeated `retailer` query params via `req.get_param_as_list("retailer")`; do not comma-join.
- **Product options gap:** there is no `/api/products` endpoint. `/api/history` without `product_name` is the only current API source for product options. Keep this request bounded and cached.
- **All tabs compute eagerly:** Streamlit tabs execute their bodies even when hidden. Multiple endpoint calls can happen on every rerun; use cache, filters, and spinners carefully.
- **All-history is expensive:** `all_history=true`/`max_files=0` is uncapped and should surface API warnings from `meta.warnings`.
- **Date values are strings after API serialization:** do not call `.strftime()` on `summary["cheapest_date"]` unless converted.
- **Empty API lists become column-less DataFrames:** guard before slicing with chart/table columns.
- **Sidebar loaded summary source changes:** current summary comes from local `history`; replace with endpoint `meta` and/or coverage summary. Do not recompute from local CSV.
- **Dependency state is inconsistent:** `requirements.txt` includes `requests==2.32.5` and `falcon`; `pyproject.toml` may not include `requests` and has a known Python-version inconsistency. Avoid broad dependency cleanup unless it blocks verification.
- **Existing unrelated uncommitted files are present:** do not touch unrelated `.planning/config.json`, notebooks, `pyproject.toml`, `uv.lock`, or data CSV changes unless explicitly required by the plan/executor.
- **Do not modify backend contract unless blocked:** Phase 03 consumes Phase 2 Falcon endpoints as-is; new endpoints are out of scope.
- **No repo-local Hermes instructions found:** no `HERMES.md` or `.hermes/HERMES.md` was present.

## PATTERN MAPPING COMPLETE

Pattern mapping for Phase 03 is complete. The planner should use this artifact to write precise tasks that first build a strict API client/sidebar flow, then refactor all four Streamlit tabs to consume Falcon endpoint payloads while preserving existing UI behavior and verification guardrails.
