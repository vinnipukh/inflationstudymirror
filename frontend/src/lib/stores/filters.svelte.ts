import type { CommonFilterParams } from '$lib/types/api';

const ENV_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined;

/**
 * Build-time default API origin (VITE_API_BASE_URL), fallback to the local
 * Falcon API on :8000. The user can override it at runtime in the sidebar.
 */
export const DEFAULT_API_BASE_URL: string =
  ENV_BASE && ENV_BASE.trim() ? ENV_BASE.replace(/\/+$/, '') : 'http://localhost:8000';

// Auto-load only Gurmar on open (per owner request). Users can add more in the sidebar.
export const DEFAULT_RETAILERS = ['Markets / Gurmar'];

/**
 * Global dashboard filter state (Svelte 5 runes, object form so components can
 * bind/mutate individual properties). Mirrors the legacy Streamlit sidebar:
 * retailer selection, date window, file cap, all-history mode.
 */
export const filters = $state({
  /** Live API origin used by every request. */
  apiBaseUrl: DEFAULT_API_BASE_URL,
  retailerOptions: [] as string[],
  inventoryMinDate: null as string | null,
  inventoryMaxDate: null as string | null,
  inventoryFileCount: null as number | null,
  selectedRetailers: [] as string[],
  startDate: null as string | null,
  endDate: null as string | null,
  maxFiles: 45,
  allHistory: false,
  /** True once inventory has been loaded successfully for the current API. */
  inventoryReady: false
});

export function resetFilters(): void {
  filters.retailerOptions.length = 0;
  filters.inventoryMinDate = null;
  filters.inventoryMaxDate = null;
  filters.inventoryFileCount = null;
  filters.selectedRetailers.length = 0;
  filters.startDate = null;
  filters.endDate = null;
  filters.maxFiles = 45;
  filters.allHistory = false;
  filters.inventoryReady = false;
}

export function initInventory(retailers: string[], minDate: string | null, maxDate: string | null): void {
  filters.retailerOptions.length = 0;
  filters.retailerOptions.push(...retailers);
  filters.inventoryMinDate = minDate;
  filters.inventoryMaxDate = maxDate;

  const defaults = DEFAULT_RETAILERS.filter((name) => retailers.includes(name));
  filters.selectedRetailers.length = 0;
  filters.selectedRetailers.push(...(defaults.length ? defaults : retailers.slice(0, Math.min(3, retailers.length))));

  const min = parseDate(minDate);
  const max = parseDate(maxDate);
  if (min && max) {
    const defaultStart = new Date(max.getTime() - 60 * 24 * 60 * 60 * 1000);
    const start = defaultStart < min ? min : defaultStart;
    filters.startDate = toInputDate(start);
    filters.endDate = toInputDate(max);
  } else {
    filters.startDate = null;
    filters.endDate = null;
  }
  filters.inventoryReady = true;
}

/** Build the common filter params reactively from the current state. */
export function buildCommonParams(): CommonFilterParams {
  return {
    retailer: [...filters.selectedRetailers],
    start_date: filters.startDate ?? undefined,
    end_date: filters.endDate ?? undefined,
    max_files: filters.allHistory ? 0 : filters.maxFiles,
    all_history: filters.allHistory
  };
}

/** Serialized param map for the API (empty strings are dropped by the client). */
export function buildQueryMap(): Record<string, unknown> {
  return {
    retailer: [...filters.selectedRetailers],
    start_date: filters.startDate ?? '',
    end_date: filters.endDate ?? '',
    max_files: filters.allHistory ? 0 : filters.maxFiles,
    all_history: filters.allHistory
  };
}

function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

function toInputDate(date: Date): string {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, '0');
  const d = String(date.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}
