import { filters, DEFAULT_API_BASE_URL } from '$lib/stores/filters.svelte';

/**
 * Build-time default API origin (for display). Requests use the live
 * `apiBaseUrl` from the filter store, which starts from this value.
 */
export const API_BASE_URL: string = DEFAULT_API_BASE_URL;

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
 * Serializes filter params into URLSearchParams handling array fields.
 */
export function buildQueryParams(params: Record<string, unknown>): URLSearchParams {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== '' && item !== null && item !== undefined) query.append(key, String(item));
      }
    } else if (typeof value === 'boolean') {
      query.set(key, String(value));
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
  params?: Record<string, unknown>,
  fetchFn: typeof fetch = fetch
): Promise<{ data: T; meta: M }> {
  const base = (filters.apiBaseUrl || DEFAULT_API_BASE_URL).replace(/\/+$/, '');
  const queryString = params ? `?${buildQueryParams(params).toString()}` : '';
  const url = `${base}${endpoint}${queryString}`;

  let res: Response;
  try {
    res = await fetchFn(url, {
      headers: {
        Accept: 'application/json'
      }
    });
  } catch (err) {
    const detail = err instanceof TypeError ? 'network error (is the Falcon API running?)' : String(err);
    throw new ApiErrorResponse(0, 'network_error', `API request to ${endpoint} failed: ${detail}`);
  }

  let payload: Record<string, unknown>;
  try {
    payload = await res.json();
  } catch {
    throw new ApiErrorResponse(res.status, 'bad_response', `API response from ${endpoint} was not valid JSON.`);
  }

  if (!res.ok) {
    const errors = Array.isArray(payload?.errors) ? payload.errors : [];
    const error = (errors[0] as Record<string, unknown> | undefined) || {
      code: 'http_error',
      message: `Request failed with status ${res.status}`
    };
    throw new ApiErrorResponse(
      res.status,
      String(error.code),
      String(error.message),
      (error.meta as Record<string, unknown>) || (payload.meta as Record<string, unknown>)
    );
  }

  return payload as { data: T; meta: M };
}
