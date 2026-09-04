# API Reference

This document provides the complete specification for the Falcon REST API implemented under `inflation_dashboard/api/`.

The API is backed by the high-performance SQLite time-series database (`InflationItems/prices.db`) with automatic fallback to CSV files. It serves the **Svelte production frontend** (`frontend/`); the legacy Streamlit client is kept for administrative use.

> **Canonical spec:** [`FALCON_API_CONTRACT.md`](FALCON_API_CONTRACT.md) is the regression-verified, authoritative contract (envelope shapes, TypeScript types, validation rules). This document is a quick reference summary and may lag the canonical spec.

---

## Architecture & Response Envelope

All API endpoints return a standardized JSON envelope serialized with `orjson`:

```json
{
  "data": {},
  "meta": {},
  "errors": []
}
```

* **`data`**: The payload (object, array, or null).
* **`meta`**: Metadata (pagination limits, warnings, query execution hints, timestamps).
* **`errors`**: Array of error objects `[{"code": "...", "message": "..."}]` on HTTP 4xx/5xx failures (empty list on success).

---

## CORS Configuration

The API registers `falcon.CORSMiddleware` in `inflation_dashboard/api/falcon_app.py`
(added 2026-09-03; the docs previously claimed it but it was not wired in).
Allowed origins are configured via `FALCON_CORS_ORIGINS` (consumed by the app
factory directly, and exposed as `--cors-origins` on `scripts/run_falcon_server.py`):

```bash
# Allow specific frontend origins (e.g. SvelteKit dev/preview)
export FALCON_CORS_ORIGINS="http://localhost:5173,http://localhost:4173"

# Default allows all origins ("*")
```

---

## Endpoints Overview

| Method | Route | Purpose | Warm Latency |
|---|---|---|---|
| `GET` | `/api/health` | Lightweight service health check | **~0.1 ms** |
| `GET` | `/api/inventory` | Discovered retailers, date boundaries, and file counts | **~0.1 ms** |
| `GET` | `/api/history` | Filtered historical price observations | **~0.3 ms** |
| `GET` | `/api/retailer-averages` | Average / median price trend series by retailer | **~0.1 ms** |
| `GET` | `/api/movers` | Top price gainers and droppers across time | **~0.1 ms** |
| `GET` | `/api/coverage` | Data density and category distribution over time | **~0.2 ms** |
| `GET` | `/api/products/search` | Fast keyword & category autocomplete for Svelte | **~0.1 ms** |
| `GET` | `/api/product` | Single product detail with full price history series | **~0.1 ms** |

---

## Detailed Endpoint Specifications

### 1. `GET /api/health`
Lightweight health and readiness check. Does not touch the database.

* **Query Parameters**: None
* **Response `data`**:
  ```json
  {
    "status": "ok"
  }
  ```
* **Response `meta`**:
  ```json
  {
    "service": "inflation-dashboard-api"
  }
  ```

---

### 2. `GET /api/inventory`
Returns available retailers, minimum and maximum observation dates, and file counts.

* **Query Parameters**: None
* **Response `data`**:
  ```json
  {
    "retailers": [
      "ClothingStores / Vakko",
      "Markets / Gurmar",
      "Technology",
      "HomeGoods",
      "Cosmetics / Watson",
      "ConstructionSuppliesMarkets / yapimaks",
      "ConstructionSuppliesMarkets / TasciYapiMarket",
      "HousesRent / Kayseri",
      "HousesRent / Sivas",
      "HousesRent / Tokat",
      "HousesRent / Emlakjet",
      "Health / Diagnostic&Surgical Services"
    ],
    "min_date": "2026-02-21",
    "max_date": "2026-09-02",
    "file_count": 982
  }
  ```

---

### 3. `GET /api/products/search`
High-speed product autocomplete endpoint backed by the `product_prices` table (covering-index seek, <2 ms).
Designed for Svelte search bars.

* **Query Parameters**:
  * `q` or `query` *(string, optional)*: Search string (matches `product_name` or `product_id`).
  * `retailer` *(string, optional)*: Restrict search to a specific retailer.
  * `category` *(string, optional)*: Restrict search to a specific category.
  * `limit` *(int, default: 20, clamped 1–100)*: Maximum number of returned matches.
* **Response `meta`**: `{"query": ..., "retailer": ..., "category": ..., "limit": ..., "count": N}`.
* **Example Request**:
  ```bash
  curl "http://localhost:8000/api/products/search?q=ceket&limit=5"
  ```
* **Response `data`**: Array of matching product summary objects:
  ```json
  [
    {
      "product_id": "M405060016-0047",
      "retailer": "ClothingStores / Vakko",
      "product_name": "AÇIK MAVİ CEKET",
      "category": "Kadin",
      "first_date": "2026-03-06",
      "last_date": "2026-09-02",
      "latest_price": 22975.0,
      "min_price": 22975.0,
      "max_price": 45950.0,
      "observations_count": 179
    }
  ]
  ```

---

### 4. `GET /api/product`
Single product detail endpoint returning the complete chronological time-series price history. Implemented by
`ProductDetailResource` (2026-09, SQLite-backed; ~10 ms cold, sub-0.2 ms cached).

* **Query Parameters**:
  * `product_id` *(string, required if `product_name` omitted)*: Unique product identifier.
  * `product_name` *(string, optional)*: Fallback product name.
  * `retailer` *(string, optional)*: Target retailer (if omitted, resolves across retailers).
