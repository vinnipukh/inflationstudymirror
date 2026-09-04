from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import gzip
import hashlib
import threading
import time
from typing import Any

import pandas as pd

from inflation_dashboard.adapters.csv_price_repository import (
    DEFAULT_MAX_FILES_PER_RETAILER,
    DEFAULT_RETAILERS,
    clear_price_cache,
    discover_csv_inventory,
    load_price_history,
)
try:
    from inflation_dashboard.adapters import sqlite_price_repository
except ImportError:
    sqlite_price_repository = None

from inflation_dashboard.application.use_cases import list_inventory_filters
from inflation_dashboard.api.serialization import json_safe_mapping

UNCAPPED_WARNING = "all_history requested; CSV load is uncapped"


def is_sqlite_available() -> bool:
    """Return True if sqlite_price_repository is imported and prices.db exists and is non-empty."""
    if sqlite_price_repository is None:
        return False
    try:
        db_path = sqlite_price_repository.get_db_path()
        return db_path.is_file() and db_path.stat().st_size > 0
    except Exception:
        return False


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
    """Return cached CSV or SQLite inventory for API filter discovery.

    Uses sqlite_price_repository.discover_sqlite_inventory() when prices.db exists,
    falling back gracefully to csv_price_repository.discover_csv_inventory().
    """
    if is_sqlite_available():
        try:
            return sqlite_price_repository.discover_sqlite_inventory()
        except Exception:
            pass
    return discover_csv_inventory()


def clear_inventory_cache() -> None:
    """Clear cached inventory for tests and one-off verification scripts.

    Also clears the derived data caches (parsed filters, loaded history,
    per-file frames, response cache) because new/changed scraped data invalidates all of them.
    """

    get_inventory.cache_clear()
    clear_history_cache()
    clear_price_cache()
    clear_response_cache()
    if is_sqlite_available():
        try:
            sqlite_price_repository.clear_price_cache()
        except Exception:
            pass


# --- Server-side request caches --------------------------------------------------
# A single Streamlit rerun fires ~5 data requests with identical/overlapping
# filters (options, retailer averages, movers, coverage, product detail). Without
# caching every request re-reads and re-parses the same CSVs from disk (~4.4s for
# the default 3-retailer x 45-file selection). These stdlib-only TTL caches keep
# repeat requests in the millisecond range. Stdlib only (verifier boundary).

HISTORY_CACHE_TTL_SECONDS = 300
MAX_HISTORY_CACHE_BYTES = 300 * 1024 * 1024
MAX_HISTORY_FRAME_BYTES = 120 * 1024 * 1024
PARSE_CACHE_TTL_SECONDS = 300

_history_cache: "OrderedDict[tuple, tuple[float, pd.DataFrame, pd.DataFrame, int]]" = OrderedDict()
_parse_cache: "OrderedDict[tuple, tuple[float, ParsedFilters]]" = OrderedDict()
_data_cache_lock = threading.RLock()


def _history_cache_key(parsed_filters: ParsedFilters) -> tuple:
    return (
        tuple(parsed_filters.selected_retailers),
        parsed_filters.start_date.isoformat() if parsed_filters.start_date else None,
        parsed_filters.end_date.isoformat() if parsed_filters.end_date else None,
        parsed_filters.max_files_per_retailer,
        parsed_filters.all_history,
    )


def _history_cache_get(key: tuple) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    with _data_cache_lock:
        entry = _history_cache.get(key)
        if entry is None:
            return None
        timestamp, history, skipped, _ = entry
        if time.monotonic() - timestamp > HISTORY_CACHE_TTL_SECONDS:
            del _history_cache[key]
            return None
        _history_cache.move_to_end(key)
        return history, skipped


def _frame_size_estimate(frame: pd.DataFrame) -> int:
    """Cheap byte estimate: object/string columns ~64B/row, numeric ~16B/row.

    Used instead of `memory_usage(deep=True)`, which walks every string object
    and itself costs seconds on a 350k-row frame.
    """

    size = 0
    for column in frame.columns:
        if frame[column].dtype == object:
            size += len(frame) * 64
        else:
            size += len(frame) * 16
    return size


