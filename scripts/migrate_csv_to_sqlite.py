#!/usr/bin/env python3
"""
Migrate raw scraped price CSVs from InflationItems/Datas into an optimized SQLite WAL database.
Maintains both normalized price_observations and aggregate product_prices with JSON time-series history.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import pandas as pd
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Import existing domain logic from inflation_dashboard
from inflation_dashboard.domain.prices import (
    PRICE_COLUMNS,
    build_product_frame,
    coerce_price,
)
from inflation_dashboard.adapters.csv_price_repository import detect_retailer

DATE_PATTERNS = [
    # YYYY-MM-DD or YYYY_MM_DD
    (re.compile(r"(20\d{2})[-_](\d{2})[-_](\d{2})"), lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
    # DD-MM-YYYY or DD_MM_YYYY
    (re.compile(r"(\d{2})[-_](\d{2})[-_](20\d{2})"), lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}"),
]

def parse_date(filename: str) -> str | None:
    for pat, formatter in DATE_PATTERNS:
        match = pat.search(filename)
        if match:
            return formatter(match)
    return None

def init_db(conn: sqlite3.Connection):
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA cache_size = -64000;")  # 64MB cache

    conn.execute("""
    CREATE TABLE IF NOT EXISTS ingested_files (
        file_path TEXT PRIMARY KEY,
        retailer TEXT NOT NULL,
        date TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        mtime REAL NOT NULL,
        rows_ingested INTEGER NOT NULL,
        ingested_at TEXT NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS price_observations (
        date TEXT NOT NULL,
        retailer TEXT NOT NULL,
        product_id TEXT NOT NULL,
        product_name TEXT,
        category TEXT,
        price REAL NOT NULL,
        source_file TEXT,
        PRIMARY KEY (date, retailer, product_id)
    );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_date_retailer ON price_observations(date, retailer);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_retailer_product ON price_observations(retailer, product_id);")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS product_prices (
        product_id TEXT NOT NULL,
        retailer TEXT NOT NULL,
        product_name TEXT,
        category TEXT,
        first_date TEXT,
        last_date TEXT,
        latest_price REAL,
        min_price REAL,
        max_price REAL,
        observations_count INTEGER,
        price_history JSON,
        PRIMARY KEY (retailer, product_id)
    );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_product_retailer ON product_prices(retailer);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_product_category ON product_prices(category);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_product_name ON product_prices(product_name);")
    conn.commit()

