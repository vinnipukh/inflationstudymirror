"""
ASGI resource handlers (high-scale principles 1, 3, 8, 10).

Synchronous twins live in ``resources.py`` (WSGI path, unchanged). These
handlers:

* are pure -- request-scoped state lives in ``req.context`` only (1);
* await non-blocking DB reads through async_price_repository (10);
* run pandas aggregation and heavy JSON serialization in a worker thread via
  ``asyncio.to_thread`` so the event loop never blocks (10);
* serve pre-serialized bytes from the L1 (in-process) / L2 (Redis) response
  cache with ETag/304 semantics (3);
* use cursor-based (keyset) pagination on list endpoints (8);
* push fire-and-forget offload events for expensive computations (4).
"""

from __future__ import annotations

import asyncio
from typing import Any

import falcon
import orjson

from inflation_dashboard.adapters import async_price_repository
from inflation_dashboard.api.cache_aside import get_response as redis_get_response
from inflation_dashboard.api.cache_aside import set_response as redis_set_response
from inflation_dashboard.api.filters import (
    ApiFilterError,
    get_cached_response,
    get_inventory,
    load_filtered_history,
    make_etag,
    parse_common_filters,
    put_cached_response,
)
from inflation_dashboard.api.pagination import decode_cursor, encode_cursor, page_meta
from inflation_dashboard.api.serialization import envelope, error_envelope, json_safe_mapping, records_from_frame
from inflation_dashboard.application.chart_specs import (
    BIGGEST_DROPS_COLUMNS,
    BIGGEST_GAINS_COLUMNS,
    CATEGORY_COVERAGE_COLUMNS,
    COVERAGE_OVER_TIME_COLUMNS,
    PRODUCT_HISTORY_COLUMNS,
    RETAILER_AVERAGE_COLUMNS,
    SKIPPED_DIAGNOSTICS_COLUMNS,
)
from inflation_dashboard.application.use_cases import (
    calculate_category_coverage,
    calculate_coverage_over_time,
    calculate_coverage_summary,
    calculate_price_movers,
    calculate_retailer_average_trends,
    get_product_history,
    list_inventory_filters,
    summarize_product_history,
)
from inflation_dashboard.domain.prices import HISTORY_COLUMNS

_OFFLOAD_ENABLED = True  # env FALCON_OFFLOAD_ENABLED checked at call time


# --- shared response plumbing ---------------------------------------------
def _accepts_gzip(req: Any) -> bool:
    header = req.get_header("Accept-Encoding")
    if not header:
        return False
    best_quality = 0.0
    for part in header.split(","):
        token = part.strip()
        quality = 1.0
        if ";" in token:
            token, _, parameters = token.partition(";")
            token = token.strip()
            for parameter in parameters.split(";"):
                parameter = parameter.strip()
                if parameter.lower().startswith("q="):
                    try:
                        quality = float(parameter[2:])
                    except ValueError:
                        quality = 0.0
        if token.lower() == "gzip":
            best_quality = max(best_quality, quality)
    return best_quality > 0.0


def _etag_matches(req: Any, etag_value: str) -> bool:
    etags = req.if_none_match
    if not etags:
        return False
    for etag in etags:
        if etag == "*" or etag == etag_value:
            return True
    return False


def _emit_cached_response(resp: Any, req: Any, body: bytes, etag_value: str, encoding: str | None, *, vary: bool) -> None:
    """Serve pre-serialized bytes with ETag/304. Cache-Control is owned by
    CacheControlMiddleware (edge-cache headers stay centralized)."""
    if _etag_matches(req, etag_value):
        resp.status = falcon.HTTP_304
        resp.etag = etag_value
        if vary:
            resp.vary = ["Accept-Encoding"]
        return
    resp.status = falcon.HTTP_200
    resp.etag = etag_value
    resp.data = body
    resp.content_type = falcon.MEDIA_JSON
    if encoding:
        resp.set_header("Content-Encoding", encoding)
    if vary:
        resp.vary = ["Accept-Encoding"]