def _history_cache_put(key: tuple, history: pd.DataFrame, skipped: pd.DataFrame) -> None:
    if history.empty:
        return
    size_bytes = _frame_size_estimate(history)
    if size_bytes > MAX_HISTORY_FRAME_BYTES:
        return
    with _data_cache_lock:
        now = time.monotonic()
        for stale_key in [k for k, (ts, _, _, _) in _history_cache.items() if now - ts > HISTORY_CACHE_TTL_SECONDS]:
            del _history_cache[stale_key]
        total_bytes = sum(size for (_, _, _, size) in _history_cache.values())
        while _history_cache and total_bytes + size_bytes > MAX_HISTORY_CACHE_BYTES:
            _, _, _, oldest_size = _history_cache.popitem(last=False)
            total_bytes -= oldest_size
        _history_cache[key] = (now, history, skipped, size_bytes)
        _history_cache.move_to_end(key)


def _parse_cache_key(req: Any) -> tuple:
    return (
        tuple(req.get_param_as_list("retailer") or []),
        req.get_param("start_date", default=None),
        req.get_param("end_date", default=None),
        req.get_param("max_files", default=None),
        req.get_param("all_history", default=None),
    )


def _parse_cache_get(key: tuple) -> ParsedFilters | None:
    with _data_cache_lock:
        entry = _parse_cache.get(key)
        if entry is None:
            return None
        timestamp, parsed_filters = entry
        if time.monotonic() - timestamp > PARSE_CACHE_TTL_SECONDS:
            del _parse_cache[key]
            return None
        _parse_cache.move_to_end(key)
        return ParsedFilters(
            selected_retailers=list(parsed_filters.selected_retailers),
            start_date=parsed_filters.start_date,
            end_date=parsed_filters.end_date,
            max_files_per_retailer=parsed_filters.max_files_per_retailer,
            all_history=parsed_filters.all_history,
            meta=dict(parsed_filters.meta),
            inventory=parsed_filters.inventory,
        )


def _parse_cache_put(key: tuple, parsed_filters: ParsedFilters) -> None:
    with _data_cache_lock:
        now = time.monotonic()
        for stale_key in [k for k, (ts, _) in _parse_cache.items() if now - ts > PARSE_CACHE_TTL_SECONDS]:
            del _parse_cache[stale_key]
        _parse_cache[key] = (now, parsed_filters)
        _parse_cache.move_to_end(key)


RESPONSE_CACHE_TTL_SECONDS = 300
MAX_RESPONSE_CACHE_ENTRIES = 512
MAX_RESPONSE_CACHE_BYTES = 1024 * 1024 * 1024  # 1 GiB total cached bytes (raw + gzip variants)
GZIP_MIN_BYTES = 1024  # only pay gzip CPU for payloads where it matters

# Entry: (expires_at, raw_bytes, gzip_bytes|None, etag, gzip_etag|None).
# Stores bytes + ETag digests only, not the envelope dict: a 77 MB payload used
# to be cached twice (dict + orjson bytes). The gzip variant and ETags are
# derived once per entry here instead of per request.
_response_cache: "OrderedDict[tuple[str, str], tuple[float, bytes, bytes | None, str, str | None]]" = OrderedDict()
_response_cache_lock = threading.RLock()


def make_etag(data: bytes) -> str:
    """Return a strong opaque ETag (RFC 7232) for pre-serialized bytes.

    The md5 digest is deterministic and identical across workers, so 304
    validation stays correct under multi-process Granian/Gunicorn serving.
    """

    return hashlib.md5(data).hexdigest()


def _gzip_variant(raw_bytes: bytes) -> bytes | None:
    """Compress once per cache entry (deterministic; mtime=0 for reproducibility)."""

    if len(raw_bytes) < GZIP_MIN_BYTES:
        return None
    return gzip.compress(raw_bytes, compresslevel=6, mtime=0)


def get_cached_response(endpoint: str, query_string: str) -> tuple[bytes, bytes | None, str, str | None] | None:
    """Return (raw_bytes, gzip_bytes|None, etag, gzip_etag|None), or None on miss/expiry."""

    key = (endpoint, query_string)
    with _response_cache_lock:
        entry = _response_cache.get(key)
        if entry is None:
            return None
        timestamp, raw_bytes, gzip_bytes, etag, gzip_etag = entry
        if time.monotonic() - timestamp > RESPONSE_CACHE_TTL_SECONDS:
            del _response_cache[key]
            return None
        _response_cache.move_to_end(key)
        return raw_bytes, gzip_bytes, etag, gzip_etag


