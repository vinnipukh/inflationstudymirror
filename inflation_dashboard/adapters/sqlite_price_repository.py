"""High-performance SQLite price repository adapter for the Falcon API and dashboard.

Interacts with the optimized SQLite database at `InflationItems/prices.db`.
Configured with WAL mode, busy_timeout, memory-mapped I/O (mmap_size),
and optimized cache sizes for high-throughput, concurrent reads.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

import pandas as pd

from inflation_dashboard.application.chart_specs import (
    BIGGEST_DROPS_COLUMNS,
    BIGGEST_GAINS_COLUMNS,
    CATEGORY_COVERAGE_COLUMNS,
    COVERAGE_OVER_TIME_COLUMNS,
    RETAILER_AVERAGE_COLUMNS,
)
from inflation_dashboard.domain.prices import HISTORY_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "InflationItems" / "prices.db"

SUPPORTED_RETAILERS = {
    "ClothingStores / Vakko",
    "Markets / Gurmar",
    "HomeGoods",
    "Technology",
    "Cosmetics / Watson",
    "ConstructionSuppliesMarkets / TasciYapiMarket",
    "ConstructionSuppliesMarkets / yapimaks",
    "HousesRent / Kayseri",
    "HousesRent / Sivas",
    "HousesRent / Tokat",
    "HousesRent / Emlakjet",
    "Health / Diagnostic&Surgical Services",
}

DEFAULT_RETAILERS = (
    "Markets / Gurmar",
    "ClothingStores / Vakko",
    "HomeGoods",
)
DEFAULT_MAX_FILES_PER_RETAILER = 45


def get_db_path() -> Path:
    """Return configured or default SQLite database path."""
    env_path = os.environ.get("PRICES_DB_PATH")
    if env_path:
        return Path(env_path).resolve()
    return DEFAULT_DB_PATH.resolve()


# Single source of truth for the read-optimized pragmas (adapter defaults).
# The launcher (scripts/run_falcon_server.py) and operators may override any of
# them via environment variables; the values below are the only defaults.
SQLITE_BUSY_TIMEOUT_MS = 5000
SQLITE_CACHE_SIZE = -128000  # negative value => KiB (128 MiB page cache)
SQLITE_MMAP_SIZE = 1024 * 1024 * 1024  # 1 GiB

_reader_local = threading.local()


def pragma_values() -> dict[str, int]:
    """Return the effective pragma values, honoring SQLITE_* environment overrides."""

    return {
        "busy_timeout": int(os.environ.get("SQLITE_BUSY_TIMEOUT", str(SQLITE_BUSY_TIMEOUT_MS))),
        "cache_size": int(os.environ.get("SQLITE_CACHE_SIZE", str(SQLITE_CACHE_SIZE))),
        "mmap_size": int(os.environ.get("SQLITE_MMAP_SIZE", str(SQLITE_MMAP_SIZE))),
    }


def _open_connection(db_path: Path, *, read_only: bool) -> sqlite3.Connection:
    """Open a single optimized connection with the effective pragma set."""

    values = pragma_values()
    if read_only:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.execute(f"PRAGMA busy_timeout = {values['busy_timeout']};")
        conn.execute(f"PRAGMA cache_size = {values['cache_size']};")
        conn.execute(f"PRAGMA mmap_size = {values['mmap_size']};")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA query_only = 1;")
    else:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute(f"PRAGMA busy_timeout = {values['busy_timeout']};")
        conn.execute(f"PRAGMA cache_size = {values['cache_size']};")
        conn.execute(f"PRAGMA mmap_size = {values['mmap_size']};")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")

    return conn


def get_db_connection(read_only: bool = True) -> sqlite3.Connection:
    """Open an optimized SQLite connection with WAL mode and high-performance PRAGMAs.

    Args:
        read_only: If True, opens with URI mode=ro and PRAGMA query_only = 1.
                   If False, opens read-write and enforces journal_mode = WAL.

    Returns a fresh connection per call (stateful write paths, tests, tooling).
    Request-serving read paths should use :func:`get_reusable_connection`.
    """
    db_path = get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Prices database not found at {db_path}")

    return _open_connection(db_path, read_only=read_only)


def get_reusable_connection() -> sqlite3.Connection:
    """Return the calling thread's persistent read-only connection.

    One connection per worker thread, lazily created on first use and reused
    across requests. This amortizes the connect+PRAGMA cost, keeps the SQLite
    page cache and mmap warm, and avoids the WAL ``-shm`` open/close churn
    that can produce rare SQLITE_BUSY for short-lived read-only connections
    (https://www.sqlite.org/wal.html#readonly; Hynek Schlawack's 2026 TIL).

    Thread-safe by construction: each thread owns its own connection.
    """

    conn = getattr(_reader_local, "connection", None)
    if conn is None:
        conn = _open_connection(get_db_path(), read_only=True)
        _reader_local.connection = conn
    return conn


def close_connection(conn: sqlite3.Connection) -> None:
    """Close a connection, unless it is the thread's persistent reader."""

    if getattr(_reader_local, "connection", None) is conn:
        return
    conn.close()


def close_local_connections() -> None:
    """Close the calling thread's persistent read-only connection.

    Call at worker shutdown or in test teardown so the db file can be
    replaced/removed on platforms where open mappings would block that.
    """

    conn = getattr(_reader_local, "connection", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _reader_local.connection = None


def clear_price_cache() -> None:
    """Clear in-memory cache if any (parity with csv_price_repository)."""
    _search_cache.clear()


_inventory_cache: pd.DataFrame | None = None
_inventory_cache_time: float = 0.0
_files_cache: pd.DataFrame | None = None
_files_cache_time: float = 0.0
CACHE_TTL_SECONDS = 300.0


def clear_price_cache() -> None:
    """Clear in-memory cache (parity with csv_price_repository)."""
    global _inventory_cache, _files_cache, _inventory_cache_time, _files_cache_time
    _inventory_cache = None
    _inventory_cache_time = 0.0
    _files_cache = None
    _files_cache_time = 0.0


def load_inventory_from_db() -> pd.DataFrame:
    """Load retailer summary inventory from SQLite database.

    Returns:
        DataFrame with columns: ['retailer', 'min_date', 'max_date', 'product_count']
    """
    global _inventory_cache, _inventory_cache_time
    import time
    now = time.monotonic()
    if _inventory_cache is not None and (now - _inventory_cache_time) < CACHE_TTL_SECONDS:
        return _inventory_cache.copy()

    conn = get_reusable_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                f.retailer, 
                f.min_date, 
                f.max_date, 
                p.product_count
            FROM (
                SELECT retailer, min(date) AS min_date, max(date) AS max_date
                FROM ingested_files
                GROUP BY retailer
            ) f
            JOIN (
                SELECT retailer, count(*) AS product_count
                FROM product_prices
                GROUP BY retailer
            ) p ON f.retailer = p.retailer
            ORDER BY f.retailer;
        """)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(rows, columns=cols)
        _inventory_cache = df.copy()
        _inventory_cache_time = time.monotonic()
        return df
    finally:
        close_connection(conn)


def discover_sqlite_inventory() -> pd.DataFrame:
    """Discover ingested file inventory from SQLite database.

    Drop-in replacement for csv_price_repository.discover_csv_inventory().

    Returns:
        DataFrame with columns: ['path', 'retailer', 'date', 'size_mb']
    """
    global _files_cache, _files_cache_time
    import time
    now = time.monotonic()
    if _files_cache is not None and (now - _files_cache_time) < CACHE_TTL_SECONDS:
        return _files_cache.copy()

    conn = get_reusable_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                file_path AS path, 
                retailer, 
                date, 
                round(file_size / 1024.0 / 1024.0, 4) AS size_mb
            FROM ingested_files
            ORDER BY retailer, date;
        """)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(rows, columns=cols)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        _files_cache = df.copy()
        _files_cache_time = time.monotonic()
        return df
    finally:
        close_connection(conn)


def _format_date(val: Any) -> str | None:
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (date, pd.Timestamp)):
        return val.strftime("%Y-%m-%d")
    return str(val).split("T")[0].split(" ")[0].strip()


