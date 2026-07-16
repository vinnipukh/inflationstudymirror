from __future__ import annotations

from typing import Any

import falcon

from inflation_dashboard.api.filters import ApiFilterError, get_inventory, load_filtered_history, parse_common_filters
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


class HealthResource:
    def on_get(self, req: Any, resp: Any) -> None:
        resp.status = falcon.HTTP_200
        resp.media = envelope({"status": "ok"}, meta={"service": "inflation-dashboard-api"})


class InventoryResource:
    def on_get(self, req: Any, resp: Any) -> None:
        inventory = get_inventory()
        filters = list_inventory_filters(inventory)
        resp.status = falcon.HTTP_200
        resp.media = envelope(
            {
                "retailers": filters["retailers"],
                "min_date": filters["min_date"],
                "max_date": filters["max_date"],
            },
            meta={"file_count": filters["file_count"], "inventory_file_count": filters["file_count"]},
        )


class HistoryResource:
    def on_get(self, req: Any, resp: Any) -> None:
        try:
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
            resp.status = falcon.HTTP_200
            resp.media = envelope(data, meta=meta)
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class RetailerAveragesResource:
    def on_get(self, req: Any, resp: Any) -> None:
        try:
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
            resp.status = falcon.HTTP_200
            resp.media = envelope(
                {"retailer_averages": records_from_frame(trends, RETAILER_AVERAGE_COLUMNS)},
                meta={**meta, "aggregation": aggregation, "skipped_file_count": len(skipped)},
            )
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class MoversResource:
    def on_get(self, req: Any, resp: Any) -> None:
        try:
            parsed_filters = parse_common_filters(req)
            history, skipped, meta = load_filtered_history(parsed_filters)
            scope_retailer = req.get_param("scope_retailer", default="All retailers")
            if scope_retailer != "All retailers" and scope_retailer not in parsed_filters.selected_retailers:
                raise ApiFilterError(
                    "invalid_filter",
                    f"Unknown retailer: {scope_retailer}",
                    meta={"filters": {"scope_retailer": scope_retailer}},
                )
            limit = _parse_positive_int(req, "limit", default=10, minimum=1)
            mover_results = calculate_price_movers(history, scope_retailer, limit)
            stats = mover_results["stats"]
            resp.status = falcon.HTTP_200
            resp.media = envelope(
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
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


class CoverageResource:
    def on_get(self, req: Any, resp: Any) -> None:
        try:
            parsed_filters = parse_common_filters(req)
            history, skipped, meta = load_filtered_history(parsed_filters)
            category_limit = _parse_positive_int(req, "category_limit", default=20, minimum=1)
            summary = calculate_coverage_summary(history, skipped)
            coverage_over_time = calculate_coverage_over_time(history)
            category_coverage = calculate_category_coverage(history, limit=category_limit)
            resp.status = falcon.HTTP_200
            resp.media = envelope(
                {
                    "summary": summary,
                    "coverage_over_time": records_from_frame(coverage_over_time, COVERAGE_OVER_TIME_COLUMNS),
                    "category_coverage": records_from_frame(category_coverage, CATEGORY_COVERAGE_COLUMNS),
                    "skipped_files": records_from_frame(skipped, SKIPPED_DIAGNOSTICS_COLUMNS),
                },
                meta={**meta, "category_limit": category_limit, "skipped_file_count": len(skipped)},
            )
        except ApiFilterError as exc:
            _set_filter_error(resp, exc)


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


def _parse_positive_int(req: Any, name: str, *, default: int, minimum: int) -> int:
    raw_value = req.get_param(name, default=None)
    if raw_value in {None, ""}:
        return default
    try:
        parsed_value = int(str(raw_value))
    except ValueError as exc:
        raise ApiFilterError("invalid_filter", f"Invalid {name}", meta={"filters": {name: raw_value}}) from exc
    if parsed_value < minimum:
        raise ApiFilterError("invalid_filter", f"Invalid {name}", meta={"filters": {name: raw_value}})
    return parsed_value