def put_cached_response(endpoint: str, query_string: str, raw_bytes: bytes) -> None:
    """Store pre-serialized bytes with a one-time gzip variant and ETag digests."""

    key = (endpoint, query_string)
    gzip_bytes = _gzip_variant(raw_bytes)
    etag = make_etag(raw_bytes)
    gzip_etag = make_etag(gzip_bytes) if gzip_bytes is not None else None
    with _response_cache_lock:
        now = time.monotonic()
        for stale_key in [k for k, (ts, _, _, _, _) in _response_cache.items() if now - ts > RESPONSE_CACHE_TTL_SECONDS]:
            del _response_cache[stale_key]
        while len(_response_cache) >= MAX_RESPONSE_CACHE_ENTRIES:
            _response_cache.popitem(last=False)
        total_bytes = sum(
            len(entry_raw) + (len(entry_gzip) if entry_gzip is not None else 0)
            for (_, entry_raw, entry_gzip, _, _) in _response_cache.values()
        )
        new_bytes = len(raw_bytes) + (len(gzip_bytes) if gzip_bytes is not None else 0)
        while _response_cache and total_bytes + new_bytes > MAX_RESPONSE_CACHE_BYTES:
            _, oldest_raw, oldest_gzip, _, _ = _response_cache.popitem(last=False)
            total_bytes -= len(oldest_raw) + (len(oldest_gzip) if oldest_gzip is not None else 0)
        _response_cache[key] = (now, raw_bytes, gzip_bytes, etag, gzip_etag)
        _response_cache.move_to_end(key)


def clear_response_cache() -> None:
    with _response_cache_lock:
        _response_cache.clear()


def clear_history_cache() -> None:
    """Clear the derived-data caches (parsed filters + loaded history + response cache)."""

    with _data_cache_lock:
        _history_cache.clear()
        _parse_cache.clear()
    clear_response_cache()


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
    """Parse and validate common filters, cached per raw request signature.

    Inventory-derived ranges are deterministic while the inventory cache is
    warm, so identical requests (same retailers/dates/max_files flags) skip the
    ~0.4s of per-request range/file-count recomputation.
    """

    key = _parse_cache_key(req)
    cached = _parse_cache_get(key)
    if cached is not None:
        return cached
    parsed_filters = _parse_common_filters_uncached(req)
    _parse_cache_put(key, parsed_filters)
    return parsed_filters


def _parse_common_filters_uncached(req: Any) -> ParsedFilters:
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


def _load_history_from_repository(parsed_filters: ParsedFilters) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Route history loading through sqlite_price_repository when available, falling back to CSV."""
    if is_sqlite_available():
        try:
            return sqlite_price_repository.load_price_history_from_db(
                tuple(parsed_filters.selected_retailers),
                parsed_filters.start_date,
                parsed_filters.end_date,
                parsed_filters.max_files_per_retailer,
            )
        except Exception:
            pass
    return load_price_history(
        tuple(parsed_filters.selected_retailers),
        parsed_filters.start_date,
        parsed_filters.end_date,
        parsed_filters.max_files_per_retailer,
        inventory=parsed_filters.inventory,
    )


def load_filtered_history(parsed_filters: ParsedFilters) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Load filtered price history, served from the in-process cache when the
    same filter signature was loaded recently.

    Cached frames are returned as copies so downstream consumers (use cases,
    serializers) can never mutate the shared cache entry.
    """

    key = _history_cache_key(parsed_filters)
    cached = _history_cache_get(key)
    if cached is not None:
        history, skipped = cached
    else:
        history, skipped = _load_history_from_repository(parsed_filters)
        _history_cache_put(key, history, skipped)
    warnings = list(parsed_filters.meta.get("warnings", []))
    if history.empty and len(skipped) > 0 and parsed_filters.meta.get("selected_inventory_file_count", 0):
        warnings.append("selected files skipped; no usable rows loaded")
    meta = {
        **parsed_filters.meta,
        "history_row_count": int(len(history)),
        "skipped_file_count": int(len(skipped)),
        "warnings": warnings,
    }
    return history.copy(), skipped.copy(), meta


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
