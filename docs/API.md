<!-- generated-by: gsd-doc-writer -->
# API Reference

This document covers the complete Falcon API implemented under `inflation_dashboard/api/`. The API is consumed by the Streamlit frontend through `inflation_dashboard/frontend/api_client.py`.

## App Factory

`inflation_dashboard.api.falcon_app.create_app()` creates a `falcon.App`, registers all API resources, and returns the WSGI application object.

```python
from inflation_dashboard.api.falcon_app import create_app

app = create_app()
```

The app factory registers these six routes:

| Method | Route | Resource | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | `HealthResource` | Lightweight service status. Does not load inventory or history data. |
| `GET` | `/api/inventory` | `InventoryResource` | Available retailer/date inventory discovered from CSV files. |
| `GET` | `/api/history` | `HistoryResource` | Filtered normalized price history, or one product's history and summary. |
| `GET` | `/api/retailer-averages` | `RetailerAveragesResource` | Average or median price trend records by date and retailer. |
| `GET` | `/api/movers` | `MoversResource` | Biggest price drops and gains for products with repeated observations. |
| `GET` | `/api/coverage` | `CoverageResource` | Dataset coverage summary, coverage over time, category coverage, and skipped-file diagnostics. |

## Response Envelope

All route handlers return the same top-level JSON object shape via `inflation_dashboard.api.serialization.envelope()` or `error_envelope()`:

```json
{
  "data": {},
  "meta": {},
  "errors": []
}
```

- `data`: endpoint payload, or `null` for validation errors.
- `meta`: filter metadata, counts, warnings, and endpoint-specific metadata.
- `errors`: an array. Successful responses use an empty array. Validation errors include objects with `code` and `message`.

The serializer converts pandas timestamps, Python dates/datetimes, numpy scalars, NaN values, mappings, tuples, and lists into JSON-native values before Falcon writes the response.

## Common Query Filters

The data endpoints call `parse_common_filters(req)` unless noted otherwise. These filters apply to:

- `/api/history`
- `/api/retailer-averages`
- `/api/movers`
- `/api/coverage`

They do not apply to `/api/health` or `/api/inventory`.

| Parameter | Type | Default / behavior | Validation |
|---|---|---|---|
| `retailer` | repeatable string | If omitted, selects existing values from `DEFAULT_RETAILERS`. If none exist, selects the first available retailers, up to three. | Unknown retailers return `400 Bad Request` with `code: "invalid_filter"`. |
| `start_date` | ISO date string | Defaults to the latest 60-day window bounded by discovered inventory min/max dates. | Invalid ISO dates return `400 Bad Request`. A start date after `end_date` returns `400 Bad Request`. |
| `end_date` | ISO date string | Defaults to inventory `max_date` when available. | Invalid ISO dates return `400 Bad Request`. |
| `max_files` | integer | Defaults to `DEFAULT_MAX_FILES_PER_RETAILER` (`45`). Limits newest files loaded per selected retailer. `0` means uncapped. | Negative or non-integer values return `400 Bad Request`. |
| `all_history` | boolean | Defaults to `false`. Truthy values force uncapped loading (`max_files=0`). | Boolean strings accepted. Other values return `400 Bad Request`. |

Common success metadata includes:

- `filters.selected_retailers`
- `filters.start_date`
- `filters.end_date`
- `filters.max_files_per_retailer`
- `filters.all_history`
- `inventory_file_count`
- `selected_inventory_file_count`
- `history_row_count` for endpoints that load history
- `skipped_file_count` for endpoints that load history
- `warnings`, including `all_history requested; CSV load is uncapped` when uncapped loading is requested

## Endpoints

### `GET /api/health`

Lightweight status check.

#### Query parameters

None.

#### Success response

```json
{
  "data": { "status": "ok" },
  "meta": { "service": "inflation-dashboard-api" },
  "errors": []
}
```

### `GET /api/inventory`

Returns filter discovery metadata from cached CSV inventory.

#### Query parameters

None.

#### Success data

| Field | Type | Description |
|---|---|---|
| `retailers` | array of strings | Sorted retailer labels available in inventory. Empty when inventory is empty. |
| `min_date` | string or null | Earliest discovered inventory date. |
| `max_date` | string or null | Latest discovered inventory date. |

#### Success metadata

| Field | Type | Description |
|---|---|---|
| `file_count` | integer | Number of inventory rows/files discovered. |
| `inventory_file_count` | integer | Same count, exposed with the common metadata name. |

### `GET /api/history`

Returns filtered normalized price history. When `product_name` is provided, returns only one product's time series and a summary.

#### Query parameters

Includes all common filters plus:

| Parameter | Type | Default / behavior | Validation |
|---|---|---|---|
| `product_name` | string | If omitted, `data.history` contains all filtered rows. If provided, `data.history` contains rows for this product and `data.summary`. | A missing product returns an empty history list and empty-product summary. |
| `product_retailer` | string | Used only with `product_name`. If omitted and exactly one retailer is selected, that one is used. | Required when `product_name` is supplied and multiple retailers are selected. |

