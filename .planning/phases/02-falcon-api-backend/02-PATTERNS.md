# Phase 02 Pattern Map: Falcon API Backend

**Phase:** 02 - falcon-api-backend  
**Role:** gsd-pattern-mapper  
**Generated:** 2026-07-16  
**Purpose:** Give the planner/executor concrete codebase patterns to reuse while adding a thin Falcon API adapter around the Phase 1 dashboard core.

## Scope and target files

Phase 02 should create a dedicated API adapter package and avoid changing Streamlit/domain code unless a true blocker is discovered.

| Target file | Role | Data flow responsibility | Closest existing analog | Planner guidance |
|---|---|---|---|---|
| `inflation_dashboard/api/__init__.py` | Package boundary | Expose API package without side effects | Existing empty package markers: `inflation_dashboard/application/__init__.py`, `inflation_dashboard/adapters/__init__.py` | Keep side-effect free. Do not discover inventory or import Streamlit here. |
| `inflation_dashboard/api/falcon_app.py` | Falcon app factory / route registration | `create_app()` builds `falcon.App`, registers `/api/*` resources | `streamlit_app.py:284-380` is the current composition root, but it is Streamlit-specific | Import Falcon and API resources only. Health route must not scan CSVs. |
| `inflation_dashboard/api/resources.py` | HTTP resource layer | Parse request, call shared filters/loading helpers, call application use cases, set `resp.media`/status | Streamlit render functions call the same use cases: `render_product_explorer`, `render_retailer_average`, `render_price_movers`, `render_overview` | Keep resources thin; no CSV parsing, price normalization, Plotly, or Streamlit logic. |
| `inflation_dashboard/api/filters.py` | Query parsing, defaulting, validation, bounded loading orchestration | Repeated `retailer`, `start_date`, `end_date`, `max_files`, `all_history`; inventory-first then load | `streamlit_app.py:290-346` sidebar/filter/load sequence; `csv_price_repository.load_price_history()` | Use `req.get_param_as_list("retailer")` for repeated params. Reject invalid filters with 400 envelopes. |
| `inflation_dashboard/api/serialization.py` | JSON-native conversion and response envelopes | Convert pandas/numpy/date values and DataFrames to JSON-safe dict/list payloads | Chart/table column constants in `chart_specs.py`; DataFrame outputs from `use_cases.py` | Do not rely on raw `DataFrame.to_dict("records")` alone; normalize `Timestamp`, `NaN`, `pd.NA`, numpy scalars. |
| `pyproject.toml` and/or `requirements.txt` | Dependency metadata | Declare Falcon minimally if API imports it | Current manifests are inconsistent | Update only enough for Falcon/API verification; avoid broad dependency churn. |

Do **not** plan Phase 02 changes to:

- `streamlit_app.py` except for a documented hard blocker. Phase 03 owns frontend HTTP refactor.
- `inflation_dashboard/domain/*`, `inflation_dashboard/application/*`, or `inflation_dashboard/adapters/csv_price_repository.py` unless a reusable core bug blocks the API.
- Scraper/data directories under `Codes/`, `Datas/`, or `Inflations/`.

## Existing data-flow pattern to preserve

The Phase 1 flow is already clean enough for an API adapter:

```text
CSV files under Datas/
  -> inflation_dashboard.adapters.csv_price_repository.discover_csv_inventory()
  -> inventory filters/defaults
  -> inflation_dashboard.adapters.csv_price_repository.load_price_history(...)
  -> pandas history/skipped DataFrames
  -> inflation_dashboard.application.use_cases.* calculations
  -> UI/API presentation layer serialization
```

Phase 02 should add only the final Falcon presentation layer:

```text
Falcon request
  -> filters.py parses/validates query params against cached inventory
  -> resources.py calls csv adapter + application use cases
  -> serialization.py converts DataFrames/mappings to JSON-native values
  -> Falcon resp.media = {"data": ..., "meta": ..., "errors": ...}
```

