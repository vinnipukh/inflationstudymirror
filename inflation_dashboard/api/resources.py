from __future__ import annotations

from typing import Any

import falcon
import orjson

from inflation_dashboard.api.filters import (
    RESPONSE_CACHE_TTL_SECONDS,
    ApiFilterError,
    get_cached_response,
    get_inventory,
    load_filtered_history,
    make_etag,
    parse_common_filters,
    put_cached_response,
)
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

try:
    from inflation_dashboard.adapters import sqlite_price_repository
except ImportError:
    sqlite_price_repository = None


def _accepts_gzip(req: Any) -> bool:
    """Return True when the client's Accept-Encoding permits a gzip response."""

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
    """RFC 7232 If-None-Match match (weak or strong; `*` is a wildcard match)."""

    etags = req.if_none_match
    if not etags:
        return False
    for etag in etags:
        if etag == "*" or etag == etag_value:
            return True
    return False


def _emit_cached_response(resp: Any, req: Any, body: bytes, etag_value: str, encoding: str | None, *, vary: bool) -> None:
    """Serve pre-serialized bytes with ETag/Cache-Control and optional gzip.

    Responds 304 Not Modified when the client already holds this representation
    (Falcon strips the body and Content-Type automatically for 304); otherwise
    200 with the payload body.
    """

    cache_control = ["public", f"max-age={RESPONSE_CACHE_TTL_SECONDS}"]
    if _etag_matches(req, etag_value):
        resp.status = falcon.HTTP_304
        resp.etag = etag_value
        resp.cache_control = cache_control
        if vary:
            resp.vary = ["Accept-Encoding"]
        return
    resp.status = falcon.HTTP_200
    resp.etag = etag_value
    resp.cache_control = cache_control
    resp.data = body
    resp.content_type = falcon.MEDIA_JSON
    if encoding:
        resp.set_header("Content-Encoding", encoding)
    if vary:
        resp.vary = ["Accept-Encoding"]


def _serve_cached(resp: Any, req: Any, endpoint: str, query_string: str) -> bool:
    """Serve the cached payload variant for this request; return True when served.

    Selects gzip vs raw from Accept-Encoding. Each variant carries its own
    strong ETag (a gzip representation is a different representation), and
    `Vary: Accept-Encoding` keeps shared caches honest.
    """

    cached = get_cached_response(endpoint, query_string)
    if cached is None:
        return False
    req.context["_cache_hit"] = True
    raw_bytes, gzip_bytes, etag, gzip_etag = cached
    if gzip_bytes is not None and _accepts_gzip(req):
        body, body_etag, encoding = gzip_bytes, gzip_etag, "gzip"
    else:
        body, body_etag, encoding = raw_bytes, etag, None
    _emit_cached_response(resp, req, body, body_etag, encoding, vary=gzip_bytes is not None)
    return True


def _send_response(resp: Any, req: Any, endpoint: str, query_string: str, envelope_dict: dict[str, object]) -> None:
    """Cache the pre-serialized response and serve it immediately (200 or 304)."""
    try:
        raw_bytes = orjson.dumps(envelope_dict)
        put_cached_response(endpoint, query_string, raw_bytes)
        if not _serve_cached(resp, req, endpoint, query_string):
            # Entry was evicted between put and get (rare under cache pressure);
            # serve the freshly serialized bytes without variant headers.
            _emit_cached_response(resp, req, raw_bytes, make_etag(raw_bytes), None, vary=False)
        # This response was computed just now, not served from a warm cache.
        req.context["_cache_hit"] = False
    except Exception:
        resp.status = falcon.HTTP_200
        resp.media = envelope_dict


class HealthResource:
    def on_get(self, req: Any, resp: Any) -> None:
        resp.status = falcon.HTTP_200
        resp.media = envelope({"status": "ok"}, meta={"service": "inflation-dashboard-api"})


class InventoryResource:
    def on_get(self, req: Any, resp: Any) -> None:
        if _serve_cached(resp, req, "inventory", req.query_string):
            return

        inventory = get_inventory()
        filters = list_inventory_filters(inventory)
        envelope_dict = envelope(
            {
                "retailers": filters["retailers"],
                "min_date": filters["min_date"],
                "max_date": filters["max_date"],
            },
            meta={"file_count": filters["file_count"], "inventory_file_count": filters["file_count"]},
        )
        _send_response(resp, req, "inventory", req.query_string, envelope_dict)


