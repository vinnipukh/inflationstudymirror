"""build_prices_json.py — EpeyKatfg: master series.csv -> single partitioned prices_json.

Converts the EpeyKatfg harvest (InflationItems/Datas/EpeyKatfg/series.csv, one row
per product/date) into a single retailer-partitioned JSON file in the same schema as
InflationItems/prices_json/*.json (e.g. Markets_Gurmar.json):

    {
      "<pid>": {
        "name":        "<product display name>",
        "category":    "<epey category slug>",
        "latest_price": <float>,
        "min_price":    <float>,
        "max_price":    <float>,
        "prices": { "<YYYY-MM-DD>": <float>, ... }
      }, ...
    }

The "prices" map is stored SPARSE (change-only): a date is written only when the
product's price differs from its previously recorded value.  The price on any
given day is the value of the most recent key <= that day, so the map is a
lossless step series.  Compared with the old per-day materialized CSVs
(epeykatfg_YYYY-MM-DD.csv, 962,441 rows / 50 MB across 1,084 files), this
collapses to ~169k change points in a single file (~6 MB).

The series.csv master already stores the daily-lowest offer (range_id windows
36/12/6 months); materialize.py collapses overlapping windows by taking the min
price per (pid, date).  This script applies the same min-per-(pid,date) collapse
before building the change-only series, so it is byte-identical to what the
aggregator sees in the per-date CSVs.

Usage:
    python build_prices_json.py                          # rebuild from scratch
    python build_prices_json.py --update                 # append new change events only
    python build_prices_json.py --series PATH --out PATH
"""
import argparse
import json
import os
import sys
from pathlib import Path

# .../InflationItems/Codes/EpeyKatfg -> .../InflationItems
_ITEMS = Path(__file__).resolve().parent.parent.parent

DEFAULT_SERIES = _ITEMS / "Datas" / "EpeyKatfg" / "series.csv"
DEFAULT_OUT = _ITEMS / "prices_json" / "EpeyKatfg.json"


def name_from_url(url: str, pid: str) -> str:
    """Product display name, same derivation as materialize.py (slug -> words)."""
    if "/" in url:
        return url.split("/")[4].replace(".html", "").replace("-", " ")
    return str(pid)


def collapse_min_per_date(series_csv: Path):
    """Read series.csv -> {pid: [(iso_date, price)]} with min price per (pid,date)."""
    import csv
    from datetime import datetime

    per = {}          # pid -> {iso: price}
    cats = {}         # pid -> epey category
    names = {}        # pid -> display name
    with open(series_csv, encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd, None)
        for url, cat, pid, date, price, rng in rd:
            if not date or not price:
                continue
            iso = datetime.strptime(date, "%d.%m.%Y").strftime("%Y-%m-%d")
            try:
                pval = float(price)
            except ValueError:
                continue
            d = per.setdefault(pid, {})
            if iso not in d or pval < d[iso]:
                d[iso] = pval
            cats.setdefault(pid, cat)
            names.setdefault(pid, name_from_url(url, pid))
    out = {}
    for pid, dm in per.items():
        out[pid] = {"name": names.get(pid, pid), "category": cats.get(pid, ""),
                    "dates": sorted(dm), "prices": [dm[d] for d in sorted(dm)]}
    return out


def build_series(series_csv: Path) -> dict:
    """Return the full product dict keyed by pid (sparse prices not yet applied)."""
    return collapse_min_per_date(series_csv)


def apply_sparse(prices_map: dict) -> dict:
    """prices: {iso: price} with only change events kept (step-series, lossless)."""
    sparse = {}
    last = None
    for iso in sorted(prices_map):
        p = prices_map[iso]
        if p != last:
            sparse[iso] = p
            last = p
    return sparse


def build_json(series_csv: Path, out_path: Path, update: bool = False):
    series_csv = Path(series_csv)
    out_path = Path(out_path)
    products = build_series(series_csv)
    if update and out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = {}

    # Merge: keep existing keys, add/refresh new data, then rebuild metadata.
    result = {}
    for pid in products:
        p = products[pid]
        old = existing.get(pid, {})
        merged = dict(old.get("prices", {}))
        # Add any new/known dates; overwrite if an older price was wrong.
        merged.update({iso: pr for iso, pr in zip(p["dates"], p["prices"])})
        sparse = apply_sparse(merged)
        vals = list(sparse.values())
        result[pid] = {
            "name": p["name"],
            "category": p["category"],
            "latest_price": vals[-1],
            "min_price": min(vals),
            "max_price": max(vals),
            "prices": sparse,
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")
    npts = sum(len(v["prices"]) for v in result.values())
    print(f"Wrote {out_path} ({len(result):,} products, {npts:,} change-points, "
          f"{os.path.getsize(out_path)/1e6:.2f} MB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build/update EpeyKatfg prices_json")
    ap.add_argument("--series", default=str(DEFAULT_SERIES))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--update", action="store_true", help="append new change events to existing file")
    args = ap.parse_args()
    build_json(Path(args.series), Path(args.out), update=args.update)