## Concrete existing patterns and excerpts

### 1. CSV inventory discovery and bounded loading

**Source:** `inflation_dashboard/adapters/csv_price_repository.py`

Key constants to reuse when filters are omitted:

```python
DEFAULT_RETAILERS = (
    "Markets / Gurmar",
    "ClothingStores / Vakko",
    "HomeGoods",
)
DEFAULT_MAX_FILES_PER_RETAILER = 45
```

Inventory is cheap relative to history loading and returns stable columns:

```python
def discover_csv_inventory(raw_data_root: Path = RAW_DATA_ROOT) -> pd.DataFrame:
    rows = []
    for csv_path in raw_data_root.rglob("*.csv"):
        retailer = detect_retailer(csv_path)
        date_value = parse_date_from_name(csv_path.name)
        if retailer not in SUPPORTED_RETAILERS or pd.isna(date_value):
            continue
        rows.append({"path": str(csv_path), "retailer": retailer, "date": date_value, "size_mb": ...})
    return pd.DataFrame(rows).sort_values(["retailer", "date"])
```

History loading already enforces the selected retailer/date/window and cap. Reuse it instead of reimplementing file scans:

```python
selected_files = inventory[
    inventory["retailer"].isin(selected_retailers)
    & (inventory["date"] >= pd.to_datetime(start_date))
    & (inventory["date"] <= pd.to_datetime(end_date))
].copy()

if max_files_per_retailer > 0:
    selected_files = (
        selected_files.sort_values(["retailer", "date"], ascending=[True, False])
        .groupby("retailer", group_keys=False)
        .head(max_files_per_retailer)
        .sort_values(["retailer", "date"])
    )
```

**API pattern:** `filters.py` should own a cached `get_inventory()` wrapper and pass the same inventory into `load_price_history(...)` so endpoints preserve inventory-first/load-second behavior.

Recommended API helper shape:

```python
@lru_cache(maxsize=1)
def get_inventory() -> pd.DataFrame:
    return discover_csv_inventory()

# Optional: copy before downstream mutation if a helper may mutate it.
inventory = get_inventory()
history, skipped = load_price_history(
    tuple(selected_retailers),
    start_date,
    end_date,
    effective_max_files,
    inventory=inventory,
)
```

### 2. Streamlit filter/default behavior to mirror, not import

**Source:** `streamlit_app.py`

Default selected retailers fall back to configured defaults, then first available retailers:

```python
retailer_options = sorted(inventory["retailer"].unique())
default_retailers = [retailer for retailer in DEFAULT_RETAILERS if retailer in retailer_options]
if not default_retailers:
    default_retailers = retailer_options[: min(3, len(retailer_options))]
```

Date window currently defaults to the last 60 days of inventory:

```python
min_date = inventory["date"].min().date()
max_date = inventory["date"].max().date()
default_start = max(min_date, (pd.Timestamp(max_date) - pd.Timedelta(days=60)).date())
```

All-history is explicit by setting an effective cap of zero:

```python
load_all_history = st.sidebar.checkbox("Load all files in date range", value=False)
effective_limit = 0 if load_all_history else max_files_per_retailer
```

**API pattern:** Copy the behavior, not the module. API modules must not import `streamlit_app.py` because it imports Streamlit/Plotly and performs UI work. Planner should explicitly choose whether API defaults use full inventory min/max or the Streamlit 60-day default; if matching current UI, encode the 60-day default in `filters.py`.

### 3. Application use-case functions are the API business logic

**Source:** `inflation_dashboard/application/use_cases.py`

Inventory endpoint should call:

```python
def list_inventory_filters(inventory: pd.DataFrame) -> dict[str, object]:
    if inventory.empty:
        return {"retailers": [], "min_date": None, "max_date": None, "file_count": 0}
    return {
        "retailers": sorted(inventory["retailer"].dropna().unique().tolist()),
        "min_date": inventory["date"].min(),
        "max_date": inventory["date"].max(),
        "file_count": len(inventory),
    }
```

