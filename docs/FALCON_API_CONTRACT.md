# Falcon REST API Contract & Specification

**Target Frontend:** Svelte 5 / SvelteKit Frontend  
**API Backend:** Falcon WSGI Application (`inflation_dashboard/api/falcon_app.py`)  
**Specification Version:** 1.1.0  
**Last Updated:** 2026-09-02  
**Status:** Active / Regression-Verified  

---

## 1. Architectural Principles & Transport Protocol

### 1.1 Transport & Media Format
- **Protocol:** HTTP/1.1 (WSGI served via Gunicorn / Waitress)
- **Base URL:** Configurable via environment variable `VITE_API_BASE_URL` or `PUBLIC_API_BASE_URL` (default: `http://localhost:8000`)
- **Default Content-Type:** `application/json` (UTF-8 encoded)
- **Serialization Engine:** Fast native JSON via `orjson` on the Falcon server, with strict standard JSON compatibility (all `NaN`, `Infinity`, `NaT`, and non-compliant floating point representations are sanitized to `null` before transmission).
- **CORS Support:** Full cross-origin access enabled via `falcon.CORSMiddleware` in `inflation_dashboard/api/falcon_app.py` (registered 2026-09-03; honors the `FALCON_CORS_ORIGINS` env var, default `*`). Preflight `OPTIONS` requests return `200 OK` with allowed headers and methods (`GET, OPTIONS`).

### 1.2 Hexagonal Architecture Separation
The API follows strict clean architecture boundaries:
1. **Domain (`inflation_dashboard/domain/`):** Pure normalization logic, price calculations, and invariant rules. No web framework dependencies.
2. **Adapters (`inflation_dashboard/adapters/`):** Storage implementations (`csv_price_repository.py` and `sqlite_price_repository.py`).
3. **Application (`inflation_dashboard/application/`):** Use cases and chart specifications.
4. **API Layer (`inflation_dashboard/api/`):** Falcon resources, request parameter parsers, JSON serialization, and error translation.
5. **Frontend Client:** Decoupled presentation layer communicating exclusively via this HTTP contract.

---

## 2. Standard API Envelope

All HTTP responses from the Falcon API adhere to a uniform top-level envelope.

### 2.1 Envelope Schema
```json
{
  "data": null,
  "meta": {},
  "errors": []
}
```

| Property | Type | Description |
|---|---|---|
| `data` | `object \| array \| null` | The primary response payload on success. `null` when a request fails with an error (e.g. HTTP 400). |
| `meta` | `object` | Metadata including filter reflections, row counts, inventory counts, and server warnings. Always an object (empty `{}` if no metadata). |
| `errors` | `array<ApiError>` | Array of error objects. Empty array `[]` on successful responses. Populated with code/message pairs on error. |

### 2.2 Error Object Schema
```json
{
  "code": "invalid_filter",
  "message": "Unknown retailer: NonExistentRetailer",
  "meta": {
    "filters": {
      "retailer": ["NonExistentRetailer"]
    }
  }
}
```

| Field | Type | Description |
|---|---|---|
| `code` | `string` | Machine-readable error code (e.g., `invalid_filter`, `not_found`, `bad_request`). |
| `message` | `string` | User-friendly error message, guaranteed safe for UI display (<= 160 characters). |
| `meta` | `object` (optional) | Contextual debugging information, such as the rejected filter parameters. |

### 2.3 HTTP Status Codes
| HTTP Code | Condition | Envelope Payload |
|---|---|---|
| `200 OK` | Successful request, even if 0 results match | `data` populated, `meta` populated, `errors: []` |
| `400 Bad Request` | Filter validation failure, syntax error in query string | `data: null`, `meta.filters` populated, `errors: [{code, message}]` |
| `404 Not Found` | Unknown route or specific entity not found | `data: null`, `errors: [{code: "not_found", message: "..."}]` |
| `500 Internal Server Error` | Unexpected backend runtime exception | Standard server error envelope |

---

## 3. Common Query Parameters

The data query endpoints (`/api/history`, `/api/retailer-averages`, `/api/movers`, `/api/coverage`) share common filter parameters handled by `parse_common_filters`.