def load_price_history_from_db(
    selected_retailers: Sequence[str],
    start_date: Any,
    end_date: Any,
    max_files_per_retailer: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load bounded price history for specified retailers and date range from SQLite.

    Args:
        selected_retailers: Sequence of retailer names to query.
        start_date: Start date string, date, or Timestamp (inclusive).
        end_date: End date string, date, or Timestamp (inclusive).
        max_files_per_retailer: Maximum most recent snapshot dates per retailer (0 for all).

    Returns:
        Tuple of (history_df, skipped_df).
        history_df columns: ['date', 'retailer', 'product_id', 'product_name', 'category', 'price', 'source_file']
        skipped_df columns: ['file', 'reason']
    """
    empty_history = pd.DataFrame(columns=HISTORY_COLUMNS)
    empty_skipped = pd.DataFrame(columns=["file", "reason"])

    retailers = [r for r in selected_retailers if r]
    if not retailers:
        return empty_history, empty_skipped

    start_str = _format_date(start_date)
    end_str = _format_date(end_date)

    conn = get_reusable_connection()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(retailers))

        if max_files_per_retailer > 0:
            # Select only the newest N dates per retailer within the date window
            query = f"""
                WITH selected_dates AS (
                    SELECT retailer, date
                    FROM (
                        SELECT retailer, date,
                               ROW_NUMBER() OVER (PARTITION BY retailer ORDER BY date DESC) AS rn
                        FROM ingested_files
                        WHERE retailer IN ({placeholders})
                          AND (? IS NULL OR date >= ?)
                          AND (? IS NULL OR date <= ?)
                    )
                    WHERE rn <= ?
                )
                SELECT 
                    p.date, 
                    p.retailer, 
                    p.product_id, 
                    p.product_name, 
                    p.category, 
                    p.price, 
                    p.source_file
                FROM price_observations p
                JOIN selected_dates sd ON p.retailer = sd.retailer AND p.date = sd.date
                ORDER BY p.retailer, p.product_name, p.date;
            """
            params = (*retailers, start_str, start_str, end_str, end_str, max_files_per_retailer)
        else:
            query = f"""
                SELECT 
                    p.date, 
                    p.retailer, 
                    p.product_id, 
                    p.product_name, 
                    p.category, 
                    p.price, 
                    p.source_file
                FROM price_observations p
                WHERE p.retailer IN ({placeholders})
                  AND (? IS NULL OR p.date >= ?)
                  AND (? IS NULL OR p.date <= ?)
                ORDER BY p.retailer, p.product_name, p.date;
            """
            params = (*retailers, start_str, start_str, end_str, end_str)

        cur.execute(query, params)
        rows = cur.fetchall()
        if not rows:
            return empty_history, empty_skipped

        cols = [d[0] for d in cur.description]
        history_df = pd.DataFrame(rows, columns=cols)
        history_df["date"] = pd.to_datetime(history_df["date"])
        history_df["price"] = history_df["price"].astype(float)
        return history_df, empty_skipped
    finally:
        close_connection(conn)


# Alias for drop-in parity
load_price_history = load_price_history_from_db


def get_product_price_history(product_id: str, retailer: str | None = None) -> dict[str, Any]:
    """Look up product price history and summary metrics for a single product.

    Args:
        product_id: Product identifier (or product name for fallback).
        retailer: Retailer name (optional; if None, resolves across all retailers).

    Returns:
        Dictionary with product metadata, JSON price history, record list, and summary.
    """
    conn = get_reusable_connection()
    try:
        cur = conn.cursor()
        if retailer:
            cur.execute("""
                SELECT 
                    product_id, 
                    retailer, 
                    product_name, 
                    category, 
                    first_date, 
                    last_date, 
                    latest_price, 
                    min_price, 
                    max_price, 
                    observations_count, 
                    price_history
                FROM product_prices
                WHERE retailer = ? AND product_id = ?;
            """, (retailer, product_id))
            row = cur.fetchone()

            if not row:
                # Fallback lookup by product name
                cur.execute("""
                    SELECT 
                        product_id, 
                        retailer, 
                        product_name, 
                        category, 
                        first_date, 
                        last_date, 
                        latest_price, 
                        min_price, 
                        max_price, 
                        observations_count, 
                        price_history
                    FROM product_prices
                    WHERE retailer = ? AND product_name = ?
                    LIMIT 1;
                """, (retailer, product_id))
                row = cur.fetchone()
        else:
            cur.execute("""
                SELECT 
                    product_id, 
                    retailer, 
                    product_name, 
                    category, 
                    first_date, 
                    last_date, 
                    latest_price, 
                    min_price, 
                    max_price, 
                    observations_count, 
                    price_history
                FROM product_prices
                WHERE product_id = ?
                ORDER BY observations_count DESC
                LIMIT 1;
            """, (product_id,))
            row = cur.fetchone()

            if not row:
                cur.execute("""
                    SELECT 
                        product_id, 
                        retailer, 
                        product_name, 
                        category, 
                        first_date, 
                        last_date, 
                        latest_price, 
                        min_price, 
                        max_price, 
                        observations_count, 
                        price_history
                    FROM product_prices
                    WHERE product_name = ?
                    ORDER BY observations_count DESC
                    LIMIT 1;
                """, (product_id,))
                row = cur.fetchone()

        if not row:
            return {}

        (
            pid, ret, pname, cat,
            first_date, last_date, latest_price, min_price, max_price,
            obs_count, history_json
        ) = row

        history_map: dict[str, float] = json.loads(history_json) if history_json else {}

        # Compute summary statistics
        cheapest_date = None
        first_price = None
        sorted_dates = sorted(history_map.keys())
        if sorted_dates:
            first_price = history_map[sorted_dates[0]]
            for d in sorted_dates:
                if history_map[d] == min_price:
                    cheapest_date = d
                    break

        change_since_first_pct = (
            ((latest_price - first_price) / first_price * 100)
            if first_price and latest_price is not None
            else 0.0
        )

        history_list = [
            {"date": d, "price": p, "category": cat, "source_file": ""}
            for d, p in sorted(history_map.items())
        ]

        return {
            "product_id": pid,
            "retailer": ret,
            "product_name": pname,
            "category": cat,
            "first_date": first_date,
            "last_date": last_date,
            "latest_price": latest_price,
            "min_price": min_price,
            "max_price": max_price,
            "observations_count": obs_count,
            "price_history": history_map,
            "history": history_list,
            "summary": {
                "latest_price": latest_price,
                "cheapest_price": min_price,
                "cheapest_date": cheapest_date,
                "change_since_first_pct": change_since_first_pct,
            },
        }
    finally:
        close_connection(conn)


def load_retailer_averages_from_db(
    selected_retailers: Sequence[str],
    start_date: Any,
    end_date: Any,
    aggregation: str = "Average",
) -> pd.DataFrame:
    """Compute daily retailer price averages or medians directly via SQLite.

    Args:
        selected_retailers: Sequence of retailer names.
        start_date: Start date string or object.
        end_date: End date string or object.
        aggregation: 'Average' (mean) or 'Median'.

    Returns:
        DataFrame with columns: ['date', 'retailer', 'price']
    """
    empty_df = pd.DataFrame(columns=RETAILER_AVERAGE_COLUMNS)
    retailers = [r for r in selected_retailers if r]
    if not retailers:
        return empty_df

    start_str = _format_date(start_date)
    end_str = _format_date(end_date)

    conn = get_reusable_connection()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(retailers))

        if aggregation == "Average":
            cur.execute(f"""
                SELECT date, retailer, avg(price) AS price
                FROM price_observations
                WHERE retailer IN ({placeholders})
                  AND (? IS NULL OR date >= ?)
                  AND (? IS NULL OR date <= ?)
                GROUP BY retailer, date
                ORDER BY retailer, date;
            """, (*retailers, start_str, start_str, end_str, end_str))
            rows = cur.fetchall()
            if not rows:
                return empty_df
            cols = [d[0] for d in cur.description]
            df = pd.DataFrame(rows, columns=cols)
        else:
            # Median aggregation: covering scan on (retailer, date, price)
            cur.execute(f"""
                SELECT date, retailer, price
                FROM price_observations
                WHERE retailer IN ({placeholders})
                  AND (? IS NULL OR date >= ?)
                  AND (? IS NULL OR date <= ?)
                ORDER BY retailer, date;
            """, (*retailers, start_str, start_str, end_str, end_str))
            rows = cur.fetchall()
            if not rows:
                return empty_df
            cols = [d[0] for d in cur.description]
            raw = pd.DataFrame(rows, columns=cols)
            df = raw.groupby(["date", "retailer"], as_index=False)["price"].median()
            df = df.sort_values(["retailer", "date"])

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df["price"] = df["price"].astype(float)
        return df[RETAILER_AVERAGE_COLUMNS].reset_index(drop=True)
    finally:
        close_connection(conn)


def load_movers_from_db(
    selected_retailers: Sequence[str],
    start_date: Any,
    end_date: Any,
    top_n: int = 10,
    scope_retailer: str = "All retailers",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute biggest drops and biggest gains for products with >= 2 observations.

    Args:
        selected_retailers: Sequence of retailer names to include.
        start_date: Start date.
        end_date: End date.
        top_n: Number of top movers to return for each side.
        scope_retailer: 'All retailers' or specific retailer name.

    Returns:
        Tuple of (biggest_drops_df, biggest_gains_df).
    """
    empty_drops = pd.DataFrame(columns=BIGGEST_DROPS_COLUMNS)
    empty_gains = pd.DataFrame(columns=BIGGEST_GAINS_COLUMNS)

    if scope_retailer != "All retailers":
        target_retailers = [scope_retailer]
    else:
        target_retailers = [r for r in selected_retailers if r]

    if not target_retailers:
        return empty_drops, empty_gains

    start_str = _format_date(start_date)
    end_str = _format_date(end_date)

    conn = get_reusable_connection()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(target_retailers))

        cur.execute(f"""
            WITH bounds AS (
                SELECT 
                    retailer,
                    product_id,
                    min(date) AS first_seen,
                    max(date) AS last_seen,
                    min(price) AS min_price,
                    max(price) AS max_price,
                    count(*) AS observations
                FROM price_observations
                WHERE retailer IN ({placeholders}) 
                  AND (? IS NULL OR date >= ?) 
                  AND (? IS NULL OR date <= ?)
                  AND price > 0
                GROUP BY retailer, product_id
                HAVING count(*) >= 2
            )
            SELECT 
                b.retailer,
                b.product_id,
                p_last.product_name,
                b.first_seen,
                b.last_seen,
                p_first.price AS first_price,
                p_last.price AS latest_price,
                b.min_price,
                b.max_price,
                b.observations
            FROM bounds b
            JOIN price_observations p_first 
              ON p_first.retailer = b.retailer 
             AND p_first.product_id = b.product_id 
             AND p_first.date = b.first_seen
            JOIN price_observations p_last 
              ON p_last.retailer = b.retailer 
             AND p_last.product_id = b.product_id 
             AND p_last.date = b.last_seen;
        """, (*target_retailers, start_str, start_str, end_str, end_str))

        rows = cur.fetchall()
        if not rows:
            return empty_drops, empty_gains

        cols = [d[0] for d in cur.description]
        stats = pd.DataFrame(rows, columns=cols)

        # Calculate percentages and metrics matching domain use cases
        stats["change_since_first_pct"] = (
            ((stats["latest_price"] - stats["first_price"]) / stats["first_price"]) * 100
        )
        stats["drop_from_peak_pct"] = (
            ((stats["latest_price"] - stats["max_price"]) / stats["max_price"]) * 100
        )
        stats["savings_vs_peak"] = stats["max_price"] - stats["latest_price"]

        drops = stats.sort_values("drop_from_peak_pct").head(top_n)[BIGGEST_DROPS_COLUMNS].reset_index(drop=True)
        gains = (
            stats.sort_values("change_since_first_pct", ascending=False)
            .head(top_n)[BIGGEST_GAINS_COLUMNS]
            .reset_index(drop=True)
        )

        return drops, gains
    finally:
        close_connection(conn)


