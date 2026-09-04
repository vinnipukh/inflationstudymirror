#!/usr/bin/env python3
"""
Build / Rebuild an optimized SQLite WAL database from the partitioned JSON price files.
"""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import time

def init_db(conn: sqlite3.Connection):
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA cache_size = -64000;")

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

    conn.execute("""
    CREATE TABLE IF NOT EXISTS price_observations (
        date TEXT NOT NULL,
        retailer TEXT NOT NULL,
        product_id TEXT NOT NULL,
        price REAL NOT NULL,
        PRIMARY KEY (date, retailer, product_id)
    );
    """)

    conn.commit()

def create_indexes(conn: sqlite3.Connection):
    print("Creating indexes...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_product_retailer ON product_prices(retailer);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_product_category ON product_prices(category);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_product_name ON product_prices(product_name);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_date_retailer ON price_observations(date, retailer);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_retailer_product ON price_observations(retailer, product_id);")
    conn.commit()

def json_to_sqlite(json_dir: Path, db_path: Path, include_observations: bool = True):
    print(f"=== Building SQLite Database from JSON ===")
    print(f"Source JSON Directory: {json_dir}")
    print(f"Target SQLite Database: {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        os.remove(db_path)
    for ext in ["-wal", "-shm"]:
        sidecar = Path(str(db_path) + ext)
        if sidecar.exists():
            os.remove(sidecar)

    conn = sqlite3.connect(str(db_path))
    init_db(conn)

    json_files = sorted(list(json_dir.glob("*.json")))
    if not json_files:
        print(f"No JSON files found in {json_dir}")
        conn.close()
        return

    start_time = time.time()
    total_products = 0
    total_obs = 0

    for jf in json_files:
        t_file = time.time()
        # Derive original retailer name from file stem
        retailer_name = jf.stem.replace("_", " / ")
        # Fix known patterns
        retailer_name = retailer_name.replace("ClothingStores / Vakko", "ClothingStores / Vakko")
        retailer_name = retailer_name.replace("Markets / Gurmar", "Markets / Gurmar")
        retailer_name = retailer_name.replace("Cosmetics / Watson", "Cosmetics / Watson")
        retailer_name = retailer_name.replace("Health / Diagnostic / Surgical / Services", "Health / Diagnostic&Surgical Services")
        retailer_name = retailer_name.replace("ConstructionSuppliesMarkets / TasciYapiMarket", "ConstructionSuppliesMarkets / TasciYapiMarket")
        retailer_name = retailer_name.replace("ConstructionSuppliesMarkets / yapimaks", "ConstructionSuppliesMarkets / yapimaks")
        retailer_name = retailer_name.replace("HousesRent / Kayseri", "HousesRent / Kayseri")
        retailer_name = retailer_name.replace("HousesRent / Sivas", "HousesRent / Sivas")
        retailer_name = retailer_name.replace("HousesRent / Tokat", "HousesRent / Tokat")
        retailer_name = retailer_name.replace("HousesRent / Emlakjet", "HousesRent / Emlakjet")

        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)

        product_rows = []
        obs_rows = []

        for pid, pdata in data.items():
            prices = pdata.get("prices", {})
            sorted_dates = sorted(prices.keys())
            first_date = sorted_dates[0] if sorted_dates else None
            last_date = sorted_dates[-1] if sorted_dates else None
            latest_price = prices.get(last_date) if last_date else pdata.get("latest_price")
            min_price = pdata.get("min_price", min(prices.values()) if prices else None)
            max_price = pdata.get("max_price", max(prices.values()) if prices else None)

            product_rows.append((
                str(pid),
                retailer_name,
                pdata.get("name"),
                pdata.get("category"),
                first_date,
                last_date,
                latest_price,
                min_price,
                max_price,
                len(prices),
                json.dumps(prices)
            ))

            if include_observations:
                for d, pr in prices.items():
                    obs_rows.append((d, retailer_name, str(pid), float(pr)))

        conn.executemany("""
        INSERT OR REPLACE INTO product_prices (
            product_id, retailer, product_name, category, first_date, last_date,
            latest_price, min_price, max_price, observations_count, price_history
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, product_rows)

        if include_observations and obs_rows:
            conn.executemany("""
            INSERT OR REPLACE INTO price_observations (
                date, retailer, product_id, price
            ) VALUES (?, ?, ?, ?);
            """, obs_rows)

        conn.commit()
        total_products += len(product_rows)
        total_obs += len(obs_rows)
        print(f"  Loaded {jf.name}: {len(product_rows):,} products ({time.time() - t_file:.2f}s)")

    create_indexes(conn)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn.close()

    elapsed = time.time() - start_time
    db_size_mb = os.path.getsize(db_path) / 1024 / 1024
    print(f"\n=== Build Complete ===")
    print(f"Total Products: {total_products:,}")
    if include_observations:
        print(f"Total Price Observations: {total_obs:,}")
    print(f"SQLite DB: {db_path} ({db_size_mb:.2f} MB)")
    print(f"Elapsed Time: {elapsed:.2f}s")

def main():
    parser = argparse.ArgumentParser(description="Build SQLite DB from JSON price history")
    parser.add_argument("--json-dir", default="InflationItems/prices_json", help="Path to JSON directory")
    parser.add_argument("--db-path", default="InflationItems/prices.db", help="Path to output SQLite database")
    parser.add_argument("--no-obs", action="store_true", help="Do not populate price_observations table (keeps DB smaller)")
    args = parser.parse_args()

    json_dir = Path(args.json_dir).resolve()
    db_path = Path(args.db_path).resolve()
    json_to_sqlite(json_dir, db_path, include_observations=not args.no_obs)

if __name__ == "__main__":
    main()