| Parameter | Type | Required | Default | Validation & Behavior |
|---|---|---|---|---|
| `retailer` | `string` (repeatable) | No | `DEFAULT_RETAILERS` (`Markets / Gurmar`, `ClothingStores / Vakko`, `ConstructionSuppliesMarkets / yapimaks`) | Must exist in the discovered inventory. Multiple retailers are specified by repeating the parameter: `?retailer=RetailerA&retailer=RetailerB`. If an unknown retailer is passed, returns HTTP 400 with `Unknown retailer: <name>`. |
| `start_date` | `string` (`YYYY-MM-DD`) | No | Latest 60-day window before `max_date` (bounded by `min_date`) | Must be valid ISO date string. Cannot be later than `end_date`. Returns HTTP 400 `Invalid date` or `Invalid date range`. |
| `end_date` | `string` (`YYYY-MM-DD`) | No | `max_date` of inventory | Must be valid ISO date string. Returns HTTP 400 `Invalid date`. |
| `max_files` | `integer` | No | `45` (`DEFAULT_MAX_FILES_PER_RETAILER`) | Must be non-negative integer. `0` disables the file cap (uncapped load). Returns HTTP 400 `Invalid max_files` if negative or non-integer. |
| `all_history` | `boolean` | No | `false` | Accepts boolean representations: `true, 1, t, yes, on` or `false, 0, f, no, off`. When true, forces `max_files=0` and adds server warning to `meta.warnings`. |

### Common Response `meta` Fields
When common filters are evaluated, the `meta` object contains:
```json
{
  "filters": {
    "selected_retailers": ["Markets / Gurmar"],
    "start_date": "2026-07-04",
    "end_date": "2026-09-02",
    "max_files_per_retailer": 45,
    "all_history": false
  },
  "inventory_file_count": 982,
  "selected_inventory_file_count": 45,
  "history_row_count": 172530,
  "skipped_file_count": 0,
  "warnings": []
}
```

---

## 4. Detailed Endpoint Specifications

### 4.1 `GET /api/health`
Lightweight service health probe. Never reads databases or files; designed for container health checks, load balancer pings, and frontend connection verification.

- **URL:** `/api/health`
- **Method:** `GET`
- **Query Parameters:** None.
- **Success Status:** `200 OK`

#### Example Response
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

---

### 4.2 `GET /api/inventory`
Discovers and returns catalog boundaries: available retailers, earliest date, and latest date across the entire dataset.

- **URL:** `/api/inventory`
- **Method:** `GET`
- **Query Parameters:** None.
- **Success Status:** `200 OK`

#### Example Response
```json
{
  "data": {
    "retailers": [
      "ClothingStores / Vakko",
      "ConstructionSuppliesMarkets / TasciYapiMarket",
      "ConstructionSuppliesMarkets / yapimaks",
      "Cosmetics / Watson",
      "HomeGoods",
      "HousesRent / Kayseri",
      "HousesRent / Sivas",
      "HousesRent / Tokat",
      "Markets / Gurmar",
      "Technology"
    ],
    "min_date": "2026-02-21T00:00:00",
    "max_date": "2026-09-02T00:00:00"
  },
  "meta": {
    "file_count": 982,
    "inventory_file_count": 982
  },
  "errors": []
}
```

---

### 4.3 `GET /api/history`
Fetches normalized price history. Operates in two distinct modes depending on whether `product_name` is supplied:
1. **General History Mode (`product_name` omitted):** Returns full normalized observations matching filter criteria.
2. **Product Explorer Mode (`product_name` provided):** Returns single-product time series and calculated summary statistics.

- **URL:** `/api/history`
- **Method:** `GET`
- **Query Parameters:**
  - Common filters (`retailer`, `start_date`, `end_date`, `max_files`, `all_history`)
  - `product_name` (`string`, optional): Product display name to focus on.
  - `product_retailer` (`string`, optional): Required if `product_name` is supplied and multiple retailers are selected. If omitted and exactly one retailer is selected, automatically defaults to that retailer.

#### Success Response: Mode A (General History)
```json
{
  "data": {
    "history": [
      {
        "date": "2026-09-02T00:00:00",
        "retailer": "Markets / Gurmar",
        "product_id": "%100 Karışık 1lt",
        "product_name": "%100 Karışık 1lt",
        "category": "Uncategorized",
        "price": 120.0,
        "source_file": "InflationItems/Datas/Markets/Gurmar/gurmar_prices_2026-09-02.csv"
      }
    ]
  },
  "meta": {
    "filters": {
      "selected_retailers": ["Markets / Gurmar"],
      "start_date": "2026-07-04",
      "end_date": "2026-09-02",
      "max_files_per_retailer": 45,
      "all_history": false
    },
    "inventory_file_count": 982,
    "selected_inventory_file_count": 45,
    "history_row_count": 1,
    "skipped_file_count": 0,
    "warnings": []
  },
  "errors": []
}
```