def migrate(datas_dir: Path, db_path: Path, force: bool = False):
    print(f"=== Starting Price Data Migration to SQLite ===")
    print(f"Source directory: {datas_dir}")
    print(f"Target SQLite DB: {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    init_db(conn)

    # Check already ingested files
    ingested = {}
    if not force:
        cur = conn.execute("SELECT file_path, mtime, file_size FROM ingested_files;")
        for row in cur.fetchall():
            ingested[row[0]] = (row[1], row[2])

    csv_files = sorted(list(datas_dir.rglob("*.csv")))
    total_files = len(csv_files)
    print(f"Found {total_files} CSV files in {datas_dir}")

    files_to_process = []
    for p in csv_files:
        rel_str = str(p.relative_to(datas_dir.parent))
        try:
            st = p.stat()
        except OSError:
            continue
        if not force and rel_str in ingested:
            old_mtime, old_size = ingested[rel_str]
            if abs(old_mtime - st.st_mtime) < 1e-3 and old_size == st.st_size:
                continue
        files_to_process.append((p, rel_str, st.st_size, st.st_mtime))

    print(f"Files to ingest (new or modified): {len(files_to_process)} / {total_files}")
    if not files_to_process:
        print("All files are already up to date.")
        conn.close()
        return

    start_time = time.time()
    total_rows = 0
    skipped_count = 0
    batch_rows = []
    batch_file_records = []

    for i, (p, rel_str, f_size, f_mtime) in enumerate(files_to_process, 1):
        date_str = parse_date(p.name)
        if not date_str:
            skipped_count += 1
            continue
        retailer = detect_retailer(p)

        try:
            df = pd.read_csv(
                p,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
                on_bad_lines="skip"
            )
        except Exception:
            skipped_count += 1
            continue

        if df.empty:
            skipped_count += 1
            continue

        price_col = next((c for c in PRICE_COLUMNS if c in df.columns), None)
        if not price_col:
            skipped_count += 1
            continue

        try:
            date_val = pd.to_datetime(date_str)
            p_frame = build_product_frame(df, retailer, price_col, date_val, p.name)
        except Exception:
            skipped_count += 1
            continue

        if p_frame.empty:
            skipped_count += 1
            continue

        p_frame = p_frame.dropna(subset=["price", "product_id"])
        if p_frame.empty:
            skipped_count += 1
            continue

        file_rows = [
            (
                date_str,
                retailer,
                str(row.product_id).strip(),
                str(row.product_name or "").strip(),
                str(row.category or "Uncategorized").strip(),
                float(row.price),
                rel_str
            )
            for row in p_frame.itertuples(index=False)
        ]

        batch_rows.extend(file_rows)
        batch_file_records.append((
            rel_str,
            retailer,
            date_str,
            f_size,
            f_mtime,
            len(file_rows),
            datetime.utcnow().isoformat()
        ))
        total_rows += len(file_rows)

        # Batch insert every 50 files
        if len(batch_file_records) >= 50:
            conn.executemany(
                "INSERT OR REPLACE INTO price_observations VALUES (?, ?, ?, ?, ?, ?, ?);",
                batch_rows
            )
            conn.executemany(
                "INSERT OR REPLACE INTO ingested_files VALUES (?, ?, ?, ?, ?, ?, ?);",
                batch_file_records
            )
            conn.commit()
            batch_rows = []
            batch_file_records = []
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            print(f"[{i}/{len(files_to_process)}] Ingested {total_rows:,} rows ({rate:.1f} files/s, elapsed: {elapsed:.1f}s)")

    # Insert remaining batch
    if batch_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO price_observations VALUES (?, ?, ?, ?, ?, ?, ?);",
            batch_rows
        )
        conn.executemany(
            "INSERT OR REPLACE INTO ingested_files VALUES (?, ?, ?, ?, ?, ?, ?);",
            batch_file_records
        )
        conn.commit()

    print(f"\nObservation ingestion complete. Total rows inserted/updated: {total_rows:,}")
    print(f"Skipped files (undated, empty, or unparseable): {skipped_count}")

    # Build / refresh product_prices table with JSON history
    print("\nBuilding product_prices table with JSON price history...")
    t_rebuild = time.time()
    conn.execute("DELETE FROM product_prices;")
    conn.execute("""
    INSERT INTO product_prices (
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
    )
    SELECT 
        product_id,
        retailer,
        max(product_name) AS product_name,
        max(category) AS category,
        min(date) AS first_date,
        max(date) AS last_date,
        (
            SELECT p2.price 
            FROM price_observations p2 
            WHERE p2.retailer = p.retailer AND p2.product_id = p.product_id 
            ORDER BY p2.date DESC 
            LIMIT 1
        ) AS latest_price,
        min(price) AS min_price,
        max(price) AS max_price,
        count(*) AS observations_count,
        json_group_object(date, price) AS price_history
    FROM (
        SELECT * FROM price_observations ORDER BY date ASC
    ) p
    GROUP BY retailer, product_id;
    """)
    conn.commit()
    print(f"Built product_prices table in {time.time() - t_rebuild:.2f}s")

    # Final stats
    p_count = conn.execute("SELECT count(*) FROM product_prices;").fetchone()[0]
    obs_count = conn.execute("SELECT count(*) FROM price_observations;").fetchone()[0]
    db_size_mb = os.path.getsize(db_path) / 1024 / 1024
    total_elapsed = time.time() - start_time

    print(f"\n=== Migration Summary ===")
    print(f"Distinct Products: {p_count:,}")
    print(f"Price Observations: {obs_count:,}")
    print(f"SQLite DB File: {db_path} ({db_size_mb:.2f} MB)")
    print(f"Total time elapsed: {total_elapsed:.2f}s")

    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Migrate price CSVs to SQLite database")
    parser.add_argument("--datas-dir", default="InflationItems/Datas", help="Path to Datas directory")
    parser.add_argument("--db-path", default="InflationItems/prices.db", help="Path to output SQLite database")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion of all files")
    args = parser.parse_args()

    datas_dir = Path(args.datas_dir).resolve()
    db_path = Path(args.db_path).resolve()
    migrate(datas_dir, db_path, force=args.force)

if __name__ == "__main__":
    main()