class HistoryResource:
    def on_get(self, req: Any, resp: Any) -> None:
        try:
            if _serve_cached(resp, req, "history", req.query_string):
                return

            parsed_filters = parse_common_filters(req)
            history, skipped, meta = load_filtered_history(parsed_filters)
            product_name = req.get_param("product_name", default=None)
            product_retailer = req.get_param("product_retailer", default=None)
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
            envelope_dict = envelope(data, meta=meta)
            _send_response(resp, req, "history", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class RetailerAveragesResource:
    def on_get(self, req: Any, resp: Any) -> None:
        try:
            if _serve_cached(resp, req, "retailer-averages", req.query_string):
                return

            aggregation = req.get_param("aggregation", default="Average")
            if aggregation not in {"Average", "Median"}:
                raise ApiFilterError(
                    "invalid_filter",
                    "Invalid aggregation",
                    meta={"filters": {"aggregation": aggregation}},
                )
            parsed_filters = parse_common_filters(req)
            history, skipped, meta = load_filtered_history(parsed_filters)
            trends = calculate_retailer_average_trends(history, parsed_filters.selected_retailers, aggregation)
            records = records_from_frame(trends, RETAILER_AVERAGE_COLUMNS)
            envelope_dict = envelope(
                {"records": records, "retailer_averages": records},
                meta={**meta, "aggregation": aggregation, "skipped_file_count": len(skipped)},
            )
            _send_response(resp, req, "retailer-averages", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class MoversResource:
    def on_get(self, req: Any, resp: Any) -> None:
        try:
            if _serve_cached(resp, req, "movers", req.query_string):
                return

            parsed_filters = parse_common_filters(req)
            history, skipped, meta = load_filtered_history(parsed_filters)
            scope_retailer = req.get_param("scope_retailer", default="All retailers")
            if scope_retailer != "All retailers" and scope_retailer not in parsed_filters.selected_retailers:
                raise ApiFilterError(
                    "invalid_filter",
                    f"Unknown retailer: {scope_retailer}",
                    meta={"filters": {"scope_retailer": scope_retailer}},
                )
            limit = _parse_bounded_int(
                req,
                "limit",
                default=_parse_bounded_int(req, "mover_count", default=10, minimum=5, maximum=30),
                minimum=5,
                maximum=30,
            )
            mover_results = calculate_price_movers(history, scope_retailer, limit)
            stats = mover_results["stats"]
            envelope_dict = envelope(
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
            _send_response(resp, req, "movers", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class CoverageResource:
    def on_get(self, req: Any, resp: Any) -> None:
        try:
            if _serve_cached(resp, req, "coverage", req.query_string):
                return

            parsed_filters = parse_common_filters(req)
            history, skipped, meta = load_filtered_history(parsed_filters)
            category_limit = _parse_bounded_int(req, "category_limit", default=20, minimum=1)
            summary = calculate_coverage_summary(history, skipped)
            coverage_over_time = calculate_coverage_over_time(history)
            category_coverage = calculate_category_coverage(history, limit=category_limit)
            envelope_dict = envelope(
                {
                    "summary": summary,
                    "coverage_over_time": records_from_frame(coverage_over_time, COVERAGE_OVER_TIME_COLUMNS),
                    "category_coverage": records_from_frame(category_coverage, CATEGORY_COVERAGE_COLUMNS),
                    "skipped_files": records_from_frame(skipped, SKIPPED_DIAGNOSTICS_COLUMNS),
                },
                meta={**meta, "category_limit": category_limit, "skipped_file_count": len(skipped)},
            )
            _send_response(resp, req, "coverage", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class ProductSearchResource:
    """Fast product autocomplete and search endpoint backed by product_prices."""

    def on_get(self, req: Any, resp: Any) -> None:
        try:
            if _serve_cached(resp, req, "products-search", req.query_string):
                return

            query = (req.get_param("q") or req.get_param("query") or "").strip()
            retailer = req.get_param("retailer", default=None)
            category = req.get_param("category", default=None)
            limit = _parse_bounded_int(req, "limit", default=20, minimum=1, maximum=100)

            results: list[dict[str, object]] = []
            if sqlite_price_repository is not None:
                try:
                    results = sqlite_price_repository.search_products(
                        query=query,
                        retailer=retailer,
                        category=category,
                        limit=limit,
                    )
                except Exception:
                    results = []

            meta = {
                "query": query,
                "retailer": retailer,
                "category": category,
                "limit": limit,
                "count": len(results),
            }
            envelope_dict = envelope(results, meta=meta)
            _send_response(resp, req, "products-search", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)
        except Exception as exc:
            resp.status = falcon.HTTP_500
            resp.media = error_envelope("server_error", str(exc))


class ProductDetailResource:
    """Fast product detail endpoint with price history backed by product_prices."""

    def on_get(self, req: Any, resp: Any) -> None:
        try:
            if _serve_cached(resp, req, "product-detail", req.query_string):
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
            if sqlite_price_repository is not None:
                try:
                    detail = sqlite_price_repository.get_product_price_history(
                        product_id=lookup_key,
                        retailer=retailer,
                    )
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
            _send_response(resp, req, "product-detail", req.query_string, envelope_dict)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)
        except Exception as exc:
            resp.status = falcon.HTTP_500
            resp.media = error_envelope("server_error", str(exc))


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