#### Success Response: Mode B (Product Explorer)
```json
{
  "data": {
    "history": [
      {
        "date": "2026-08-01T00:00:00",
        "price": 110.0,
        "category": "Uncategorized",
        "source_file": "InflationItems/Datas/Markets/Gurmar/gurmar_prices_2026-08-01.csv"
      },
      {
        "date": "2026-09-02T00:00:00",
        "price": 120.0,
        "category": "Uncategorized",
        "source_file": "InflationItems/Datas/Markets/Gurmar/gurmar_prices_2026-09-02.csv"
      }
    ],
    "summary": {
      "latest_price": 120.0,
      "cheapest_price": 110.0,
      "cheapest_date": "2026-08-01T00:00:00",
      "change_since_first_pct": 9.09
    }
  },
  "meta": {
    "filters": {
      "selected_retailers": ["Markets / Gurmar"],
      "start_date": "2026-07-04",
      "end_date": "2026-09-02",
      "max_files_per_retailer": 45,
      "all_history": false
    },
    "product_name": "%100 Karışık 1lt",
    "product_retailer": "Markets / Gurmar",
    "inventory_file_count": 982,
    "selected_inventory_file_count": 45,
    "history_row_count": 2,
    "skipped_file_count": 0,
    "warnings": []
  },
  "errors": []
}
```

#### Empty Product State (Missing Product)
If a product has no records in the selected range, it returns `200 OK` with an empty history list and zeroed/null summary:
```json
{
  "data": {
    "history": [],
    "summary": {
      "latest_price": null,
      "cheapest_price": null,
      "cheapest_date": null,
      "change_since_first_pct": 0.0
    }
  },
  "meta": {
    "product_name": "Nonexistent Item",
    "product_retailer": "Markets / Gurmar"
  },
  "errors": []
}
```

---

### 4.4 `GET /api/retailer-averages`
Returns average or median price points per date for each selected retailer, suitable for time-series trend charts.

- **URL:** `/api/retailer-averages`
- **Method:** `GET`
- **Query Parameters:**
  - Common filters (`retailer`, `start_date`, `end_date`, `max_files`, `all_history`)
  - `aggregation` (`string`, optional): Metric to calculate. Either `"Average"` or `"Median"` (case-sensitive). Default is `"Average"`.
- **Validation:** If `aggregation` is not `"Average"` or `"Median"`, returns HTTP 400 with `Invalid aggregation`.

#### Example Response
```json
{
  "data": {
    "records": [
      {
        "date": "2026-09-02T00:00:00",
        "retailer": "Markets / Gurmar",
        "price": 183.13
      }
    ],
    "retailer_averages": [
      {
        "date": "2026-09-02T00:00:00",
        "retailer": "Markets / Gurmar",
        "price": 183.13
      }
    ]
  },
  "meta": {
    "filters": { ... },
    "aggregation": "Average",
    "skipped_file_count": 0
  },
  "errors": []
}
```

---

### 4.5 `GET /api/movers`
Calculates biggest price drops and gains for products with repeated observations over time.

- **URL:** `/api/movers`
- **Method:** `GET`
- **Query Parameters:**
  - Common filters (`retailer`, `start_date`, `end_date`, `max_files`, `all_history`)
  - `scope_retailer` (`string`, optional): Retailer to isolate. Defaults to `"All retailers"`. If set to a specific retailer, it must be present in `retailer` selections.
  - `limit` (`integer`, optional): Number of items per category (drops/gains). Default is `10`. Minimum `5`, maximum `30`.
  - `mover_count` (`integer`, optional): Alias for `limit`.
- **Validation:**
  - If `scope_retailer` is not `"All retailers"` or one of the selected retailers, returns HTTP 400 `Unknown retailer: <name>`.
  - If `limit` is not between 5 and 30, returns HTTP 400 `Invalid limit`.