History endpoint can optionally support product selectors using:

```python
def get_product_history(history: pd.DataFrame, retailer: str, product_name: str) -> pd.DataFrame:
    product_history = history[
        history["retailer"].eq(retailer) & history["product_name"].eq(product_name)
    ].copy()
    return product_history.sort_values("date")
```

and summary:

```python
def summarize_product_history(product_history: pd.DataFrame) -> dict[str, object]:
    if product_history.empty:
        return {"latest_price": None, "cheapest_price": None, "cheapest_date": None, "change_since_first_pct": 0.0}
    ...
```

Retailer averages endpoint should call:

```python
calculate_retailer_average_trends(history, selected_retailers, aggregation)
```

Only `"Average"` and `"Median"` should be accepted at the API boundary; reject other values with HTTP 400.

Movers endpoint should call:

```python
calculate_price_movers(history, selected_retailer, mover_count)
```

The current UI uses `"All retailers"` plus a slider range of `5..30`; match or explicitly document a different API range.

Coverage endpoint should call:

```python
calculate_coverage_summary(history, skipped)
calculate_coverage_over_time(history)
calculate_category_coverage(history, limit=category_limit)
```

### 4. Stable payload columns already exist

**Source:** `inflation_dashboard/application/chart_specs.py`

Reuse these constants when selecting/ordering records for API output:

```python
PRODUCT_HISTORY_COLUMNS = ["date", "price", "category", "source_file"]
RETAILER_AVERAGE_COLUMNS = ["date", "retailer", "price"]
BIGGEST_DROPS_COLUMNS = ["retailer", "product_name", "latest_price", "max_price", "savings_vs_peak", "drop_from_peak_pct", "last_seen"]
BIGGEST_GAINS_COLUMNS = ["retailer", "product_name", "first_price", "latest_price", "change_since_first_pct", "first_seen", "last_seen"]
SKIPPED_DIAGNOSTICS_COLUMNS = ["file", "reason"]
COVERAGE_OVER_TIME_COLUMNS = ["date", "retailer", "tracked_products"]
CATEGORY_COVERAGE_COLUMNS = ["retailer", "category", "products"]
```

**API pattern:** `serialization.records_from_frame(frame, columns=...)` should select existing columns in the declared order and ignore missing optional columns rather than crashing on empty frames that may not include all columns.

### 5. Domain layer owns CSV normalization; API must not duplicate it

**Source:** `inflation_dashboard/domain/prices.py`

The normalized history columns are fixed here:

```python
HISTORY_COLUMNS = ["date", "retailer", "product_id", "product_name", "category", "price", "source_file"]
```

Price parsing and product normalization already happen before use-case/API layers:

```python
prices = frame[price_column].map(coerce_price)
product_data = pd.DataFrame({
    "date": date_value,
    "retailer": retailer,
    "product_id": product_id,
    "product_name": product_name,
    "category": category,
    "price": prices,
    "source_file": source_file,
})
product_data = product_data.dropna(subset=["product_id", "product_name", "price"])
return product_data[HISTORY_COLUMNS]
```

**API pattern:** Never parse raw CSVs or coerce prices in Falcon resources. Treat `history` as the canonical DataFrame and serialize it.

## Recommended API endpoint responsibilities

### `/api/health`

- Resource: `HealthResource` in `resources.py`.
- Must be lightweight: no inventory discovery and no CSV loading.
- Suggested response:

```json
{"data": {"status": "ok"}, "meta": {"service": "inflation-dashboard-api"}, "errors": []}
```

### `/api/inventory`

- Resource calls cached `get_inventory()` and `list_inventory_filters(inventory)`.
- Returns available retailers and ISO date bounds.
- Include `meta.file_count`/`inventory_file_count`.
- Empty inventory is a valid 200 with empty data and counts; not a 500.

### `/api/history`

