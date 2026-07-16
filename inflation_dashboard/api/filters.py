from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any

import pandas as pd

from inflation_dashboard.adapters.csv_price_repository import (
    DEFAULT_MAX_FILES_PER_RETAILER,
    DEFAULT_RETAILERS,
    discover_csv_inventory,
    load_price_history,
)
from inflation_dashboard.application.use_cases import list_inventory_filters
from inflation_dashboard.api.serialization import json_safe_mapping

UNCAPPED_WARNING = "all_history requested; CSV load is uncapped"


class ApiFilterError(ValueError):
    """HTTP-400-ready filter validation error."""

    def __init__(self, code: str, message: str, meta: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.meta = meta or {}


@dataclass(frozen=True)
class ParsedFilters:
    selected_retailers: list[str]
    start_date: date | None
    end_date: date | None
    max_files_per_retailer: int
    all_history: bool
    meta: dict[str, object]
    inventory: pd.DataFrame


@lru_cache(maxsize=1)
def get_inventory() -> pd.DataFrame:
    """Return cached CSV inventory for API filter discovery."""

    return discover_csv_inventory()


def clear_inventory_cache() -> None:
    """Clear cached inventory for tests and one-off verification scripts."""

    get_inventory.cache_clear()


def parse_bool_param(req: Any, name: str, default: bool = False) -> bool:
    raw_value = req.get_param(name, default=None)
    if raw_value is None or raw_value == "":
        return default
    normalized = str(raw_value).strip().casefold()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ApiFilterError("invalid_filter", f"Invalid {name}", meta={"filters": {name: raw_value}})


def parse_common_filters(req: Any) -> ParsedFilters:
    inventory = get_inventory()
    inventory_filters = list_inventory_filters(inventory)
    available_retailers = list(inventory_filters.get("retailers") or [])

    requested_retailers = req.get_param_as_list("retailer") or []
    requested_retailers = [retailer for retailer in requested_retailers if retailer]
    unknown_retailers = sorted(set(requested_retailers) - set(available_retailers))
    if unknown_retailers:
        unknown = unknown_retailers[0]
        raise ApiFilterError(
            "invalid_filter",
            f"Unknown retailer: {unknown}",
            meta={"filters": {"retailer": requested_retailers}},
        )

    if requested_retailers:
        selected_retailers = requested_retailers
    else:
        selected_retailers = [retailer for retailer in DEFAULT_RETAILERS if retailer in available_retailers]
        if not selected_retailers:
            selected_retailers = available_retailers[: min(3, len(available_retailers))]

    min_date = _as_date(inventory_filters.get("min_date"))
    max_date = _as_date(inventory_filters.get("max_date"))
    default_start = None
    if min_date and max_date:
        default_start = max(min_date, (pd.Timestamp(max_date) - pd.Timedelta(days=60)).date())

    start_date = _parse_date_param(req, "start_date", default_start)
    end_date = _parse_date_param(req, "end_date", max_date)
    if start_date and end_date and start_date > end_date:
        raise ApiFilterError(
            "invalid_filter",
            "Invalid date range",
            meta={"filters": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}},
        )

    all_history = parse_bool_param(req, "all_history")
    max_files_per_retailer = _parse_max_files(req)
    if all_history or max_files_per_retailer == 0:
        effective_max_files = 0
        all_history = True
    else:
        effective_max_files = max_files_per_retailer

    selected_inventory_file_count = _selected_inventory_file_count(
        inventory,
        selected_retailers,
        start_date,
        end_date,
        effective_max_files,
    )
    warnings = [UNCAPPED_WARNING] if all_history else []
    meta = {
        "filters": {
            "selected_retailers": selected_retailers,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "max_files_per_retailer": effective_max_files,
            "all_history": all_history,
        },
        "inventory_file_count": int(inventory_filters.get("file_count") or 0),
        "selected_inventory_file_count": selected_inventory_file_count,
        "warnings": warnings,
    }
    return ParsedFilters(
        selected_retailers=selected_retailers,
        start_date=start_date,
        end_date=end_date,
        max_files_per_retailer=effective_max_files,
        all_history=all_history,
        meta=json_safe_mapping(meta),
        inventory=inventory,
    )


def load_filtered_history(parsed_filters: ParsedFilters) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    history, skipped = load_price_history(
        tuple(parsed_filters.selected_retailers),
        parsed_filters.start_date,
        parsed_filters.end_date,
        parsed_filters.max_files_per_retailer,
        inventory=parsed_filters.inventory,
    )
    warnings = list(parsed_filters.meta.get("warnings", []))
    if history.empty and len(skipped) > 0 and parsed_filters.meta.get("selected_inventory_file_count", 0):
        warnings.append("selected files skipped; no usable rows loaded")
    meta = {
        **parsed_filters.meta,
        "history_row_count": int(len(history)),
        "skipped_file_count": int(len(skipped)),
        "warnings": warnings,
    }
    return history, skipped, meta


def _parse_date_param(req: Any, name: str, default: date | None) -> date | None:
    raw_value = req.get_param(name, default=None)
    if raw_value in {None, ""}:
        return default
    try:
        return date.fromisoformat(str(raw_value))
    except ValueError as exc:
        raise ApiFilterError("invalid_filter", "Invalid date", meta={"filters": {name: raw_value}}) from exc


def _parse_max_files(req: Any) -> int:
    raw_value = req.get_param("max_files", default=None)
    if raw_value in {None, ""}:
        return DEFAULT_MAX_FILES_PER_RETAILER
    try:
        max_files = int(str(raw_value))
    except ValueError as exc:
        raise ApiFilterError("invalid_filter", "Invalid max_files", meta={"filters": {"max_files": raw_value}}) from exc
    if max_files < 0:
        raise ApiFilterError("invalid_filter", "Invalid max_files", meta={"filters": {"max_files": raw_value}})
    return max_files


def _as_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _selected_inventory_file_count(
    inventory: pd.DataFrame,
    selected_retailers: list[str],
    start_date: date | None,
    end_date: date | None,
    max_files_per_retailer: int,
) -> int:
    if inventory.empty or not selected_retailers or start_date is None or end_date is None:
        return 0
    selected = inventory[
        inventory["retailer"].isin(selected_retailers)
        & (inventory["date"] >= pd.to_datetime(start_date))
        & (inventory["date"] <= pd.to_datetime(end_date))
    ].copy()
    if max_files_per_retailer > 0:
        selected = (
            selected.sort_values(["retailer", "date"], ascending=[True, False])
            .groupby("retailer", group_keys=False)
            .head(max_files_per_retailer)
        )
    return int(len(selected))