#### Example Response
```json
{
  "data": {
    "biggest_drops": [
      {
        "retailer": "Markets / Gurmar",
        "product_name": "Zeytinyağı Riviera 1L",
        "latest_price": 249.90,
        "max_price": 349.90,
        "savings_vs_peak": 100.00,
        "drop_from_peak_pct": -28.58,
        "last_seen": "2026-09-02T00:00:00"
      }
    ],
    "biggest_gains": [
      {
        "retailer": "Markets / Gurmar",
        "product_name": "Organik Yumurta 10lu",
        "first_price": 45.00,
        "latest_price": 69.90,
        "change_since_first_pct": 55.33,
        "first_seen": "2026-03-06T00:00:00",
        "last_seen": "2026-09-02T00:00:00"
      }
    ]
  },
  "meta": {
    "filters": { ... },
    "scope_retailer": "All retailers",
    "limit": 10,
    "eligible_product_count": 3120,
    "skipped_file_count": 0
  },
  "errors": []
}
```

---

### 4.6 `GET /api/coverage`
Returns data pipeline health diagnostics: observation volume over time, category coverage, and skipped invalid files.

- **URL:** `/api/coverage`
- **Method:** `GET`
- **Query Parameters:**
  - Common filters (`retailer`, `start_date`, `end_date`, `max_files`, `all_history`)
  - `category_limit` (`integer`, optional): Caps the number of top categories returned in `category_coverage`. Default `20`. Must be `>= 1`.
- **Validation:** If `category_limit` is `< 1`, returns HTTP 400 `Invalid category_limit`.

#### Example Response
```json
{
  "data": {
    "summary": {
      "retailer_count": 1,
      "product_count": 3834,
      "observation_count": 3834,
      "date_range": "2026-09-02 → 2026-09-02",
      "skipped_file_count": 0
    },
    "coverage_over_time": [
      {
        "date": "2026-09-02T00:00:00",
        "retailer": "Markets / Gurmar",
        "tracked_products": 3834
      }
    ],
    "category_coverage": [
      {
        "retailer": "Markets / Gurmar",
        "category": "Uncategorized",
        "products": 3834
      }
    ],
    "skipped_files": [
      {
        "file": "InflationItems/Datas/Corrupted/sample.csv",
        "reason": "Missing required date format"
      }
    ]
  },
  "meta": {
    "filters": { ... },
    "category_limit": 20,
    "skipped_file_count": 0
  },
  "errors": []
}
```

---

### 4.7 `GET /api/products/search` (Autocomplete & Detail)
Fast autocomplete search endpoint designed for the Svelte frontend search inputs and typeahead widgets.

- **URL:** `/api/products/search` (or `/api/product`)
- **Method:** `GET`
- **Query Parameters:**
  - `q` (`string`, required): Search term (min length: 2 characters).
  - `retailer` (`string`, optional): Optional retailer filter to narrow autocomplete suggestions.
  - `limit` (`integer`, optional): Maximum number of autocomplete suggestions (default: `20`, max: `100`).
- **Validation:**
  - If `q` is missing or shorter than 2 characters, returns HTTP 400 `Search query must be at least 2 characters`.

#### Example Response
```json
{
  "data": {
    "products": [
      {
        "product_id": "12345",
        "product_name": "Sütaş Tam Yağlı Süt 1L",
        "retailer": "Markets / Gurmar",
        "category": "Süt ve Kahvaltılık",
        "latest_price": 34.50,
        "last_seen": "2026-09-02"
      }
    ]
  },
  "meta": {
    "query": "Sütaş",
    "retailer": "Markets / Gurmar",
    "limit": 20,
    "result_count": 1
  },
  "errors": []
}
```

---

## 5. TypeScript Interfaces for the Svelte Frontend

The following TypeScript definitions should be placed in `src/lib/types/api.ts` in the Svelte application:

