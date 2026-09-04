"""
Asynchronous price repository (SQLAlchemy async engine over aiosqlite).

Implements high-scale principles:
* Asynchronous non-blocking I/O -- principle 10 (falcon.asgi resources await
  these calls; nothing blocks the event loop).
* Read/write splitting at the session layer -- principle 2::
      session.read   -> read-only engine (SQLite WAL, mode=ro URI)
      session.write  -> optional write engine (Postgres/SQLite) for future
                        state-changing endpoints
* Cursor-based (keyset) pagination -- principle 8 (product search).

Engine URLs:
* FALCON_DB_READ_URL   -- default: read-only sqlite+aiosqlite URI on the
                          existing prices.db (PRICES_DB_PATH / default path).
* FALCON_DB_WRITE_URL  -- optional; when unset the session exposes
                          ``write=None`` and state changes stay confined to
                          the ingest pipeline (correct for a read dashboard).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from inflation_dashboard.adapters.sqlite_price_repository import DEFAULT_DB_PATH, get_db_path
from inflation_dashboard.application.chart_specs import RETAILER_AVERAGE_COLUMNS
from inflation_dashboard.domain.prices import HISTORY_COLUMNS

PRODUCT_SEARCH_COLUMNS = [
    "product_id",
    "retailer",
    "product_name",
    "category",
    "first_date",
    "last_date",
    "latest_price",
    "min_price",
    "max_price",
    "observations_count",
]

PRODUCT_DETAIL_COLUMNS = PRODUCT_SEARCH_COLUMNS + ["price_history"]

_engines: dict[str, Any] = {}


def _read_engine_url() -> str:
    configured = os.environ.get("FALCON_DB_READ_URL")
    if configured:
        return configured
    db_path = get_db_path()
    return f"sqlite+aiosqlite:///file:{db_path.as_posix()}?mode=ro&uri=true"


def get_read_engine() -> Any:
    """Return the process-wide async read engine (created lazily)."""
    from sqlalchemy.ext.asyncio import create_async_engine

    if _engines.get("read") is None:
        url = _read_engine_url()
        _engines["read"] = create_async_engine(
            url,
            pool_size=10,
            max_overflow=20,
            pool_recycle=1800,
            connect_args={"timeout": 10.0},
        )
    return _engines["read"]


def get_write_engine() -> Any | None:
    """Return an optional write engine, or None when writes are disabled."""
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ.get("FALCON_DB_WRITE_URL")
    if not url:
        return None
    if _engines.get("write") is None:
        _engines["write"] = create_async_engine(url, pool_size=5, max_overflow=10)
    return _engines["write"]


def get_db_session() -> dict[str, Any]:
    """Return the request-scoped database session (read/write split).

    Bound to ``req.context.db`` by SessionMiddleware. Resources must never
    hold this across requests (statelessness principle).
    """
    read = get_read_engine()
    write = get_write_engine()
    return {"read": read, "write": write, "read_only": write is None}


async def close_db_session() -> None:
    """Dispose engines (call at worker shutdown / test teardown)."""
    for kind in list(_engines):
        try:
            await _engines.pop(kind).dispose()
        except Exception:
            pass


def _rows_to_dicts(rows: Sequence[Any], columns: Sequence[str]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row, strict=True)) for row in rows]


async def async_discover_inventory() -> pd.DataFrame:
    """Mirror of sqlite_price_repository.discover_sqlite_inventory() (async)."""
    from sqlalchemy import text

    engine = get_read_engine()
    query = text(
        """
        SELECT
            file_path AS path,
            retailer,
            date,
            round(file_size / 1024.0 / 1024.0, 4) AS size_mb
        FROM ingested_files
        ORDER BY retailer, date;
        """
    )
    async with engine.connect() as conn:
        result = await conn.execute(query)
        rows = result.fetchall()
        columns = list(result.keys())
    df = pd.DataFrame(rows, columns=columns)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


async def async_load_inventory_summary() -> pd.DataFrame:
    """Mirror of sqlite_price_repository.load_inventory_from_db() (async)."""
    from sqlalchemy import text

    engine = get_read_engine()
    query = text(
        """
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
        """
    )
    async with engine.connect() as conn:
        result = await conn.execute(query)
        rows = result.fetchall()
        columns = list(result.keys())
    return pd.DataFrame(rows, columns=columns)


def _search_where_clauses(
    query: str, retailer: str | None, category: str | None
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    bound: dict[str, Any] = {}
    if retailer:
        clauses.append("retailer = :retailer")
        bound["retailer"] = retailer
    if category:
        clauses.append("category = :category")
        bound["category"] = category
    if query:
        clauses.append("(product_name LIKE :q OR product_id LIKE :q)")
        bound["q"] = f"%{query}%"
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_clause, bound


async def async_search_products(
    query: str = "",
    retailer: str | None = None,
    category: str | None = None,
    limit: int = 20,
    cursor: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Keyset-paginated product search over (observations_count DESC, product_id ASC).

    Returns ``(rows, next_cursor)``. ``next_cursor`` is None on the last page.
    """
    from sqlalchemy import text

    bounded_limit = min(max(1, limit), 100)
    engine = get_read_engine()
    where_clause, bound_values = _search_where_clauses(query.strip(), retailer, category)

    keyset_clause = ""
    if cursor is not None:
        try:
            cursor_count = int(cursor["oc"])
            cursor_id = str(cursor["pid"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("malformed cursor") from exc
        keyset_clause = (
            " AND (observations_count < :cursor_count"
            "      OR (observations_count = :cursor_count AND product_id > :cursor_id))"
        )
        bound_values["cursor_count"] = cursor_count
        bound_values["cursor_id"] = cursor_id

    sql = f"""
        SELECT {", ".join(PRODUCT_SEARCH_COLUMNS)}
        FROM product_prices
        {where_clause}{keyset_clause}
        ORDER BY observations_count DESC, product_id ASC
        LIMIT {bounded_limit + 1};
    """
    async with engine.connect() as conn:
        result = await conn.execute(text(sql).bindparams(**bound_values) if bound_values else text(sql))
        rows = _rows_to_dicts(result.fetchall(), PRODUCT_SEARCH_COLUMNS)

    next_cursor: dict[str, Any] | None = None
    if len(rows) > bounded_limit:
        rows = rows[:bounded_limit]
        last = rows[-1]
        next_cursor = {"oc": int(last["observations_count"]), "pid": str(last["product_id"])}
    return rows, next_cursor


async def async_get_product_detail(
    product_id: str, retailer: str | None = None
) -> dict[str, Any] | None:
    """Mirror of sqlite_price_repository.get_product_price_history() (async)."""
    from sqlalchemy import text

    engine = get_read_engine()
    columns_sql = ", ".join(PRODUCT_DETAIL_COLUMNS)
    base_sql = f"SELECT {columns_sql} FROM product_prices"

    async def fetch_one(statement: Any) -> dict[str, Any] | None:
        async with engine.connect() as conn:
            result = await conn.execute(statement)
            row = result.fetchone()
        if row is None:
            return None
        return dict(zip(PRODUCT_DETAIL_COLUMNS, row, strict=True))

    # 1) exact product_id (+ retailer when given)
    if retailer:
        row = await fetch_one(
            text(f"{base_sql} WHERE retailer = :retailer AND product_id = :pid").bindparams(
                retailer=retailer, pid=product_id
            )
        )
        if row is None:  # fallback: match by product name
            row = await fetch_one(
                text(f"{base_sql} WHERE retailer = :retailer AND product_name = :pid LIMIT 1").bindparams(
                    retailer=retailer, pid=product_id
                )
            )
    else:
        row = await fetch_one(
            text(f"{base_sql} WHERE product_id = :pid ORDER BY observations_count DESC LIMIT 1").bindparams(
                pid=product_id
            )
        )
        if row is None:
            row = await fetch_one(
                text(f"{base_sql} WHERE product_name = :pid ORDER BY observations_count DESC LIMIT 1").bindparams(
                    pid=product_id
                )
            )

    if row is None:
        return None

    history_map: dict[str, float] = (
        json.loads(row["price_history"]) if row.get("price_history") else {}
    )
    sorted_dates = sorted(history_map.keys())

    cheapest_date = None
    first_price = history_map[sorted_dates[0]] if sorted_dates else None
    min_price = row["min_price"]
    for d in sorted_dates:
        if history_map[d] == min_price:
            cheapest_date = d
            break

    latest_price = row["latest_price"]
    change_since_first_pct = (
        ((latest_price - first_price) / first_price * 100)
        if first_price and latest_price is not None
        else 0.0
    )

    return {
        "product_id": row["product_id"],
        "retailer": row["retailer"],
        "product_name": row["product_name"],
        "category": row["category"],
        "first_date": row["first_date"],
        "last_date": row["last_date"],
        "latest_price": latest_price,
        "min_price": min_price,
        "max_price": row["max_price"],
        "observations_count": row["observations_count"],
        "price_history": history_map,
        "history": [{"date": d, "price": p, "category": row["category"], "source_file": ""} for d, p in history_map.items()],
        "summary": {
            "latest_price": latest_price,
            "cheapest_price": min_price,
            "cheapest_date": cheapest_date,
            "change_since_first_pct": change_since_first_pct,
        },
    }


def _format_date(val: Any) -> str | None:
    if val is None or pd.isna(val):
        return None
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    return str(val).split("T")[0].split(" ")[0].strip()


async def async_load_price_history(
    selected_retailers: Sequence[str],
    start_date: Any,
    end_date: Any,
    max_files_per_retailer: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mirror of sqlite_price_repository.load_price_history_from_db() (async).

    Used as the async DB path for the dashboard endpoints. The history rows
    become a DataFrame so downstream pandas use cases are unchanged.
    """
    from sqlalchemy import text

    empty_history = pd.DataFrame(columns=HISTORY_COLUMNS)
    empty_skipped = pd.DataFrame(columns=["file", "reason"])

    retailers = [r for r in selected_retailers if r]
    if not retailers:
        return empty_history, empty_skipped

    start_str = _format_date(start_date)
    end_str = _format_date(end_date)

    placeholders = ", ".join([f":r{i}" for i in range(len(retailers))])
    retailers_map = {f"r{i}": retailer for i, retailer in enumerate(retailers)}
    params: dict[str, Any] = dict(retailers_map)
    params["start_date"] = start_str
    params["end_date"] = end_str

    if max_files_per_retailer > 0:
        params["max_files"] = max_files_per_retailer
        sql = f"""
            WITH selected_dates AS (
                SELECT retailer, date
                FROM (
                    SELECT retailer, date,
                           ROW_NUMBER() OVER (PARTITION BY retailer ORDER BY date DESC) AS rn
                    FROM ingested_files
                    WHERE retailer IN ({placeholders})
                      AND (:start_date IS NULL OR date >= :start_date)
                      AND (:end_date IS NULL OR date <= :end_date)
                )
                WHERE rn <= :max_files
            )
            SELECT
                p.date, p.retailer, p.product_id, p.product_name, p.category, p.price, p.source_file
            FROM price_observations p
            JOIN selected_dates sd ON p.retailer = sd.retailer AND p.date = sd.date
            ORDER BY p.retailer, p.product_name, p.date;
        """
    else:
        sql = f"""
            SELECT
                p.date, p.retailer, p.product_id, p.product_name, p.category, p.price, p.source_file
            FROM price_observations p
            WHERE p.retailer IN ({placeholders})
              AND (:start_date IS NULL OR p.date >= :start_date)
              AND (:end_date IS NULL OR p.date <= :end_date)
            ORDER BY p.retailer, p.product_name, p.date;
        """

    engine = get_read_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(sql).bindparams(**params))
        rows = result.fetchall()
        columns = list(result.keys())

    if not rows:
        return empty_history, empty_skipped

    history_df = pd.DataFrame(rows, columns=columns)
    history_df["date"] = pd.to_datetime(history_df["date"])
    history_df["price"] = history_df["price"].astype(float)
    return history_df, empty_skipped


async def async_load_retailer_averages(
    selected_retailers: Sequence[str],
    start_date: Any,
    end_date: Any,
    aggregation: str = "Average",
) -> pd.DataFrame:
    """Mirror of sqlite_price_repository.load_retailer_averages_from_db() (async)."""
    from sqlalchemy import text

    empty_df = pd.DataFrame(columns=RETAILER_AVERAGE_COLUMNS)
    retailers = [r for r in selected_retailers if r]
    if not retailers:
        return empty_df

    start_str = _format_date(start_date)
    end_str = _format_date(end_date)
    placeholders = ", ".join([f":r{i}" for i in range(len(retailers))])
    params: dict[str, Any] = {f"r{i}": r for i, r in enumerate(retailers)}
    params["start_date"] = start_str
    params["end_date"] = end_str

    engine = get_read_engine()
    if aggregation == "Average":
        sql = f"""
            SELECT date, retailer, avg(price) AS price
            FROM price_observations
            WHERE retailer IN ({placeholders})
              AND (:start_date IS NULL OR date >= :start_date)
              AND (:end_date IS NULL OR date <= :end_date)
            GROUP BY retailer, date
            ORDER BY retailer, date;
        """
        async with engine.connect() as conn:
            result = await conn.execute(text(sql).bindparams(**params))
            rows = result.fetchall()
            columns = list(result.keys())
        if not rows:
            return empty_df
        df = pd.DataFrame(rows, columns=columns)
    else:
        sql = f"""
            SELECT date, retailer, price
            FROM price_observations
            WHERE retailer IN ({placeholders})
              AND (:start_date IS NULL OR date >= :start_date)
              AND (:end_date IS NULL OR date <= :end_date)
            ORDER BY retailer, date;
        """
        async with engine.connect() as conn:
            result = await conn.execute(text(sql).bindparams(**params))
            rows = result.fetchall()
            columns = list(result.keys())
        if not rows:
            return empty_df
        raw = pd.DataFrame(rows, columns=columns)
        df = raw.groupby(["date", "retailer"], as_index=False)["price"].median().sort_values(["retailer", "date"])

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["price"] = df["price"].astype(float)
    return df[RETAILER_AVERAGE_COLUMNS].reset_index(drop=True)


def is_sqlite_db_available() -> bool:
    """True when the existing prices.db is readable (async path may be used)."""
    try:
        return get_db_path().is_file() and get_db_path().stat().st_size > 0
    except Exception:
        return False
