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
  end_date?: string; // YYYY-MM-DD
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
  status: 'ok' | string;
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
  warnings?: string[];
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
  aggregation: 'Average' | 'Median';
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

// ── 7. Product Detail (SQLite-backed) ───────────────────────────────────────

export interface ProductDetailData {
  product_id: string | null;
  retailer: string | null;
  product_name: string | null;
  category: string | null;
  first_date: string | null;
  last_date: string | null;
  latest_price: number | null;
  min_price: number | null;
  max_price: number | null;
  observations_count: number;
  price_history: Record<string, number>; // {date: price}
  history: ProductHistoryPoint[];
  summary: ProductSummary;
}

export interface ProductDetailMeta {
  product_id: string | null;
  retailer: string | null;
  observations_count: number;
}

export type ProductDetailResponse = ApiResponse<ProductDetailData, ProductDetailMeta>;
