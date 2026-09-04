#!/usr/bin/env python3
"""
SQLite Extreme Read Performance & Concurrency Benchmark.
Profiles dashboard queries across 100+ concurrent readers and evaluates
connection strategies (fresh connect, connection pool, thread-local).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import concurrent.futures
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import queue
import sqlite3
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

# Set project root
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "InflationItems" / "prices.db"

# -----------------------------------------------------------------------------
# Benchmark Query Suite
# -----------------------------------------------------------------------------
BENCHMARK_QUERIES = [
    {
        "name": "1_product_detail",
        "desc": "Single product lookup by ID (autocompletion / detail)",
        "sql": """
            SELECT product_id, retailer, product_name, category, first_date, last_date,
                   latest_price, min_price, max_price, observations_count, price_history
            FROM product_prices
            WHERE retailer = ? AND product_id = ?;
        """,
        "params": ("ClothingStores / Vakko", "M405487839-0027-0104"),
    },
    {
        "name": "2_product_search",
        "desc": "Product search by name pattern (autocomplete search)",
        "sql": """
            SELECT product_id, retailer, product_name, category, latest_price, min_price, max_price, observations_count
            FROM product_prices
            WHERE retailer = ? AND product_name LIKE ?
            ORDER BY observations_count DESC
            LIMIT 20;
        """,
        "params": ("ClothingStores / Vakko", "%GÖMLEK%"),
    },
    {
        "name": "3_retailer_averages",
        "desc": "Daily price averages (covering index on retailer, date, price)",
        "sql": """
            SELECT date, retailer, avg(price) AS avg_price, count(*) AS obs_count
            FROM price_observations
            WHERE retailer IN (?, ?) AND date >= ? AND date <= ?
            GROUP BY retailer, date
            ORDER BY retailer, date;
        """,
        "params": ("ClothingStores / Vakko", "Markets / Gurmar", "2026-08-01", "2026-08-15"),
    },
    {
        "name": "4_category_coverage",
        "desc": "Category aggregation (covering index on retailer, category, product_id)",
        "sql": """
            SELECT retailer, category, count(product_id) AS products
            FROM product_prices
            WHERE retailer = ?
            GROUP BY retailer, category
            ORDER BY products DESC
            LIMIT 20;
        """,
        "params": ("ClothingStores / Vakko",),
    },
    {
        "name": "5_movers_drops_retailer",
        "desc": "Top price drops for retailer (covering index on movers columns)",
        "sql": """
            SELECT product_id, retailer, product_name, category, latest_price, max_price, min_price,
                   ((latest_price - max_price) / max_price * 100.0) AS drop_from_peak_pct
            FROM product_prices
            WHERE retailer = ? AND observations_count >= 2 AND max_price > 0
            ORDER BY drop_from_peak_pct ASC
            LIMIT 10;
        """,
        "params": ("ClothingStores / Vakko",),
    },
    {
        "name": "6_movers_drops_all",
        "desc": "Top price drops across all retailers (global covering index)",
        "sql": """
            SELECT product_id, retailer, product_name, category, latest_price, max_price, min_price,
                   ((latest_price - max_price) / max_price * 100.0) AS drop_from_peak_pct
            FROM product_prices
            WHERE observations_count >= 2 AND max_price > 0
            ORDER BY drop_from_peak_pct ASC
            LIMIT 10;
        """,
        "params": (),
    },
    {
        "name": "7_history_slice",
        "desc": "Filtered history slice (bounded retailer + date range)",
        "sql": """
            SELECT date, retailer, product_id, product_name, category, price
            FROM price_observations
            WHERE retailer = ? AND date >= ? AND date <= ?
            ORDER BY retailer, date
            LIMIT 500;
        """,
        "params": ("Markets / Gurmar", "2026-08-01", "2026-08-15"),
    },
    {
        "name": "8_inventory_discovery",
        "desc": "Inventory summary discovery across all retailers",
        "sql": """
            SELECT retailer, count(*) AS product_count, min(first_date) AS min_date, max(last_date) AS max_date
            FROM product_prices
            GROUP BY retailer
            ORDER BY retailer;
        """,
        "params": (),
    },
]

# -----------------------------------------------------------------------------
# Connection Strategies
# -----------------------------------------------------------------------------
def open_readonly_connection(db_path: Path, check_same_thread: bool = True) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=check_same_thread, timeout=15.0)
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA cache_size = -64000;")      # 64 MB page cache
    conn.execute("PRAGMA mmap_size = 1073741824;")    # 1 GB mmap
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA query_only = 1;")
    return conn


class ConnectionPool:
    """Thread-safe FIFO connection pool of pre-opened read-only SQLite connections."""

    def __init__(self, db_path: Path, pool_size: int = 20):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=pool_size)
        for _ in range(pool_size):
            self._pool.put(open_readonly_connection(db_path, check_same_thread=False))

    def acquire(self, timeout: float = 10.0) -> sqlite3.Connection:
        return self._pool.get(timeout=timeout)

    def release(self, conn: sqlite3.Connection) -> None:
        self._pool.put(conn)

    def close(self) -> None:
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except queue.Empty:
                break


class ThreadLocalConnections:
    """Thread-local connection holder ensuring exactly one connection per worker thread."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()

    def get(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = open_readonly_connection(self.db_path, check_same_thread=True)
        return self._local.conn

    def close_current(self) -> None:
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn


# -----------------------------------------------------------------------------
# Benchmark Result Structures
# -----------------------------------------------------------------------------
@dataclass
class QueryStat:
    name: str
    count: int
    latencies: List[float]

    @property
    def min_ms(self) -> float:
        return float(np.min(self.latencies)) if self.latencies else 0.0

    @property
    def mean_ms(self) -> float:
        return float(np.mean(self.latencies)) if self.latencies else 0.0

    @property
    def p50_ms(self) -> float:
        return float(np.percentile(self.latencies, 50)) if self.latencies else 0.0

    @property
    def p90_ms(self) -> float:
        return float(np.percentile(self.latencies, 90)) if self.latencies else 0.0

    @property
    def p95_ms(self) -> float:
        return float(np.percentile(self.latencies, 95)) if self.latencies else 0.0

    @property
    def p99_ms(self) -> float:
        return float(np.percentile(self.latencies, 99)) if self.latencies else 0.0

    @property
    def max_ms(self) -> float:
        return float(np.max(self.latencies)) if self.latencies else 0.0


@dataclass
class BenchmarkReport:
    strategy_name: str
    concurrency: int
    total_requests: int
    elapsed_seconds: float
    rps: float
    error_count: int
    all_latencies: List[float] = field(default_factory=list)
    query_stats: Dict[str, QueryStat] = field(default_factory=dict)

    @property
    def min_ms(self) -> float:
        return float(np.min(self.all_latencies)) if self.all_latencies else 0.0

    @property
    def mean_ms(self) -> float:
        return float(np.mean(self.all_latencies)) if self.all_latencies else 0.0

    @property
    def p50_ms(self) -> float:
        return float(np.percentile(self.all_latencies, 50)) if self.all_latencies else 0.0

    @property
    def p90_ms(self) -> float:
        return float(np.percentile(self.all_latencies, 90)) if self.all_latencies else 0.0

    @property
    def p95_ms(self) -> float:
        return float(np.percentile(self.all_latencies, 95)) if self.all_latencies else 0.0

    @property
    def p99_ms(self) -> float:
        return float(np.percentile(self.all_latencies, 99)) if self.all_latencies else 0.0

    @property
    def max_ms(self) -> float:
        return float(np.max(self.all_latencies)) if self.all_latencies else 0.0

    def print_summary(self) -> None:
        print(f"\n{'=' * 80}")
        print(f"Strategy   : {self.strategy_name}")
        print(f"Concurrency: {self.concurrency} concurrent worker threads")
        print(f"Requests   : {self.total_requests} queries (errors: {self.error_count})")
        print(f"Duration   : {self.elapsed_seconds:.3f} s  ==>  Throughput: {self.rps:.1f} queries/sec (RPS)")
        print(f"Overall Latency (ms):")
        print(f"  Min : {self.min_ms:7.2f} ms | Mean: {self.mean_ms:7.2f} ms")
        print(f"  p50 : {self.p50_ms:7.2f} ms | p90 : {self.p90_ms:7.2f} ms")
        print(f"  p95 : {self.p95_ms:7.2f} ms | p99 : {self.p99_ms:7.2f} ms | Max: {self.max_ms:7.2f} ms")
        print(f"{'-' * 80}")
        print(f"{'Query Name':<26} | {'Count':>5} | {'p50 (ms)':>9} | {'p95 (ms)':>9} | {'p99 (ms)':>9} | {'Mean (ms)':>9}")
        print(f"{'-' * 80}")
        for qname, stat in sorted(self.query_stats.items()):
            print(f"{qname:<26} | {stat.count:>5} | {stat.p50_ms:>9.2f} | {stat.p95_ms:>9.2f} | {stat.p99_ms:>9.2f} | {stat.mean_ms:>9.2f}")
        print(f"{'=' * 80}")


# -----------------------------------------------------------------------------
# Execution Engine
# -----------------------------------------------------------------------------
def run_benchmark(
    strategy_name: str,
    db_path: Path,
    concurrency: int,
    total_requests: int,
    execute_query_fn: Callable[[int], Tuple[str, float, bool]],
    setup_fn: Optional[Callable[[], None]] = None,
    teardown_fn: Optional[Callable[[], None]] = None,
) -> BenchmarkReport:
    if setup_fn:
        setup_fn()

    errors = 0
    all_lats: List[float] = []
    by_query: Dict[str, List[float]] = defaultdict(list)

    t_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(execute_query_fn, i) for i in range(total_requests)]
        for f in concurrent.futures.as_completed(futures):
            try:
                qname, lat_ms, success = f.result()
                if success:
                    all_lats.append(lat_ms)
                    by_query[qname].append(lat_ms)
                else:
                    errors += 1
            except Exception:
                errors += 1
    elapsed = time.perf_counter() - t_start

    if teardown_fn:
        teardown_fn()

    rps = len(all_lats) / elapsed if elapsed > 0 else 0.0
    q_stats = {
        name: QueryStat(name=name, count=len(lats), latencies=lats)
        for name, lats in by_query.items()
    }

    return BenchmarkReport(
        strategy_name=strategy_name,
        concurrency=concurrency,
        total_requests=total_requests,
        elapsed_seconds=elapsed,
        rps=rps,
        error_count=errors,
        all_latencies=all_lats,
        query_stats=q_stats,
    )