- Common load filters: repeated `retailer`, `start_date`, `end_date`, `max_files`, `all_history`.
- Planner should explicitly decide product selector contract:
  - Recommended: support optional `product_name` and `product_retailer`/single `retailer` selector.
  - If both product selectors are present, return `{history: [...], summary: {...}}` using `get_product_history()` and `summarize_product_history()`.
  - If omitted, return bounded normalized history records and warn in metadata if row count is large or all-history was requested.
- Use `PRODUCT_HISTORY_COLUMNS` only for product-specific history; use `HISTORY_COLUMNS`/explicit API columns if returning all loaded history.

### `/api/retailer-averages`

- Parse common load filters plus `aggregation`.
- Validate `aggregation in {"Average", "Median"}`; otherwise HTTP 400.
- Call `calculate_retailer_average_trends(history, selected_retailers, aggregation)`.
- Serialize `RETAILER_AVERAGE_COLUMNS`.

### `/api/movers`

- Parse common load filters plus `scope_retailer` and `limit`/`mover_count`.
- Default scope: `"All retailers"`.
- Default count: `10`; recommended bounds: `5..30` to match current UI.
- Call `calculate_price_movers(history, selected_retailer, mover_count)`.
- Serialize `BIGGEST_DROPS_COLUMNS` and `BIGGEST_GAINS_COLUMNS`; include `eligible_product_count`/`stats_count` from `stats` in metadata.
- No repeat observations should be HTTP 200 with empty lists.

### `/api/coverage`

- Parse common load filters plus optional `category_limit` default `20`.
- Call coverage summary, coverage over time, and category coverage use cases.
- Include skipped diagnostics in both `data.skipped_files` and `meta.skipped_file_count`.
- Use `COVERAGE_OVER_TIME_COLUMNS`, `CATEGORY_COVERAGE_COLUMNS`, and `SKIPPED_DIAGNOSTICS_COLUMNS`.

## Import and dependency boundaries

### Allowed directions

```text
inflation_dashboard/api/*
  may import: falcon, functools, datetime, pandas/numpy for serialization checks,
              inflation_dashboard.adapters.csv_price_repository,
              inflation_dashboard.application.use_cases,
              inflation_dashboard.application.chart_specs,
              inflation_dashboard.domain.prices constants if needed

inflation_dashboard/application/*
  may import: pandas and domain-independent helpers
  must not import: falcon, streamlit

inflation_dashboard/domain/*
  may import: pandas/re/domain utilities
  must not import: falcon, streamlit

inflation_dashboard/adapters/csv_price_repository.py
  may import: pandas/pathlib/domain normalizers
  must not import: falcon, streamlit
```

### Import style conventions

Existing package code uses:

```python
from __future__ import annotations

import pandas as pd

from inflation_dashboard.application.use_cases import (...)
```

Follow that style in new API modules:

- Put `from __future__ import annotations` first.
- Prefer absolute imports from `inflation_dashboard...`.
- Keep Falcon imports isolated to `inflation_dashboard/api/*`.
- Do not import `streamlit_app.py` into API code.

## Filter parsing conventions

Implement one shared parsed-filter object or dict in `filters.py` so resource classes do not duplicate query parsing.

Recommended behavior:

1. `inventory = get_inventory()` with `@lru_cache(maxsize=1)`.
2. `available = list_inventory_filters(inventory)["retailers"]`.
3. Read repeated retailers with Falcon `req.get_param_as_list("retailer")`; do not use plain `get_param()` for this.
4. If omitted, use `DEFAULT_RETAILERS` intersected with available retailers; if empty, fallback to first `min(3, len(available))` retailers.
5. Reject unknown retailers with HTTP 400 envelope.
6. Parse `start_date`/`end_date` as ISO `%Y-%m-%d`; reject bad formats.
7. If dates omitted, use either inventory min/max or the 60-day Streamlit default; the plan must specify which.
8. Reject `start_date > end_date` with HTTP 400 envelope.
9. Parse `all_history` bool and `max_files` int.
10. Effective max files:
    - `0` if `all_history=true`.
    - Provided `max_files` if present.
    - `DEFAULT_MAX_FILES_PER_RETAILER` otherwise.
