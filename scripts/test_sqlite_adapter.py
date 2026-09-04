#!/usr/bin/env python3
"""Comprehensive test suite and performance benchmark for the SQLite price repository adapter.

Tests all adapter functions and measures execution latencies.
Usage:
    ./.venv/bin/python scripts/test_sqlite_adapter.py
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inflation_dashboard.adapters.sqlite_price_repository import (
    DEFAULT_RETAILERS,
    discover_sqlite_inventory,
    get_db_connection,
    get_product_price_history,
    load_coverage_from_db,
    load_inventory_from_db,
    load_movers_from_db,
    load_price_history_from_db,
    load_retailer_averages_from_db,
)
from inflation_dashboard.application.chart_specs import (
    BIGGEST_DROPS_COLUMNS,
    BIGGEST_GAINS_COLUMNS,
    CATEGORY_COVERAGE_COLUMNS,
    COVERAGE_OVER_TIME_COLUMNS,
    RETAILER_AVERAGE_COLUMNS,
)
from inflation_dashboard.domain.prices import HISTORY_COLUMNS


def run_benchmark():
    print("=" * 70)
    print("TESTING SQLITE PRICE REPOSITORY ADAPTER")
    print("=" * 70)

    results = []

    # 1. Connection & Pragmas Test
    print("\n[1/7] Testing get_db_connection()...")
    t0 = time.perf_counter()
    conn_ro = get_db_connection(read_only=True)
    cur = conn_ro.cursor()
    journal = cur.execute("PRAGMA journal_mode;").fetchone()[0]
    busy = cur.execute("PRAGMA busy_timeout;").fetchone()[0]
    cache = cur.execute("PRAGMA cache_size;").fetchone()[0]
    mmap = cur.execute("PRAGMA mmap_size;").fetchone()[0]
    query_only = cur.execute("PRAGMA query_only;").fetchone()[0]
    conn_ro.close()
    t1 = time.perf_counter()

    assert journal.lower() == "wal", f"Expected WAL mode, got {journal}"
    assert busy == 5000, f"Expected busy_timeout 5000, got {busy}"
    assert cache == -128000, f"Expected cache_size -128000, got {cache}"
    assert mmap == 1073741824, f"Expected mmap 1GB, got {mmap}"
    assert query_only == 1, f"Expected query_only=1 for read_only, got {query_only}"
    lat = (t1 - t0) * 1000
    print(f"  PASS: read_only connection opened and pragmas verified in {lat:.2f} ms")
    results.append(("get_db_connection(read_only=True)", lat, "OK"))

    # Test read_write connection
    t0 = time.perf_counter()
    conn_rw = get_db_connection(read_only=False)
    conn_rw.close()
    t1 = time.perf_counter()
    lat = (t1 - t0) * 1000
    print(f"  PASS: read_write connection opened in {lat:.2f} ms")
    results.append(("get_db_connection(read_only=False)", lat, "OK"))

    # 2. Inventory Test
    print("\n[2/7] Testing load_inventory_from_db() and discover_sqlite_inventory()...")
    t0 = time.perf_counter()
    inv = load_inventory_from_db()
    t1 = time.perf_counter()
    lat_inv = (t1 - t0) * 1000
    assert not inv.empty, "Inventory must not be empty"
    expected_inv_cols = ["retailer", "min_date", "max_date", "product_count"]
    assert list(inv.columns) == expected_inv_cols, f"Cols mismatch: {inv.columns}"
    assert inv["product_count"].sum() > 0, "Expected > 0 products"
    print(f"  PASS: load_inventory_from_db() returned {len(inv)} retailers in {lat_inv:.2f} ms")
    print(f"        Total products: {inv['product_count'].sum():,}")
    results.append(("load_inventory_from_db()", lat_inv, f"{len(inv)} retailers"))

    t0 = time.perf_counter()
    files_inv = discover_sqlite_inventory()
    t1 = time.perf_counter()
    lat_files = (t1 - t0) * 1000
    assert not files_inv.empty
    assert list(files_inv.columns) == ["path", "retailer", "date", "size_mb"]
    print(f"  PASS: discover_sqlite_inventory() returned {len(files_inv)} files in {lat_files:.2f} ms")
    results.append(("discover_sqlite_inventory()", lat_files, f"{len(files_inv)} files"))

    # 3. Price History Test
    print("\n[3/7] Testing load_price_history_from_db()...")
    test_retailers = ["Markets / Gurmar", "HomeGoods"]
    start_date = "2026-08-01"
    end_date = "2026-08-31"

    # 3a. Bounded with max_files_per_retailer = 5
    t0 = time.perf_counter()
    hist_5, skipped_5 = load_price_history_from_db(
        test_retailers, start_date, end_date, max_files_per_retailer=5
    )
    t1 = time.perf_counter()
    lat_hist_5 = (t1 - t0) * 1000
    assert list(hist_5.columns) == HISTORY_COLUMNS
    assert len(hist_5) > 0
    assert len(skipped_5) == 0
    print(f"  PASS: load_price_history (max_files=5) returned {len(hist_5):,} rows in {lat_hist_5:.2f} ms")
    results.append(("load_price_history(max_files=5)", lat_hist_5, f"{len(hist_5):,} rows"))

    # 3b. Uncapped (max_files_per_retailer = 0)
    t0 = time.perf_counter()
    hist_all, skipped_all = load_price_history_from_db(
        test_retailers, start_date, end_date, max_files_per_retailer=0
    )
    t1 = time.perf_counter()
    lat_hist_all = (t1 - t0) * 1000
    assert len(hist_all) >= len(hist_5)
    print(f"  PASS: load_price_history (max_files=0) returned {len(hist_all):,} rows in {lat_hist_all:.2f} ms")
    results.append(("load_price_history(max_files=0)", lat_hist_all, f"{len(hist_all):,} rows"))

    # 3c. Empty input test
    empty_h, empty_s = load_price_history_from_db([], start_date, end_date)
    assert empty_h.empty and empty_s.empty
    print("  PASS: empty selected_retailers handled gracefully")

    # 4. Product Price History Test
    print("\n[4/7] Testing get_product_price_history()...")
    # Sample product from Gurmar
    sample_pid = hist_5.iloc[0]["product_id"]
    sample_ret = hist_5.iloc[0]["retailer"]
    sample_name = hist_5.iloc[0]["product_name"]

    t0 = time.perf_counter()
    prod_data = get_product_price_history(sample_pid, sample_ret)
    t1 = time.perf_counter()
    lat_prod = (t1 - t0) * 1000
    assert prod_data, f"Product {sample_pid} not found"
    assert prod_data["product_id"] == sample_pid
    assert prod_data["retailer"] == sample_ret
    assert "price_history" in prod_data and isinstance(prod_data["price_history"], dict)
    assert "summary" in prod_data
    assert "history" in prod_data and len(prod_data["history"]) > 0
    print(f"  PASS: get_product_price_history(by product_id) returned {len(prod_data['price_history'])} points in {lat_prod:.2f} ms")
    results.append(("get_product_price_history(by ID)", lat_prod, f"{len(prod_data['price_history'])} points"))

    # Test fallback by product_name
    t0 = time.perf_counter()
    prod_data_name = get_product_price_history(sample_name, sample_ret)
    t1 = time.perf_counter()
    lat_prod_name = (t1 - t0) * 1000
    assert prod_data_name
    print(f"  PASS: get_product_price_history(fallback by name) in {lat_prod_name:.2f} ms")
    results.append(("get_product_price_history(by Name)", lat_prod_name, "OK"))

    # Test not found
    not_found = get_product_price_history("NONEXISTENT_XYZ_12345", "Markets / Gurmar")
    assert not_found == {}
    print("  PASS: non-existent product returned empty dict")

    # 5. Retailer Averages Test
    print("\n[5/7] Testing load_retailer_averages_from_db()...")
    t0 = time.perf_counter()
    avg_df = load_retailer_averages_from_db(
        test_retailers, start_date, end_date, aggregation="Average"
    )
    t1 = time.perf_counter()
    lat_avg = (t1 - t0) * 1000
    assert list(avg_df.columns) == RETAILER_AVERAGE_COLUMNS
    assert not avg_df.empty
    print(f"  PASS: load_retailer_averages (Average) returned {len(avg_df)} rows in {lat_avg:.2f} ms")
    results.append(("load_retailer_averages(Average)", lat_avg, f"{len(avg_df)} rows"))

    t0 = time.perf_counter()
    med_df = load_retailer_averages_from_db(
        test_retailers, start_date, end_date, aggregation="Median"
    )
    t1 = time.perf_counter()
    lat_med = (t1 - t0) * 1000
    assert list(med_df.columns) == RETAILER_AVERAGE_COLUMNS
    assert not med_df.empty
    print(f"  PASS: load_retailer_averages (Median) returned {len(med_df)} rows in {lat_med:.2f} ms")
    results.append(("load_retailer_averages(Median)", lat_med, f"{len(med_df)} rows"))

    # 6. Movers Test
    print("\n[6/7] Testing load_movers_from_db()...")
    t0 = time.perf_counter()
    drops, gains = load_movers_from_db(
        test_retailers, start_date, end_date, top_n=10, scope_retailer="Markets / Gurmar"
    )
    t1 = time.perf_counter()
    lat_movers = (t1 - t0) * 1000
    assert list(drops.columns) == BIGGEST_DROPS_COLUMNS
    assert list(gains.columns) == BIGGEST_GAINS_COLUMNS
    assert not drops.empty and not gains.empty
    print(f"  PASS: load_movers (Gurmar, top 10) returned in {lat_movers:.2f} ms")
    print(f"        Top drop: {drops.iloc[0]['product_name']} ({drops.iloc[0]['drop_from_peak_pct']:.1f}%)")
    print(f"        Top gain: {gains.iloc[0]['product_name']} (+{gains.iloc[0]['change_since_first_pct']:.1f}%)")
    results.append(("load_movers_from_db(single retailer)", lat_movers, "10 drops / 10 gains"))

    t0 = time.perf_counter()
    drops_all, gains_all = load_movers_from_db(
        test_retailers, start_date, end_date, top_n=10, scope_retailer="All retailers"
    )
    t1 = time.perf_counter()
    lat_movers_all = (t1 - t0) * 1000
    assert not drops_all.empty and not gains_all.empty
    print(f"  PASS: load_movers (All retailers, top 10) returned in {lat_movers_all:.2f} ms")
    results.append(("load_movers_from_db(All retailers)", lat_movers_all, "10 drops / 10 gains"))

    # 7. Coverage Test
    print("\n[7/7] Testing load_coverage_from_db()...")
    t0 = time.perf_counter()
    cov_data = load_coverage_from_db(test_retailers, start_date, end_date, category_limit=15)
    t1 = time.perf_counter()
    lat_cov = (t1 - t0) * 1000
    assert "summary" in cov_data and cov_data["summary"]["observation_count"] > 0
    assert list(cov_data["coverage_over_time"].columns) == COVERAGE_OVER_TIME_COLUMNS
    assert list(cov_data["category_coverage"].columns) == CATEGORY_COVERAGE_COLUMNS
    print(f"  PASS: load_coverage_from_db() returned in {lat_cov:.2f} ms")
    print(f"        Summary observations: {cov_data['summary']['observation_count']:,}")
    results.append(("load_coverage_from_db()", lat_cov, f"{cov_data['summary']['observation_count']:,} obs"))

    print("\n" + "=" * 70)
    print("LATENCY BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"{'Function':<42} | {'Latency (ms)':<14} | {'Detail'}")
    print("-" * 70)
    for fn, lat, detail in results:
        print(f"{fn:<42} | {lat:>10.2f} ms  | {detail}")
    print("=" * 70)
    print("ALL TESTS PASSED SUCCESSFULLY!\n")


if __name__ == "__main__":
    run_benchmark()