#### Success data without `product_name`

| Field | Type | Description |
|---|---|---|
| `history` | array of objects | Normalized rows from `HISTORY_COLUMNS`. Empty if no rows match the filters. |

#### Success data with `product_name`

| Field | Type | Description |
|---|---|---|
| `history` | array of objects | Product history rows with `date`, `price`, `category`, `source_file`. |
| `summary` | object | Product summary from `summarize_product_history()`. |

Product summary fields:

| Field | Type | Empty-product value |
|---|---|---|
| `latest_price` | number or null | `null` |
| `cheapest_price` | number or null | `null` |
| `cheapest_date` | string or null | `null` |
| `change_since_first_pct` | number | `0.0` |

### `GET /api/retailer-averages`

Returns average or median price trends grouped by date and retailer.

#### Query parameters

Includes all common filters plus:

| Parameter | Type | Default / behavior | Validation |
|---|---|---|---|
| `aggregation` | string | Defaults to `Average`. `Median` switches to median. | Must be exactly `Average` or `Median`. |

#### Success data

| Field | Type | Description |
|---|---|---|
| `records` | array of objects | Trend records with `date`, `retailer`, `price`. |
| `retailer_averages` | array of objects | Same as `records`. |

### `GET /api/movers`

Returns biggest drops and gains for products with at least two observations.

#### Query parameters

Includes all common filters plus:

| Parameter | Type | Default / behavior | Validation |
|---|---|---|---|
| `scope_retailer` | string | Defaults to `All retailers`. Scopes mover calculations to one retailer. | Must be `All retailers` or a selected retailer. |
| `limit` | integer | Defaults to `10`. Controls rows per mover list. | Between `5` and `30`. |

#### Success data

| Field | Type | Description |
|---|---|---|
| `biggest_drops` | array of objects | Rows with `retailer`, `product_name`, price, and percentage data. |
| `biggest_gains` | array of objects | Rows with `retailer`, `product_name`, price, and percentage data. |

### `GET /api/coverage`

Returns dataset coverage diagnostics.

#### Query parameters

Includes all common filters plus:

| Parameter | Type | Default / behavior | Validation |
|---|---|---|---|
| `category_limit` | integer | Defaults to `20`. Caps category coverage rows. | Must be at least `1`. |

#### Success data

| Field | Type | Description |
|---|---|---|
| `summary` | object | Coverage counts and date range. |
| `coverage_over_time` | array of objects | Tracked products by date and retailer. |
| `category_coverage` | array of objects | Products by retailer and category. |
| `skipped_files` | array of objects | Skipped file diagnostics. |

## Error Responses

Filter validation errors return `400 Bad Request` responses.

Error envelope shape:

```json
{
  "data": null,
  "meta": { "filters": {} },
  "errors": [
    { "code": "invalid_filter", "message": "Unknown retailer: <name>" }
  ]
}
```

Documented failure codes:

| Trigger | Message |
|---|---|
| Unknown `retailer` | `Unknown retailer: <name>` |
| Invalid `start_date` or `end_date` | `Invalid date` |
| `start_date` after `end_date` | `Invalid date range` |
| Invalid `max_files` | `Invalid max_files` |
| Invalid `all_history` | `Invalid all_history` |
| Product lookup with multiple retailers and no `product_retailer` | `product_retailer is required` |
| Invalid `aggregation` | `Invalid aggregation` |
| Invalid `scope_retailer` | `Unknown retailer: <name>` |
| Invalid `limit`, `mover_count`, or `category_limit` | `Invalid <parameter>` |

## Empty States

Empty states are successful responses unless a filter is invalid:

- Empty inventory: `retailers: []`, `min_date: null`, `max_date: null`, counts `0`
- Empty history: `data.history: []`
- Missing product: empty history list, summary values `null`/`0.0`
- No retailer averages: `data.records: []`, `data.retailer_averages: []`
- No movers: empty `biggest_drops` and `biggest_gains`
- No coverage: zero-valued summary, `date_range: "-"`, empty arrays

## Frontend Integration

The Streamlit frontend (`streamlit_app.py`) consumes these endpoints through `inflation_dashboard.frontend.api_client`. Each endpoint has a dedicated wrapper function:

| Endpoint | Client Method |
|---|---|
| `/api/inventory` | `fetch_inventory(base_url)` |
| `/api/history` | `fetch_history(base_url, filters)` |
| `/api/retailer-averages` | `fetch_retailer_averages(base_url, filters)` |
| `/api/movers` | `fetch_movers(base_url, filters)` |
| `/api/coverage` | `fetch_coverage(base_url, filters)` |

The client validates response envelopes and raises `ApiClientError` on non-JSON, non-envelope, or non-200 responses.

## Verification

```bash
# Bounded in-process smoke check
uv run python scripts/verify_falcon_api.py

# Frontend API client verification
uv run python scripts/verify_streamlit_api_frontend.py

# Combined full-stack test
uv run python scripts/verify_full_stack.py
```