* **Error states**: missing both `product_id`/`product_name` → HTTP 400 `invalid_filter`; product not found →
  HTTP 404 `not_found`.
* **Example Request**:
  ```bash
  curl "http://localhost:8000/api/product?product_id=M405487839-0027-0104"
  ```
* **Response `data`**:
  ```json
  {
    "product_id": "M405487839-0027-0104",
    "retailer": "ClothingStores / Vakko",
    "product_name": "BEJ DESENLI MAXI ELBISE",
    "category": "Kadin",
    "first_date": "2026-03-06",
    "last_date": "2026-09-02",
    "latest_price": 36475.0,
    "min_price": 36475.0,
    "max_price": 72950.0,
    "observations_count": 177,
    "price_history": {
      "2026-03-06": 72950.0,
      "2026-05-14": 54712.5,
      "2026-08-25": 36475.0,
      "2026-09-02": 36475.0
    },
    "summary": {
      "latest_price": 36475.0,
      "cheapest_price": 36475.0,
      "cheapest_date": "2026-08-25",
      "change_since_first_pct": -50.0
    }
  }
  ```

---

### 5. `GET /api/history`
Returns filtered historical price observations across retailers.

* **Query Parameters**:
  * `retailer` *(string, repeatable)*: e.g. `?retailer=Markets / Gurmar&retailer=HomeGoods`. Unknown values → HTTP 400.
  * `start_date` / `end_date` *(YYYY-MM-DD, optional)*: Filter window (defaults to the latest 60 days).
  * `max_files` *(int, default: 45)*: Bound history to the newest N files per retailer; `0` = uncapped.
  * `all_history` *(bool, default: false)*: Load uncapped history (`max_files=0`).
  * `product_name` *(string, optional)*: Filter to a single product; returns `{history, summary}`.
  * `product_retailer` *(string, optional)*: Required with `product_name` when multiple retailers are selected.

---

### 6. `GET /api/retailer-averages`
Calculates daily average or median price trends by retailer.

* **Query Parameters**:
  * `retailer` *(string, repeatable)*
  * `start_date`, `end_date` *(YYYY-MM-DD, optional)*
  * `max_files`, `all_history` *(optional)*
  * `aggregation` *(string, default: "Average")*: `"Average"` or `"Median"` (case-sensitive).
* **Response `data`**:
  ```json
  {
    "records": [
      {
        "date": "2026-08-01",
        "retailer": "Markets / Gurmar",
        "price": 142.50
      }
    ]
  }
  ```

---

### 7. `GET /api/movers`
Identifies the products with the largest price gains and price drops across the selected time period.

* **Query Parameters**:
  * `retailer`, `start_date`, `end_date`, `max_files`, `all_history` *(optional)*
  * `scope_retailer` *(string, default: "All retailers")*: restric analysis to one retailer or all.
  * `limit` *(int, default: 10, min 5, max 30)*: rows per category (alias: `mover_count`).
* **Response `data`**:
  ```json
  {
    "biggest_drops": [
      {
        "retailer": "Markets / Gurmar",
        "product_name": "Zeytinyağı Riviera 1L",
        "latest_price": 249.9,
        "max_price": 349.9,
        "savings_vs_peak": 100.0,
        "drop_from_peak_pct": -28.58,
        "last_seen": "2026-09-02T00:00:00"
      }
    ],
    "biggest_gains": [
      {
        "retailer": "Markets / Gurmar",
        "product_name": "Organik Yumurta 10lu",
        "first_price": 45.0,
        "latest_price": 69.9,
        "change_since_first_pct": 55.33,
        "first_seen": "2026-03-06T00:00:00",
        "last_seen": "2026-09-02T00:00:00"
      }
    ]
  }
  ```

---

### 8. `GET /api/coverage`
Returns data density, observation counts over time, and category distributions.

* **Query Parameters**:
  * `retailer`, `start_date`, `end_date`, `max_files`, `all_history` *(optional)*
  * `category_limit` *(int, default: 20, min 1)*: Maximum number of category bars to return.
* **Response `data`**:
  ```json
  {
    "summary": {
      "retailer_count": 3,
      "product_count": 15908,
      "observation_count": 425115,
      "date_range": "2026-07-20 → 2026-09-02",
      "skipped_file_count": 0
    },
    "coverage_over_time": [ ... ],
    "category_coverage": [ ... ]
  }
  ```

---

## Performance & Caching

- **Warm latency**: all endpoints serve in **0.09–0.23 ms** on warm requests (`scripts/benchmark_falcon_api.py`).
- **Response cache**: `api/filters.py` keeps a thread-safe LRU/TTL cache of pre-serialized `orjson` bytes
  (via `get_cached_response`/`put_cached_response`); warm requests bypass recalculation and serialization.
- **Dynamic routing**: data endpoints route through `sqlite_price_repository` when `InflationItems/prices.db`
  exists and fall back to `csv_price_repository` otherwise (`is_sqlite_available()` in `api/filters.py`).
- **Boundary**: `inflation_dashboard/api/` never imports `sqlite3`; database access lives only in the adapters layer.

## TypeScript Interfaces for Svelte Frontend

The complete TypeScript contract is located in [`docs/FALCON_API_CONTRACT.md`](FALCON_API_CONTRACT.md).