11. Reject negative `max_files`.
12. Include selected filters and estimated load counts in `meta`.

Recommended metadata keys:

```python
{
    "filters": {
        "selected_retailers": [...],
        "start_date": "YYYY-MM-DD",
        "end_date": "YYYY-MM-DD",
        "max_files_per_retailer": 45,
        "all_history": False,
    },
    "inventory_file_count": 748,
    "selected_inventory_file_count": 3,
    "history_row_count": 123,
    "skipped_file_count": 0,
    "warnings": [],
}
```

Add `"all_history requested; CSV load is uncapped"` or similar when the cap is disabled.

## Serialization conventions

Phase 1 deliberately returns pandas-native values; Phase 2 must convert them before Falcon assigns `resp.media`.

Recommended helpers in `serialization.py`:

```python
def envelope(data, meta=None, errors=None) -> dict[str, object]:
    return {"data": json_safe(data), "meta": json_safe(meta or {}), "errors": json_safe(errors or [])}


def error_envelope(code: str, message: str, *, meta=None) -> dict[str, object]:
    return envelope(None, meta=meta or {}, errors=[{"code": code, "message": message}])
```

`to_json_value(value)` should handle:

- `pd.Timestamp`, `datetime.date`, `datetime.datetime` -> ISO date/datetime string.
- `pd.NaT`, `pd.NA`, `numpy.nan`, float `NaN` -> `None`.
- numpy scalar integers/floats/bools -> `.item()` then normal JSON value.
- `dict`, `list`, `tuple` recursively.
- native `int`, `float`, `str`, `bool`, `None` unchanged.

`records_from_frame(frame, columns=None)` should:

- Return `[]` for `None`/empty frames.
- Select only columns that exist.
- Preserve the requested order.
- Convert each cell through `to_json_value`.

Pitfall to encode in PLAN.md: `frame.to_dict("records")` by itself can leak `Timestamp`, `NaN`, `NaT`, and numpy scalars into `resp.media`; always run the explicit conversion helper.

## Error and empty-state patterns

### HTTP 400 invalid filters

Return HTTP 400 with the same envelope shape:

```json
{
  "data": null,
  "meta": {"filters": {"retailer": ["Unknown"]}},
  "errors": [{"code": "invalid_filter", "message": "Unknown retailer: Unknown"}]
}
```

Expected 400 cases:

- Unknown `retailer` filter.
- Bad `start_date`/`end_date` format.
- `start_date > end_date`.
- Negative `max_files`.
- Unsupported `aggregation`.
- Invalid mover/category limits outside chosen bounds.

### HTTP 200 valid empty results

Return HTTP 200 with stable empty data shapes and diagnostic `meta` for:

- Inventory exists but selected date window has no files.
- CSV files load but history has no usable rows.
- Product history selector matches no rows.
- Movers have no products with at least two observations.

Skipped-file diagnostics are normal. Treat them as non-fatal unless all selected files fail or no usable data remains specifically due to failures; the plan should define whether that case is 500 or a 200/diagnostic envelope with `errors` populated.

## Lightweight verification patterns

There is no canonical test suite yet, so PLAN.md should include focused smoke verification without a long-running server.

Recommended verification script/tasks:

1. Ensure Falcon is installed or report dependency blocker clearly; prefer the project/user `uv` workflow over ad hoc `pip`.
2. Import `inflation_dashboard.api.falcon_app.create_app`.
3. Use `falcon.testing.TestClient(create_app())`.
4. Exercise:
   - `GET /api/health`
   - `GET /api/inventory`
   - `GET /api/retailer-averages?retailer=Markets%20/%20Gurmar&max_files=1`
   - `GET /api/movers?retailer=Markets%20/%20Gurmar&max_files=1&limit=5`
   - `GET /api/coverage?retailer=Markets%20/%20Gurmar&max_files=1`
   - invalid retailer returns 400 with `errors`.