def load_coverage_from_db(
    selected_retailers: Sequence[str],
    start_date: Any,
    end_date: Any,
    category_limit: int = 20,
) -> dict[str, Any]:
    """Compute summary coverage metrics, coverage over time, and category coverage directly via SQLite.

    Args:
        selected_retailers: Sequence of retailer names.
        start_date: Start date.
        end_date: End date.
        category_limit: Max categories to return.

    Returns:
        Dict with 'summary', 'coverage_over_time', 'category_coverage', and 'skipped_files'.
    """
    retailers = [r for r in selected_retailers if r]
    empty_summary = {
        "retailer_count": 0,
        "product_count": 0,
        "observation_count": 0,
        "date_range": "-",
        "skipped_file_count": 0,
    }
    empty_over_time = pd.DataFrame(columns=COVERAGE_OVER_TIME_COLUMNS)
    empty_category = pd.DataFrame(columns=CATEGORY_COVERAGE_COLUMNS)
    empty_skipped = pd.DataFrame(columns=["file", "reason"])

    if not retailers:
        return {
            "summary": empty_summary,
            "coverage_over_time": empty_over_time,
            "category_coverage": empty_category,
            "skipped_files": empty_skipped,
        }

    start_str = _format_date(start_date)
    end_str = _format_date(end_date)

    conn = get_reusable_connection()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(retailers))
        params = (*retailers, start_str, start_str, end_str, end_str)

        # 1. Summary
        cur.execute(f"""
            SELECT 
                count(DISTINCT retailer) AS retailer_count,
                count(DISTINCT product_id) AS product_count,
                count(*) AS observation_count,
                min(date) AS min_date,
                max(date) AS max_date
            FROM price_observations
            WHERE retailer IN ({placeholders})
              AND (? IS NULL OR date >= ?)
              AND (? IS NULL OR date <= ?);
        """, params)
        sum_row = cur.fetchone()
        if not sum_row or sum_row[2] == 0:
            return {
                "summary": empty_summary,
                "coverage_over_time": empty_over_time,
                "category_coverage": empty_category,
                "skipped_files": empty_skipped,
            }

        ret_count, prod_count, obs_count, min_d, max_d = sum_row
        summary = {
            "retailer_count": ret_count,
            "product_count": prod_count,
            "observation_count": obs_count,
            "date_range": f"{min_d} → {max_d}" if min_d and max_d else "-",
            "skipped_file_count": 0,
        }

        # 2. Coverage over time
        cur.execute(f"""
            SELECT date, retailer, count(DISTINCT product_id) AS tracked_products
            FROM price_observations
            WHERE retailer IN ({placeholders})
              AND (? IS NULL OR date >= ?)
              AND (? IS NULL OR date <= ?)
            GROUP BY date, retailer
            ORDER BY date, retailer;
        """, params)
        cot_rows = cur.fetchall()
        cot_cols = [d[0] for d in cur.description]
        coverage_over_time = pd.DataFrame(cot_rows, columns=cot_cols)
        if not coverage_over_time.empty:
            coverage_over_time["date"] = pd.to_datetime(coverage_over_time["date"])

        # 3. Category coverage
        cur.execute(f"""
            SELECT retailer, category, count(DISTINCT product_id) AS products
            FROM price_observations
            WHERE retailer IN ({placeholders})
              AND (? IS NULL OR date >= ?)
              AND (? IS NULL OR date <= ?)
            GROUP BY retailer, category
            ORDER BY products DESC
            LIMIT ?;
        """, (*params, category_limit))
        cat_rows = cur.fetchall()
        cat_cols = [d[0] for d in cur.description]
        category_coverage = pd.DataFrame(cat_rows, columns=cat_cols)

        return {
            "summary": summary,
            "coverage_over_time": coverage_over_time,
            "category_coverage": category_coverage,
            "skipped_files": empty_skipped,
        }
    finally:
        close_connection(conn)