# -----------------------------------------------------------------------------
# Main CLI & Benchmark Suites
# -----------------------------------------------------------------------------
def run_comparison(db_path: Path, concurrency: int, total_requests: int) -> List[BenchmarkReport]:
    reports: List[BenchmarkReport] = []

    # 1. Thread-Local Strategy
    tl = ThreadLocalConnections(db_path)

    def worker_thread_local(i: int) -> Tuple[str, float, bool]:
        q = BENCHMARK_QUERIES[i % len(BENCHMARK_QUERIES)]
        conn = tl.get()
        t0 = time.perf_counter()
        try:
            cur = conn.cursor()
            cur.execute(q["sql"], q["params"])
            cur.fetchall()
            lat = (time.perf_counter() - t0) * 1000.0
            return q["name"], lat, True
        except Exception as e:
            return q["name"], 0.0, False

    def setup_tl() -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            list(ex.map(lambda _: tl.get().execute("SELECT 1;").fetchall(), range(concurrency)))

    rep_tl = run_benchmark(
        "Thread-Local Connections (1 conn per thread)",
        db_path,
        concurrency=concurrency,
        total_requests=total_requests,
        execute_query_fn=worker_thread_local,
        setup_fn=setup_tl,
    )
    rep_tl.print_summary()
    reports.append(rep_tl)

    # 2. Connection Pool Strategy
    pool_size = min(concurrency, 30)
    pool = ConnectionPool(db_path, pool_size=pool_size)

    def worker_pool(i: int) -> Tuple[str, float, bool]:
        q = BENCHMARK_QUERIES[i % len(BENCHMARK_QUERIES)]
        t0 = time.perf_counter()
        conn = pool.acquire(timeout=15.0)
        try:
            cur = conn.cursor()
            cur.execute(q["sql"], q["params"])
            cur.fetchall()
            lat = (time.perf_counter() - t0) * 1000.0
            return q["name"], lat, True
        except Exception as e:
            return q["name"], 0.0, False
        finally:
            pool.release(conn)

    rep_pool = run_benchmark(
        f"Connection Pool (pool_size={pool_size})",
        db_path,
        concurrency=concurrency,
        total_requests=total_requests,
        execute_query_fn=worker_pool,
        teardown_fn=pool.close,
    )
    rep_pool.print_summary()
    reports.append(rep_pool)

    # 3. Fresh Connect Per Query Strategy (smaller sample size if concurrency is high)
    fresh_requests = min(total_requests, 300)

    def worker_fresh(i: int) -> Tuple[str, float, bool]:
        q = BENCHMARK_QUERIES[i % len(BENCHMARK_QUERIES)]
        t0 = time.perf_counter()
        conn = None
        try:
            conn = open_readonly_connection(db_path, check_same_thread=True)
            cur = conn.cursor()
            cur.execute(q["sql"], q["params"])
            cur.fetchall()
            lat = (time.perf_counter() - t0) * 1000.0
            return q["name"], lat, True
        except Exception as e:
            return q["name"], 0.0, False
        finally:
            if conn:
                conn.close()

    rep_fresh = run_benchmark(
        "Fresh Connect Per Query (sqlite3.connect per call)",
        db_path,
        concurrency=min(concurrency, 50),
        total_requests=fresh_requests,
        execute_query_fn=worker_fresh,
    )
    rep_fresh.print_summary()
    reports.append(rep_fresh)

    return reports