5. Assert every response contains exactly the stable top-level contract keys: `data`, `meta`, `errors`.
6. Assert date fields are strings/null, not pandas `Timestamp`.
7. Assert no `NaN`/`Infinity`-like values appear in JSON payloads.
8. Source scan boundaries:
   - API modules may import `falcon` but not `streamlit`.
   - Domain/application/CSV adapter modules must not import `falcon` or `streamlit`.

## Dependency metadata pattern

Current files observed:

```toml
# pyproject.toml
[project]
name = "inflationstudymirror"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = []
```

```text
# requirements.txt excerpt
certifi==2026.1.4
...
requests==2.32.5
...
camoufox
beautifulsoup4
seleniumbase
cloudscraper
curl-cffi
```

Research found local `falcon` missing while `pandas`, `streamlit`, and `plotly` were installed. The planner should require the implementation to declare Falcon if code imports it, but should avoid a broad manifest cleanup in this phase unless necessary for verification. Mention the existing Python/dependency inconsistency as a risk, not as a Phase 02 overhaul mandate.

## PLAN.md pitfalls to encode

- **Do not import Streamlit from API code.** `streamlit_app.py` imports Streamlit/Plotly and is a UI composition root, not a reusable API service.
- **Do not duplicate CSV/domain logic.** Reuse `discover_csv_inventory()`, `load_price_history()`, and application use cases.
- **Keep `/api/health` lightweight.** It must not discover inventory or read CSVs.
- **Use repeated query parsing correctly.** Falcon `get_param()` is insufficient for `?retailer=A&retailer=B`; use `get_param_as_list("retailer")`.
- **Require explicit all-history.** Default to bounded `DEFAULT_MAX_FILES_PER_RETAILER`; only `max_files=0` or `all_history=true` should disable caps.
- **Convert pandas/numpy/date values explicitly.** Raw `DataFrame.to_dict("records")` is not enough for stable JSON.
- **Cache carefully.** Inventory cache is safe and useful. If caching history, key by primitive tuples and avoid mutating cached DataFrames; copy or treat as read-only.
- **Define `/api/history` product behavior.** Existing `get_product_history()` needs both retailer and product name, so the plan must specify optional selectors or an all-loaded-history payload contract.
- **Handle skipped diagnostics visibly.** Include skipped file counts and rows in coverage/data metadata.
- **Use bounded smoke requests.** Test with `Markets / Gurmar` and `max_files=1` to avoid loading hundreds of CSVs.
- **Do not launch a long-running server for verification.** Use Falcon `TestClient` or direct resource invocation.

## Planner-ready file responsibility checklist

Before finalizing Phase 02 PLAN.md, ensure tasks assign these responsibilities explicitly:

- `inflation_dashboard/api/falcon_app.py`
  - app factory
  - route registration for all six endpoints
  - no inventory scans at import/app creation except resource construction
- `inflation_dashboard/api/resources.py`
  - one resource per endpoint or grouped endpoint resources
  - response status/envelope setting
  - application use-case calls only after filters/load are resolved
- `inflation_dashboard/api/filters.py`
  - cached inventory helper
  - repeated retailer parsing/defaulting
  - ISO date parsing/defaulting
  - max file/all-history parsing
  - common metadata construction
  - invalid filter exception/result shape
- `inflation_dashboard/api/serialization.py`
  - `envelope`/`error_envelope`
  - JSON-safe scalar conversion
  - DataFrame-to-record conversion with column selection
- dependency metadata
  - add Falcon minimally where the project expects runtime dependencies
- verification
  - Falcon `TestClient` smoke checks
  - invalid-filter 400 check
  - JSON-native serialization check
  - import-boundary scan
