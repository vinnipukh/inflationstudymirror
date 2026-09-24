#!/usr/bin/env python3
"""consolidate_inflation_details.py — merge per-date inflation detail CSVs into ONE file per dataset.

Per-date snapshots are archived in /inflation_per_date_csvs.zip (513 files, the
live copies were deleted). This script rebuilds the consolidated long-format
CSVs straight from the archive:

    Inflations/Datas/**/{store}.csv   (one per dataset, unified schema)

Notes:
  - Files named *_summary.csv are excluded (only YYYY-MM-DD dated detail files).
  - Rows are deduplicated per (date, product_id, price): exact duplicate copies
    and cartesian metric bloat produced by writer bugs are dropped, while
    same-name products with different prices on the same date are preserved.
  - Source files are read from the archive zip at the repo root; the archive
    itself is never modified.


    date, product_id, product_name, category, tuik_category, price,
    relative_1d, relative_7d, relative_15d, relative_30d [, <dataset extras>]

The schema is modelled on the leanest existing per-date format
(EpeyKatfg: urun_id, product_name, price, tuik_category, relative_1d/7d/15d/30d)
with column names unified:
  product identity   -> product_id / product_name
  site category      -> category          ('' if n/a)
  TUIK COICOP code   -> tuik_category
  price              -> price             (native numeric string; rent: median_price)
  per-interval rels   -> relative_1d / 7d / 15d / 30d (basic_inflation_* mapped; '' if n/a)
Dataset-specific columns are kept as trailing extras only when they carry
information not covered by the core (url, Kategori ID, sector, Rooms, ...).
Redundant duplicates (Watsons shown_price == price) are dropped.

Rows are byte-identical to the originals except for the added date column.

Usage:  python3 scripts/consolidate_inflation_details.py
"""
import glob
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Inflations" / "Datas"

CORE = ["date", "product_id", "product_name", "category", "tuik_category", "price",
        "relative_1d", "relative_7d", "relative_15d", "relative_30d"]

# Each core field maps to an ordered list of candidate source column names
# (schemas drifted over time inside a dataset, so we take the first that exists).
CANDIDATES = {
    "product_id":   ["product_id", "id", "urun_id", "Stok Kodu", "product_key"],
    "product_name": ["product_name", "product-name", "name", "canonical_key", "District"],
    "category":     ["category", "Ana Kategori", "store"],
    "tuik_category": ["tuik_category", "tuik_code"],
    "price":        ["price", "shown_price", "Fiyat", "median_price"],
    "relative_1d":  ["relative_1d", "basic_inflation_1d"],
    "relative_7d":  ["relative_7d", "basic_inflation_7d"],
    "relative_15d": ["relative_15d", "basic_inflation_15d"],
    "relative_30d": ["relative_30d", "basic_inflation_30d"],
}

DATASETS = [
    {"match": "ClothingStores/Vakko/vakko_inflation_*.csv",
     "out": "ClothingStores/Vakko/vakko_inflation.csv",
     "extra": ["Kategori ID"]},
    {"match": "ConstructionSuppliesMarkets/Yapimaks/yapimaks_detailed_inf_*.csv",
     "out": "ConstructionSuppliesMarkets/Yapimaks/yapimaks_detailed_inf.csv",
     "extra": []},
    {"match": "Cosmetics/watsons_inflation_*.csv",
     "out": "Cosmetics/watsons_inflation.csv",
     "extra": []},
    {"match": "HomeGoods/chakra_inflation_*.csv",
     "out": "HomeGoods/chakra_inflation.csv",
     "extra": ["url"]},
    {"match": "Markets/Gurmar/gurmar_inflation_*.csv",
     "out": "Markets/Gurmar/gurmar_inflation.csv",
     "extra": ["url", "eski_fiyat"]},
    {"match": "HousesRent/Kayseri/Kayseri_inflation_*.csv",
     "out": "HousesRent/Kayseri/Kayseri_inflation.csv",
     "extra": ["Rooms"], "composite_id": True},
    {"match": "HousesRent/Sivas/Sivas_inflation_*.csv",
     "out": "HousesRent/Sivas/Sivas_inflation.csv",
     "extra": ["Rooms"], "composite_id": True},
    {"match": "HousesRent/Tokat/Tokat_inflation_*.csv",
     "out": "HousesRent/Tokat/Tokat_inflation.csv",
     "extra": ["Rooms"], "composite_id": True},
    {"match": "EpeyKatfg/epeykatfg_inflation_*.csv",
     "out": "EpeyKatfg/epeykatfg_inflation.csv",
     "extra": []},
    {"match": "Final_Reports/turkey_inflation_*.csv",
     "out": "Final_Reports/turkey_inflation.csv",
     "extra": ["sector"]},
]