def run_scaling_benchmark(db_path: Path, concurrency_levels: List[int], requests_per_level: int) -> List[BenchmarkReport]:
    tl = ThreadLocalConnections(db_path)

    def worker_thread_local(i: int) -> Tuple[str, float, bool]:
        q = BENCHMARK_QUERIES[i % len(BENCHMARK_QUERIES)]
        conn = tl.get()
        t0 = time.perf_counter()
        try:
            cur = conn.cursor()
            cur.execute(q["sql"], q["params"])
            cur.fetchall()
            lat = (time.perf_counter() - t0) * 1000.0
            return q["name"], lat, True
        except Exception as e:
            return q["name"], 0.0, False

    reports: List[BenchmarkReport] = []
    print(f"\n================ Scaling Concurrency Test across {concurrency_levels} workers ================")
    for c in concurrency_levels:
        with concurrent.futures.ThreadPoolExecutor(max_workers=c) as ex:
            list(ex.map(lambda _: tl.get().execute("SELECT 1;").fetchall(), range(c)))

        rep = run_benchmark(
            f"Thread-Local @ {c} Concurrent Readers",
            db_path,
            concurrency=c,
            total_requests=requests_per_level,
            execute_query_fn=worker_thread_local,
        )
        rep.print_summary()
        reports.append(rep)
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile and Benchmark SQLite extreme read performance")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Path to SQLite database file")
    parser.add_argument("--concurrency", type=int, default=100, help="Number of concurrent reader threads")
    parser.add_argument("--requests", type=int, default=800, help="Total queries to execute per test")
    parser.add_argument("--mode", choices=["compare", "scale", "all"], default="all", help="Benchmark mode")
    parser.add_argument("--json-out", default=None, help="Output JSON results to specified file")
    args = parser.parse_args()

    db_path = Path(args.db_path).resolve()
    if not db_path.exists():
        print(f"Error: DB path not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"=== SQLite Extreme Read Performance & Concurrency Benchmark ===")
    print(f"Target Database : {db_path} ({db_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"Reader Workers  : {args.concurrency}")
    print(f"Total Requests  : {args.requests}")

    all_reports: List[BenchmarkReport] = []

    if args.mode in ["compare", "all"]:
        all_reports.extend(run_comparison(db_path, args.concurrency, args.requests))

    if args.mode in ["scale", "all"]:
        scale_levels = [1, 10, 25, 50, 100]
        all_reports.extend(run_scaling_benchmark(db_path, scale_levels, requests_per_level=min(args.requests, 500)))

    if args.json_out:
        out_data = [
            {
                "strategy": r.strategy_name,
                "concurrency": r.concurrency,
                "requests": r.total_requests,
                "elapsed_s": r.elapsed_seconds,
                "rps": r.rps,
                "errors": r.error_count,
                "p50_ms": r.p50_ms,
                "p90_ms": r.p90_ms,
                "p95_ms": r.p95_ms,
                "p99_ms": r.p99_ms,
                "queries": {
                    qname: {
                        "count": qstat.count,
                        "p50_ms": qstat.p50_ms,
                        "p95_ms": qstat.p95_ms,
                        "p99_ms": qstat.p99_ms,
                        "mean_ms": qstat.mean_ms,
                    }
                    for qname, qstat in r.query_stats.items()
                }
            }
            for r in all_reports
        ]
        with open(args.json_out, "w", encoding="utf-8") as jf:
            json.dump(out_data, jf, indent=2)
        print(f"Saved benchmark report to {args.json_out}")

if __name__ == "__main__":
    main()
