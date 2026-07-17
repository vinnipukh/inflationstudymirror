from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import requests

DEFAULT_API_BASE_URL = "http://localhost:8000"
FRONTEND_DEFAULT_RETAILERS = ("Markets / Gurmar", "ClothingStores / Vakko", "HomeGoods")
FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER = 45
SHORT_TIMEOUT_SECONDS = 10
DATA_TIMEOUT_SECONDS = 60
ENVELOPE_KEYS = {"data", "meta", "errors"}

ParamValue = str | int | bool | None
QueryParams = list[tuple[str, ParamValue]]


class ApiClientError(RuntimeError):
    """Display-safe error raised when the Falcon API cannot be consumed."""

    def __init__(self, message: str, *, status_code: int | None = None, meta: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.meta = meta or {}


@dataclass(frozen=True)
class ApiEnvelope:
    """Validated Falcon API envelope."""

    data: Any
    meta: dict[str, Any]
    errors: list[Any]


@dataclass(frozen=True)
class DashboardFilters:
    """Shared dashboard filters serialized to Falcon common query parameters."""

    selected_retailers: tuple[str, ...]
    start_date: date | str | None
    end_date: date | str | None
    max_files: int = FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER
    all_history: bool = False


def normalize_api_base_url(api_base_url: str) -> str:
    """Normalize a user-entered Falcon API base URL."""

    normalized = (api_base_url or DEFAULT_API_BASE_URL).strip().rstrip("/")
    return normalized or DEFAULT_API_BASE_URL


def _date_to_iso(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def build_common_params(filters: DashboardFilters) -> QueryParams:
    """Build common Falcon query params, preserving repeated retailer pairs."""

    params: QueryParams = []
    for retailer in filters.selected_retailers:
        params.append(("retailer", retailer))

    start_date = _date_to_iso(filters.start_date)
    end_date = _date_to_iso(filters.end_date)
    if start_date:
        params.append(("start_date", start_date))
    if end_date:
        params.append(("end_date", end_date))

    effective_max_files = 0 if filters.all_history else int(filters.max_files)
    params.append(("max_files", effective_max_files))
    params.append(("all_history", str(bool(filters.all_history)).lower()))
    return params


def _validate_envelope(payload: Any, *, status_code: int | None = None) -> ApiEnvelope:
    if not isinstance(payload, dict):
        raise ApiClientError("API response was not a JSON object.", status_code=status_code)

    actual_keys = set(payload.keys())
    if actual_keys != ENVELOPE_KEYS:
        missing = ", ".join(sorted(ENVELOPE_KEYS - actual_keys)) or "none"
        extra = ", ".join(sorted(actual_keys - ENVELOPE_KEYS)) or "none"
        raise ApiClientError(
            f"API response was not a valid envelope (missing: {missing}; extra: {extra}).",
            status_code=status_code,
        )

    meta = payload["meta"]
    errors = payload["errors"]
    if not isinstance(meta, dict):
        raise ApiClientError("API envelope meta must be an object.", status_code=status_code)
    if not isinstance(errors, list):
        raise ApiClientError("API envelope errors must be a list.", status_code=status_code, meta=meta)
    if errors:
        first_error = errors[0]
        if isinstance(first_error, dict):
            message = str(first_error.get("message") or first_error.get("code") or "API returned an error.")
        else:
            message = str(first_error)
        raise ApiClientError(message, status_code=status_code, meta=meta)

    return ApiEnvelope(data=payload["data"], meta=meta, errors=errors)


def fetch_endpoint(
    api_base_url: str,
    endpoint_path: str,
    params: QueryParams | tuple[tuple[str, ParamValue], ...] | None = None,
    *,
    timeout: int = DATA_TIMEOUT_SECONDS,
) -> ApiEnvelope:
    """Fetch and validate a Falcon API endpoint.

    `params` is intentionally list-of-pairs compatible so repeated `retailer`
    values are not collapsed into a comma-joined string.
    """

    base_url = normalize_api_base_url(api_base_url)
    path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
    url = f"{base_url}{path}"
    request_params = list(params or [])

    try:
        response = requests.get(url, params=request_params, timeout=timeout)
    except requests.Timeout as exc:
        raise ApiClientError(f"API request to {path} timed out after {timeout} seconds.") from exc
    except requests.RequestException as exc:
        raise ApiClientError(f"API request to {path} failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ApiClientError(
            f"API response from {path} was not valid JSON.",
            status_code=response.status_code,
        ) from exc

    try:
        envelope = _validate_envelope(payload, status_code=response.status_code)
    except ApiClientError:
        raise

    if not 200 <= response.status_code < 300:
        raise ApiClientError(
            f"API request to {path} returned HTTP {response.status_code}.",
            status_code=response.status_code,
            meta=envelope.meta,
        )

    return envelope


def fetch_health(api_base_url: str) -> ApiEnvelope:
    return fetch_endpoint(api_base_url, "/api/health", timeout=SHORT_TIMEOUT_SECONDS)


def fetch_inventory(api_base_url: str) -> ApiEnvelope:
    return fetch_endpoint(api_base_url, "/api/inventory", timeout=SHORT_TIMEOUT_SECONDS)


def fetch_history(
    api_base_url: str,
    filters: DashboardFilters,
    product_name: str | None = None,
    product_retailer: str | None = None,
) -> ApiEnvelope:
    params = build_common_params(filters)
    if product_name:
        params.append(("product_name", product_name))
    if product_retailer:
        params.append(("product_retailer", product_retailer))
    return fetch_endpoint(api_base_url, "/api/history", params, timeout=DATA_TIMEOUT_SECONDS)


def fetch_retailer_averages(api_base_url: str, filters: DashboardFilters, aggregation: str = "Average") -> ApiEnvelope:
    params = build_common_params(filters)
    params.append(("aggregation", aggregation))
    return fetch_endpoint(api_base_url, "/api/retailer-averages", params, timeout=DATA_TIMEOUT_SECONDS)


def fetch_movers(api_base_url: str, filters: DashboardFilters, scope_retailer: str = "All retailers", limit: int = 10) -> ApiEnvelope:
    params = build_common_params(filters)
    params.extend([("scope_retailer", scope_retailer), ("limit", limit)])
    return fetch_endpoint(api_base_url, "/api/movers", params, timeout=DATA_TIMEOUT_SECONDS)


def fetch_coverage(api_base_url: str, filters: DashboardFilters, category_limit: int = 20) -> ApiEnvelope:
    params = build_common_params(filters)
    params.append(("category_limit", category_limit))
    return fetch_endpoint(api_base_url, "/api/coverage", params, timeout=DATA_TIMEOUT_SECONDS)
