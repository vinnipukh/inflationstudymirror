<!-- generated-by: gsd-doc-writer -->
# API Reference

This document covers the Falcon API implemented under `inflation_dashboard/api/`. It documents only the routes registered by `inflation_dashboard.api.falcon_app.create_app()`.

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
| `retailer` | repeatable string | If omitted, selects existing values from `DEFAULT_RETAILERS` (`Markets / Gurmar`, `ClothingStores / Vakko`, `HomeGoods`). If none exist in inventory, selects the first available retailers, up to three. | Unknown retailers return `400 Bad Request` with `code: "invalid_filter"`. |
| `start_date` | ISO date string | Defaults to the latest 60-day window bounded by discovered inventory min/max dates when inventory has dates. | Invalid ISO dates return `400 Bad Request`. A start date after `end_date` returns `400 Bad Request`. |
| `end_date` | ISO date string | Defaults to inventory `max_date` when available. | Invalid ISO dates return `400 Bad Request`. |
| `max_files` | integer | Defaults to `DEFAULT_MAX_FILES_PER_RETAILER` (`45`). Limits newest files loaded per selected retailer after date filtering. `0` means uncapped. | Negative or non-integer values return `400 Bad Request`. |
| `all_history` | boolean | Defaults to `false`. Truthy values force uncapped loading and set effective `max_files_per_retailer` to `0`. | Accepted true values: `1`, `true`, `t`, `yes`, `y`, `on`. Accepted false values: `0`, `false`, `f`, `no`, `n`, `off`. Other values return `400 Bad Request`. |

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

If selected files are skipped and no usable rows load, history-loading endpoints append the warning `selected files skipped; no usable rows loaded`.

## Endpoints

### `GET /api/health`

Lightweight status check.

#### Query parameters

None.

#### Success response