async def _serve_cached_any(req: Any, resp: Any, endpoint: str, query_string: str) -> bool:
    """Serve from L1 (in-process) then L2 (shared Redis); True when served."""
    cached = get_cached_response(endpoint, query_string)
    if cached is None:
        store = getattr(req.context, "store", None)
        if store is not None:
            cached = await redis_get_response(store, endpoint, query_string)
    if cached is None:
        return False
    raw_bytes, gzip_bytes, etag, gzip_etag = cached
    req.context["_cache_hit"] = True
    if gzip_bytes is not None and _accepts_gzip(req):
        body, body_etag, encoding = gzip_bytes, gzip_etag, "gzip"
    else:
        body, body_etag, encoding = raw_bytes, etag, None
    _emit_cached_response(resp, req, body, body_etag, encoding, vary=gzip_bytes is not None)
    return True


async def _offload_computed(req: Any, endpoint: str, query_string: str, byte_len: int) -> None:
    """Fire-and-forget offload event for expensive computed responses (4)."""
    import os

    if os.environ.get("FALCON_OFFLOAD_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return
    store = getattr(req.context, "store", None)
    if store is None or store.backend_name == "memory":
        return
    try:
        await store.enqueue(
            "falcon:events",
            {
                "event": "api.response_computed",
                "endpoint": endpoint,
                "query": query_string[:200],
                "bytes": byte_len,
            },
        )
    except Exception:
        pass


async def _compute_send(req: Any, resp: Any, endpoint: str, query_string: str, envelope_dict: dict[str, object]) -> None:
    """Serialize once (worker thread), populate L1 + L2, and serve 200/304."""
    try:
        raw_bytes: bytes = await asyncio.to_thread(orjson.dumps, envelope_dict)

        async def _populate_caches() -> None:
            await asyncio.to_thread(put_cached_response, endpoint, query_string, raw_bytes)
            store = getattr(req.context, "store", None)
            if store is not None:
                await redis_set_response(store, endpoint, query_string, raw_bytes)

        await _populate_caches()
        if not await _serve_cached_any(req, resp, endpoint, query_string):
            _emit_cached_response(resp, req, raw_bytes, make_etag(raw_bytes), None, vary=False)
        req.context["_cache_hit"] = False
        if endpoint in {"/api/history", "/api/movers", "/api/coverage", "/api/retailer-averages"}:
            await _offload_computed(req, endpoint, query_string, len(raw_bytes))
    except Exception:
        resp.status = falcon.HTTP_200
        resp.media = envelope_dict


def _set_filter_error(resp: Any, exc: ApiFilterError) -> None:
    resp.status = falcon.HTTP_400
    resp.media = error_envelope(exc.code, exc.message, meta=exc.meta)


def _single_selected_retailer(selected_retailers: list[str]) -> str:
    if len(selected_retailers) == 1:
        return selected_retailers[0]
    raise ApiFilterError(
        "invalid_filter",
        "product_retailer is required",
        meta={"filters": {"selected_retailers": selected_retailers}},
    )


def _parse_bounded_int(req: Any, name: str, *, default: int, minimum: int, maximum: int | None = None) -> int:
    raw_value = req.get_param(name, default=None)
    if raw_value in {None, ""}:
        return default
    try:
        parsed_value = int(str(raw_value))
    except ValueError as exc:
        raise ApiFilterError("invalid_filter", f"Invalid {name}", meta={"filters": {name: raw_value}}) from exc
    if parsed_value < minimum or (maximum is not None and parsed_value > maximum):
        raise ApiFilterError("invalid_filter", f"Invalid {name}", meta={"filters": {name: raw_value}})
    return parsed_value


async def _inventory_frame() -> Any:
    """Async inventory discovery: SQLite via async engine, CSV via threads."""
    if async_price_repository.is_sqlite_db_available():
        try:
            return await async_price_repository.async_discover_inventory()
        except Exception:
            pass
    return await asyncio.to_thread(get_inventory)


# --- resources -------------------------------------------------------------
class HealthResource:
    async def on_get(self, req: Any, resp: Any) -> None:
        resp.status = falcon.HTTP_200
        resp.media = envelope(
            {"status": "ok"},
            meta={
                "service": "inflation-dashboard-api",
                "interface": "asgi",
                "store_backend": getattr(req.context, "store_backend", None),
            },
        )


class InventoryResource:
    async def on_get(self, req: Any, resp: Any) -> None:
        if await _serve_cached_any(req, resp, "/api/inventory", req.query_string):
            return
        inventory = await _inventory_frame()
        filters = await asyncio.to_thread(list_inventory_filters, inventory)
        envelope_dict = envelope(
            {
                "retailers": filters["retailers"],
                "min_date": filters["min_date"],
                "max_date": filters["max_date"],
            },
            meta={"file_count": filters["file_count"], "inventory_file_count": filters["file_count"]},
        )
        await _compute_send(req, resp, "/api/inventory", req.query_string, envelope_dict)


class HistoryResource:
    async def on_get(self, req: Any, resp: Any) -> None:
        try:
            if await _serve_cached_any(req, resp, "/api/history", req.query_string):
                return

            product_name = req.get_param("product_name", default=None)
            product_retailer = req.get_param("product_retailer", default=None)

            def compute() -> dict[str, object]:
                parsed_filters = parse_common_filters(req)
                history, skipped, meta = load_filtered_history(parsed_filters)
                if product_name:
                    retailer = product_retailer or _single_selected_retailer(parsed_filters.selected_retailers)
                    product_history = get_product_history(history, retailer, product_name)
                    data = {
                        "history": records_from_frame(product_history, PRODUCT_HISTORY_COLUMNS),
                        "summary": json_safe_mapping(summarize_product_history(product_history)),
                    }
                    meta = {**meta, "product_name": product_name, "product_retailer": retailer}
                else:
                    data = {"history": records_from_frame(history, HISTORY_COLUMNS)}
                    if parsed_filters.all_history or len(history) > 5000:
                        meta = {**meta, "warnings": [*meta.get("warnings", []), "history response may be large"]}
                return envelope(data, meta=meta)

            envelope_dict = await asyncio.to_thread(compute)
            await _compute_send(req, resp, "/api/history", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class RetailerAveragesResource:
    async def on_get(self, req: Any, resp: Any) -> None:
        try:
            if await _serve_cached_any(req, resp, "/api/retailer-averages", req.query_string):
                return

            aggregation = req.get_param("aggregation", default="Average")
            if aggregation not in {"Average", "Median"}:
                raise ApiFilterError(
                    "invalid_filter",
                    "Invalid aggregation",
                    meta={"filters": {"aggregation": aggregation}},
                )

            def compute() -> dict[str, object]:
                parsed_filters = parse_common_filters(req)
                history, skipped, meta = load_filtered_history(parsed_filters)
                trends = calculate_retailer_average_trends(history, parsed_filters.selected_retailers, aggregation)
                records = records_from_frame(trends, RETAILER_AVERAGE_COLUMNS)
                return envelope(
                    {"records": records, "retailer_averages": records},
                    meta={**meta, "aggregation": aggregation, "skipped_file_count": len(skipped)},
                )

            envelope_dict = await asyncio.to_thread(compute)
            await _compute_send(req, resp, "/api/retailer-averages", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class MoversResource:
    async def on_get(self, req: Any, resp: Any) -> None:
        try:
            if await _serve_cached_any(req, resp, "/api/movers", req.query_string):
                return

            scope_retailer = req.get_param("scope_retailer", default="All retailers")
            limit = _parse_bounded_int(
                req,
                "limit",
                default=_parse_bounded_int(req, "mover_count", default=10, minimum=5, maximum=30),
                minimum=5,
                maximum=30,
            )

            def compute() -> dict[str, object]:
                parsed_filters = parse_common_filters(req)
                history, skipped, meta = load_filtered_history(parsed_filters)
                if scope_retailer != "All retailers" and scope_retailer not in parsed_filters.selected_retailers:
                    raise ApiFilterError(
                        "invalid_filter",
                        f"Unknown retailer: {scope_retailer}",
                        meta={"filters": {"scope_retailer": scope_retailer}},
                    )
                mover_results = calculate_price_movers(history, scope_retailer, limit)
                stats = mover_results["stats"]
                return envelope(
                    {
                        "biggest_drops": records_from_frame(mover_results["biggest_drops"], BIGGEST_DROPS_COLUMNS),
                        "biggest_gains": records_from_frame(mover_results["biggest_gains"], BIGGEST_GAINS_COLUMNS),
                    },
                    meta={
                        **meta,
                        "scope_retailer": scope_retailer,
                        "limit": limit,
                        "eligible_product_count": int(len(stats)),
                        "skipped_file_count": len(skipped),
                    },
                )

            envelope_dict = await asyncio.to_thread(compute)
            await _compute_send(req, resp, "/api/movers", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class CoverageResource:
    async def on_get(self, req: Any, resp: Any) -> None:
        try:
            if await _serve_cached_any(req, resp, "/api/coverage", req.query_string):
                return

            category_limit = _parse_bounded_int(req, "category_limit", default=20, minimum=1)

            def compute() -> dict[str, object]:
                parsed_filters = parse_common_filters(req)
                history, skipped, meta = load_filtered_history(parsed_filters)
                summary = calculate_coverage_summary(history, skipped)
                coverage_over_time = calculate_coverage_over_time(history)
                category_coverage = calculate_category_coverage(history, limit=category_limit)
                return envelope(
                    {
                        "summary": summary,
                        "coverage_over_time": records_from_frame(coverage_over_time, COVERAGE_OVER_TIME_COLUMNS),
                        "category_coverage": records_from_frame(category_coverage, CATEGORY_COVERAGE_COLUMNS),
                        "skipped_files": records_from_frame(skipped, SKIPPED_DIAGNOSTICS_COLUMNS),
                    },
                    meta={**meta, "category_limit": category_limit, "skipped_file_count": len(skipped)},
                )

            envelope_dict = await asyncio.to_thread(compute)
            await _compute_send(req, resp, "/api/coverage", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class ProductSearchResource:
    """Fast product autocomplete/search with cursor-based pagination."""

    async def on_get(self, req: Any, resp: Any) -> None:
        try:
            if await _serve_cached_any(req, resp, "/api/products/search", req.query_string):
                return

            query = (req.get_param("q") or req.get_param("query") or "").strip()
            retailer = req.get_param("retailer", default=None)
            category = req.get_param("category", default=None)
            limit = _parse_bounded_int(req, "limit", default=20, minimum=1, maximum=100)
            cursor_token = req.get_param("cursor", default=None)
            cursor = decode_cursor(cursor_token, required_fields=("oc", "pid"))

            results: list[dict[str, object]] = []
            next_cursor_payload: dict[str, object] | None = None
            if async_price_repository.is_sqlite_db_available():
                try:
                    results, next_cursor_payload = await async_price_repository.async_search_products(
                        query=query, retailer=retailer, category=category, limit=limit, cursor=cursor
                    )
                except ValueError as exc:
                    raise ApiFilterError(
                        "invalid_cursor",
                        "The cursor parameter is malformed or expired; restart pagination from the first page.",
                    ) from exc
            else:
                results = []

            next_cursor = encode_cursor(next_cursor_payload) if next_cursor_payload else None
            meta: dict[str, object] = {
                "query": query,
                "retailer": retailer,
                "category": category,
                "limit": limit,
                "count": len(results),
                **page_meta(used_cursor=cursor_token, next_cursor=next_cursor, limit=limit, count=len(results)),
            }
            envelope_dict = envelope(results, meta=meta)
            await _compute_send(req, resp, "/api/products/search", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)
        except Exception as exc:
            resp.status = falcon.HTTP_500
            resp.media = error_envelope("server_error", str(exc))


class ProductDetailResource:
    """Async product detail (price history) backed by product_prices."""

    async def on_get(self, req: Any, resp: Any) -> None:
        try:
            if await _serve_cached_any(req, resp, "/api/product", req.query_string):
                return

            product_id = req.get_param("product_id", default=None)
            retailer = req.get_param("retailer", default=None)
            product_name = req.get_param("product_name", default=None)

            lookup_key = product_id or product_name
            if not lookup_key:
                raise ApiFilterError(
                    "invalid_filter",
                    "product_id or product_name is required",
                    meta={"filters": {"product_id": product_id, "product_name": product_name}},
                )

            detail: dict[str, object] | None = None
            if async_price_repository.is_sqlite_db_available():
                try:
                    detail = await async_price_repository.async_get_product_detail(product_id=lookup_key, retailer=retailer)
                except Exception:
                    detail = None

            if not detail:
                resp.status = falcon.HTTP_404
                resp.media = error_envelope(
                    "not_found",
                    f"Product not found: {lookup_key}",
                    meta={"product_id": product_id, "product_name": product_name, "retailer": retailer},
                )
                return

            meta = {
                "product_id": detail.get("product_id"),
                "retailer": detail.get("retailer"),
                "observations_count": detail.get("observations_count", 0),
            }
            envelope_dict = envelope(detail, meta=meta)
            await _compute_send(req, resp, "/api/product", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)
        except Exception as exc:
            resp.status = falcon.HTTP_500
            resp.media = error_envelope("server_error", str(exc))