_SEARCH_CACHE_TTL_SECONDS = 300
_search_cache: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}


def search_products(
    query: str = "",
    retailer: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search products in SQLite product_prices table for autocomplete.

    Args:
        query: Search term to match against product_name or product_id.
        retailer: Optional retailer filter.
        category: Optional category filter.
        limit: Max products to return (1-100).

    Returns:
        List of product dictionaries with metadata and current price.
    """
    bounded_limit = min(max(1, limit), 100)
    clean_q = query.strip()
    cache_key = (clean_q, retailer, category, bounded_limit)

    import time
    now = time.monotonic()
    cached = _search_cache.get(cache_key)
    if cached is not None:
        ts, results = cached
        if now - ts <= _SEARCH_CACHE_TTL_SECONDS:
            return results

    conn = get_reusable_connection()
    try:
        cur = conn.cursor()
        clauses: list[str] = []
        params: list[Any] = []

        if retailer:
            clauses.append("retailer = ?")
            params.append(retailer)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if clean_q:
            clauses.append("(product_name LIKE ? OR product_id LIKE ?)")
            params.extend([f"%{clean_q}%", f"%{clean_q}%"])

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        cur.execute(f"""
            SELECT 
                product_id, 
                retailer, 
                product_name, 
                category, 
                first_date, 
                last_date, 
                latest_price, 
                min_price, 
                max_price, 
                observations_count
            FROM product_prices
            {where_clause}
            ORDER BY observations_count DESC, product_name ASC
            LIMIT ?;
        """, (*params, bounded_limit))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        results = [dict(zip(cols, row)) for row in rows]
        _search_cache[cache_key] = (now, results)
        return results
    finally:
        close_connection(conn)