```typescript
/**
 * Standard API Response Envelope.
 */
export interface ApiResponse<T, M = Record<string, unknown>> {
  data: T;
  meta: M;
  errors: ApiError[];
}

/**
 * Standard API Error Detail.
 */
export interface ApiError {
  code: string;
  message: string;
  meta?: Record<string, unknown>;
}

/**
 * Error Envelope (data is null on failure).
 */
export interface ApiErrorEnvelope {
  data: null;
  meta: Record<string, unknown>;
  errors: ApiError[];
}

// ── Common Filter Parameters ──────────────────────────────────────────────────

export interface CommonFilterParams {
  retailer?: string | string[];
  start_date?: string; // YYYY-MM-DD
  end_date?: string;   // YYYY-MM-DD
  max_files?: number;
  all_history?: boolean;
}

export interface CommonFilterMeta {
  filters: {
    selected_retailers: string[];
    start_date: string | null;
    end_date: string | null;
    max_files_per_retailer: number;
    all_history: boolean;
  };
  inventory_file_count: number;
  selected_inventory_file_count: number;
  history_row_count?: number;
  skipped_file_count?: number;
  warnings?: string[];
}

// ── 1. Health ─────────────────────────────────────────────────────────────────

export interface HealthData {
  status: "ok" | string;
}

export interface HealthMeta {
  service: string;
}

export type HealthResponse = ApiResponse<HealthData, HealthMeta>;

// ── 2. Inventory ──────────────────────────────────────────────────────────────

export interface InventoryData {
  retailers: string[];
  min_date: string | null; // ISO datetime/date
  max_date: string | null; // ISO datetime/date
}

export interface InventoryMeta {
  file_count: number;
  inventory_file_count: number;
}

export type InventoryResponse = ApiResponse<InventoryData, InventoryMeta>;

// ── 3. History ────────────────────────────────────────────────────────────────

export interface HistoryRecord {
  date: string; // ISO datetime: "2026-09-02T00:00:00"
  retailer: string;
  product_id: string | null;
  product_name: string;
  category: string | null;
  price: number | null;
  source_file: string;
}

export interface ProductHistoryPoint {
  date: string;
  price: number | null;
  category: string | null;
  source_file: string;
}

export interface ProductSummary {
  latest_price: number | null;
  cheapest_price: number | null;
  cheapest_date: string | null;
  change_since_first_pct: number;
}

export interface GeneralHistoryData {
  history: HistoryRecord[];
}

export interface ProductHistoryData {
  history: ProductHistoryPoint[];
  summary: ProductSummary;
}

export interface HistoryMeta extends CommonFilterMeta {
  product_name?: string;
  product_retailer?: string;
}

export type HistoryResponse = ApiResponse<GeneralHistoryData | ProductHistoryData, HistoryMeta>;

// ── 4. Retailer Averages ──────────────────────────────────────────────────────

export interface RetailerAverageRecord {
  date: string;
  retailer: string;
  price: number | null;
}

export interface RetailerAveragesData {
  records: RetailerAverageRecord[];
  retailer_averages: RetailerAverageRecord[];
}

export interface RetailerAveragesMeta extends CommonFilterMeta {
  aggregation: "Average" | "Median";
}

export type RetailerAveragesResponse = ApiResponse<RetailerAveragesData, RetailerAveragesMeta>;

// ── 5. Movers ─────────────────────────────────────────────────────────────────

export interface MoverDropRecord {
  retailer: string;
  product_name: string;
  latest_price: number | null;
  max_price: number | null;
  savings_vs_peak: number | null;
  drop_from_peak_pct: number | null;
  last_seen: string | null;
}

export interface MoverGainRecord {
  retailer: string;
  product_name: string;
  first_price: number | null;
  latest_price: number | null;
  change_since_first_pct: number | null;
  first_seen: string | null;
  last_seen: string | null;
}

export interface MoversData {
  biggest_drops: MoverDropRecord[];
  biggest_gains: MoverGainRecord[];
}

export interface MoversMeta extends CommonFilterMeta {
  scope_retailer: string;
  limit: number;
  eligible_product_count: number;
}

export type MoversResponse = ApiResponse<MoversData, MoversMeta>;

// ── 6. Coverage ───────────────────────────────────────────────────────────────

export interface CoverageSummary {
  retailer_count: number;
  product_count: number;
  observation_count: number;
  date_range: string;
  skipped_file_count: number;
}

export interface CoverageOverTimeRecord {
  date: string;
  retailer: string;
  tracked_products: number;
}

export interface CategoryCoverageRecord {
  retailer: string;
  category: string;
  products: number;
}

export interface SkippedFileDiagnostic {
  file: string;
  reason: string;
}

export interface CoverageData {
  summary: CoverageSummary;
  coverage_over_time: CoverageOverTimeRecord[];
  category_coverage: CategoryCoverageRecord[];
  skipped_files: SkippedFileDiagnostic[];
}

export interface CoverageMeta extends CommonFilterMeta {
  category_limit: number;
}

export type CoverageResponse = ApiResponse<CoverageData, CoverageMeta>;

// ── 7. Product Search & Autocomplete ──────────────────────────────────────────

export interface ProductSearchResult {
  product_id: string;
  product_name: string;
  retailer: string;
  category: string | null;
  latest_price: number | null;
  last_seen: string | null;
}

export interface ProductSearchData {
  products: ProductSearchResult[];
}

export interface ProductSearchMeta {
  query: string;
  retailer?: string;
  limit: number;
  result_count: number;
}

export type ProductSearchResponse = ApiResponse<ProductSearchData, ProductSearchMeta>;
```