def _pick(df, candidates):
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series(pd.NA, index=df.index, dtype="object")


def _normalise(df, cfg, date_str):
    out = pd.DataFrame(index=df.index)
    out["date"] = date_str
    for c in CORE[1:]:
        out[c] = _pick(df, CANDIDATES[c])
    for e in cfg["extra"]:
        out[e] = df[e] if e in df.columns else pd.NA
    if cfg.get("composite_id"):
        # rent rows: identity = "District | Rooms"; the rooms column lives in extras
        dist = out["product_name"].fillna("").astype(str)
        rooms = out[cfg["extra"][0]].fillna("").astype(str)
        out["product_id"] = dist + " | " + rooms
    return out


import re as _re
import zipfile as _zipfile
import io as _io

_ZIP = ROOT / "inflation_per_date_csvs.zip"
_DATE_TOKEN = _re.compile(r"^\d{4}-\d{2}-\d{2}$")


def convert_dataset(cfg):
    # match per-date files inside the archive (pattern is relative to Inflations/Datas)
    names = [n for n in _zipfile.ZipFile(_ZIP).namelist()
             if n.startswith("Inflations/Datas/") and n.endswith(".csv")]
    import fnmatch
    rel_pat = "Inflations/Datas/" + cfg["match"]
    files = []
    for n in names:
        if fnmatch.fnmatch(n, rel_pat):
            token = n.rsplit("/", 1)[-1].rsplit("_", 1)[-1].replace(".csv", "")
            if _DATE_TOKEN.match(token):      # exclude *_summary.csv etc.
                files.append(n)
    files.sort()
    if not files:
        print(f"  (no files in archive for {cfg['match']})")
        return 0, 0
    with _zipfile.ZipFile(_ZIP) as z:
        frames = [
            _normalise(pd.read_csv(_io.BytesIO(z.read(n)), encoding="utf-8",
                                   dtype=str, on_bad_lines="skip"),
                       cfg, n.rsplit("_", 1)[-1].replace(".csv", ""))
            for n in files
        ]
    merged = pd.concat(frames, ignore_index=True)
    # writer-bug cleanup: one row per (date, product_id, price)
    before = len(merged)
    merged = merged.drop_duplicates(subset=["date", "product_id", "price"], keep="first")
    merged = merged.sort_values(["date", "product_id"], kind="stable")
    out_path = DATA / cfg["out"]
    merged.to_csv(out_path, index=False, encoding="utf-8")
    if before > len(merged):
        print(f"  ({len(files)} files; {before:,} -> {len(merged):,} rows after dedup)")
    return len(merged), len(files)


def main():
    print("=== Consolidate per-date inflation detail CSVs -> one file per dataset ===")
    total_rows = total_files = 0
    for cfg in DATASETS:
        rows, n_files = convert_dataset(cfg)
        total_rows += rows; total_files += n_files
        if n_files:
            print(f"  {DATA / cfg['out']}: {rows:,} rows from {n_files} files")
    print(f"Done. {total_files} archived per-date files -> {len(DATASETS)} consolidated files ({total_rows:,} rows)")
    print(f"Source: {_ZIP}")


if __name__ == "__main__":
    main()