```json
{
  "data": {
    "status": "ok"
  },
  "meta": {
    "service": "inflation-dashboard-api"
  },
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
| `product_name` | string | If omitted, `data.history` contains all filtered history rows. If provided, `data.history` contains rows for this product only and `data.summary` is included. | No explicit validation. A missing product returns an empty history list and an empty-product summary. |
| `product_retailer` | string | Used only with `product_name`. If omitted and exactly one common `retailer` is selected, that selected retailer is used. | Required when `product_name` is supplied and multiple retailers are selected; otherwise returns `400 Bad Request` with `message: "product_retailer is required"`. |

#### Success data without `product_name`

| Field | Type | Description |
|---|---|---|
| `history` | array of objects | Normalized rows from `HISTORY_COLUMNS`. Empty if no rows match the filters. |

Large history responses add the warning `history response may be large` when `all_history` is true or more than 5,000 rows are returned.

#### Success data with `product_name`

| Field | Type | Description |
|---|---|---|
| `history` | array of objects | Product history rows with columns `date`, `price`, `category`, and `source_file`. Empty if the product is not found. |
| `summary` | object | Product summary from `summarize_product_history()`. |

Product summary fields are:

| Field | Type | Empty-product value |
|---|---|---|
| `latest_price` | number or null | `null` |
| `cheapest_price` | number or null | `null` |
| `cheapest_date` | string or null | `null` |
| `change_since_first_pct` | number | `0.0` |

Product responses also add `product_name` and `product_retailer` to `meta`.

### `GET /api/retailer-averages`

Returns average or median price trends grouped by date and retailer.

#### Query parameters

Includes all common filters plus:

| Parameter | Type | Default / behavior | Validation |
|---|---|---|---|
| `aggregation` | string | Defaults to `Average`. `Median` switches the aggregation from mean to median. | Must be exactly `Average` or `Median`; other values return `400 Bad Request` with `message: "Invalid aggregation"`. |

#### Success data

| Field | Type | Description |
|---|---|---|
| `records` | array of objects | Trend records with columns `date`, `retailer`, and `price`. Empty if no filtered rows are available. |
| `retailer_averages` | array of objects | Same records as `records`, retained as an explicit endpoint-specific key. |

#### Success metadata

Includes common metadata plus:

| Field | Type | Description |
|---|---|---|
| `aggregation` | string | Effective aggregation, `Average` or `Median`. |
| `skipped_file_count` | integer | Number of skipped CSV files. |

### `GET /api/movers`

Returns biggest drops and gains for products with at least two observations.

#### Query parameters

Includes all common filters plus:

| Parameter | Type | Default / behavior | Validation |
|---|---|---|---|
| `scope_retailer` | string | Defaults to `All retailers`. Use a selected retailer to scope mover calculations to one retailer. | Must be `All retailers` or one of the selected retailers from the common filter. Unknown values return `400 Bad Request`. |
| `limit` | integer | Defaults to the parsed `mover_count` value, or `10` when neither is supplied. Controls number of rows returned for each mover list. | Must be between `5` and `30`, inclusive. |
| `mover_count` | integer | Backward-compatible default source for `limit`. Used only when `limit` is not supplied. | Must be between `5` and `30`, inclusive. |

#### Success data

| Field | Type | Description |
|---|---|---|
| `biggest_drops` | array of objects | Rows with columns `retailer`, `product_name`, `latest_price`, `max_price`, `savings_vs_peak`, `drop_from_peak_pct`, and `last_seen`. Empty if no eligible repeated products are found. |
| `biggest_gains` | array of objects | Rows with columns `retailer`, `product_name`, `first_price`, `latest_price`, `change_since_first_pct`, `first_seen`, and `last_seen`. Empty if no eligible repeated products are found. |

#### Success metadata

Includes common metadata plus:

| Field | Type | Description |
|---|---|---|
| `scope_retailer` | string | Effective mover scope. |
| `limit` | integer | Effective row limit. |
| `eligible_product_count` | integer | Number of products with enough observations for mover statistics before top-N slicing. |
| `skipped_file_count` | integer | Number of skipped CSV files. |

### `GET /api/coverage`

Returns dataset coverage diagnostics for the selected history.

#### Query parameters

Includes all common filters plus:

| Parameter | Type | Default / behavior | Validation |
|---|---|---|---|
| `category_limit` | integer | Defaults to `20`. Caps category coverage rows. | Must be at least `1`. Non-integer or smaller values return `400 Bad Request`. |

#### Success data

| Field | Type | Description |
|---|---|---|
| `summary` | object | Coverage counts and date range. |
| `coverage_over_time` | array of objects | Rows with columns `date`, `retailer`, and `tracked_products`. Empty if no filtered history is available. |
| `category_coverage` | array of objects | Rows with columns `retailer`, `category`, and `products`, capped by `category_limit`. Empty if no filtered history is available. |
| `skipped_files` | array of objects | Skipped file diagnostics with columns `file` and `reason`. |

`summary` contains:

| Field | Type | Empty-history value |
|---|---|---|
| `retailer_count` | integer | `0` |
| `product_count` | integer | `0` |
| `observation_count` | integer | `0` |
| `date_range` | string | `"-"` |
| `skipped_file_count` | integer | Number of skipped files. |

#### Success metadata

Includes common metadata plus:

| Field | Type | Description |
|---|---|---|
| `category_limit` | integer | Effective category coverage cap. |
| `skipped_file_count` | integer | Number of skipped CSV files. |

## Error Responses

Filter validation errors are converted to `400 Bad Request` responses by `_set_filter_error()`.

Error envelope shape:

```json
{
  "data": null,
  "meta": {
    "filters": {}
  },
  "errors": [
    {
      "code": "invalid_filter",
      "message": "Invalid filter message"
    }
  ]
}
```

Documented validation failures include:

| Trigger | Message source |
|---|---|
| Unknown `retailer` | `Unknown retailer: <name>` |
| Invalid `start_date` or `end_date` | `Invalid date` |
| `start_date` after `end_date` | `Invalid date range` |
| Invalid `max_files` | `Invalid max_files` |
| Invalid `all_history` boolean | `Invalid all_history` |
| Product lookup with multiple selected retailers and no `product_retailer` | `product_retailer is required` |
| Invalid `aggregation` | `Invalid aggregation` |
| Invalid `scope_retailer` | `Unknown retailer: <name>` |
| Invalid `limit`, `mover_count`, or `category_limit` | `Invalid <parameter>` |

## Empty States

Empty states are successful responses unless a filter is invalid:

- Empty inventory returns `retailers: []`, `min_date: null`, `max_date: null`, and count metadata of `0`.
- Empty history returns `data.history: []`.
- Product history for a missing product returns `data.history: []` and summary values of `null`/`0.0`.
- Retailer averages return `data.records: []` and `data.retailer_averages: []` when there is no filtered history.
- Movers return empty `biggest_drops` and `biggest_gains` lists when there are no products with repeated observations.
- Coverage returns zero-valued summary counts, `date_range: "-"`, and empty coverage arrays when there is no filtered history.

## Smoke Verification

Run the bounded Falcon API smoke check from the repository root:

```bash
python scripts/verify_falcon_api.py
```

The script uses Falcon's in-process `falcon.testing.TestClient`; it does not bind a port or start a persistent server. It verifies route registration, import boundaries, stable envelope keys, endpoint response shapes, JSON-native serialization, an empty product-history response, and an invalid-filter `400 Bad Request` response.