---

## 6. Svelte Frontend Integration Patterns

### 6.1 Recommended API Client Helper (`src/lib/api/client.ts`)

```typescript
import type { ApiResponse, CommonFilterParams } from '$lib/types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export class ApiErrorResponse extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public meta?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ApiErrorResponse';
  }
}

/**
 * Serializes CommonFilterParams into URLSearchParams handling array fields.
 */
export function buildQueryParams(params: Record<string, any>): URLSearchParams {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        query.append(key, String(item));
      }
    } else {
      query.set(key, String(value));
    }
  }
  return query;
}

/**
 * Universal type-safe fetcher for Falcon API endpoints.
 */
export async function fetchApi<T, M = Record<string, unknown>>(
  endpoint: string,
  params?: Record<string, any>,
  fetchFn: typeof fetch = fetch
): Promise<ApiResponse<T, M>> {
  const queryString = params ? `?${buildQueryParams(params).toString()}` : '';
  const url = `${API_BASE_URL}${endpoint}${queryString}`;

  const res = await fetchFn(url, {
    headers: {
      Accept: 'application/json',
    },
  });

  const payload = await res.json();

  if (!res.ok) {
    const error = payload.errors?.[0] || {
      code: 'http_error',
      message: `Request failed with status ${res.status}`,
    };
    throw new ApiErrorResponse(res.status, error.code, error.message, error.meta || payload.meta);
  }

  return payload as ApiResponse<T, M>;
}
```

### 6.2 Svelte 5 Rune State Management Example

```svelte
<script lang="ts">
  import { fetchApi } from '$lib/api/client';
  import type { InventoryData, InventoryMeta, RetailerAverageRecord } from '$lib/types/api';

  let inventory = $state<InventoryData | null>(null);
  let selectedRetailers = $state<string[]>([]);
  let averages = $state<RetailerAverageRecord[]>([]);
  let loading = $state(false);
  let errorMessage = $state<string | null>(null);

  // Load initial inventory
  async function loadInventory() {
    try {
      loading = true;
      const res = await fetchApi<InventoryData, InventoryMeta>('/api/inventory');
      inventory = res.data;
      selectedRetailers = res.data.retailers.slice(0, 3);
      await loadAverages();
    } catch (err: any) {
      errorMessage = err.message;
    } finally {
      loading = false;
    }
  }

  // Reload trend averages when filters change
  async function loadAverages() {
    try {
      loading = true;
      errorMessage = null;
      const res = await fetchApi<{ records: RetailerAverageRecord[] }>('/api/retailer-averages', {
        retailer: selectedRetailers,
        aggregation: 'Average'
      });
      averages = res.data.records;
    } catch (err: any) {
      errorMessage = err.message;
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    loadInventory();
  });
</script>

{#if loading}
  <div class="spinner">Loading inflation statistics...</div>
{:else if errorMessage}
  <div class="alert alert-error">{errorMessage}</div>
{:else}
  <div class="dashboard-grid">
    <div class="metric-card">
      <h3>Monitored Retailers</h3>
      <p>{selectedRetailers.join(', ')}</p>
    </div>
    <div class="metric-card">
      <h3>Data Points</h3>
      <p>{averages.length} trend records</p>
    </div>
  </div>
{/if}
```

---

## 7. Verification & Compliance Checklist

All Falcon API endpoints are validated by regression test suites:
- `python scripts/verify_falcon_api.py` (Falcon API in-process TestClient smoke suite)
- `python scripts/verify_full_stack.py` (Full stack integration suite)

### Verification Requirements:
1. **Zero Leaked Types:** Payloads must never leak NaN, Infinity, pandas `NaT`/`NA`, or numpy scalars into JSON.
2. **Deterministic Envelopes:** All endpoints must always return `{ "data", "meta", "errors" }`.
3. **CORS Headers:** `Access-Control-Allow-Origin: *` must be present on responses and preflight requests.
4. **Boundary Isolation:** Handlers and adapters must strictly respect domain boundaries and never import presentation libraries (`streamlit`, `plotly`).
