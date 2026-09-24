"""materialize.py — series.csv -> the single partitioned JSON price store.

Maintains the canonical EpeyKatfg price store:
    InflationItems/prices_json/EpeyKatfg.json
built by build_prices_json.py: a change-only (sparse) date->price map per
product, with entries written only when a product's price differs from its
last recorded value.  Run after every pull so the store stays current; the
old per-date CSVs (epeykatfg_YYYY-MM-DD.csv) are retired — the calculators
now read series.csv directly via katfg_reader.py.

Usage: python materialize.py [--days 45] [--all] [--csv] [--skip-json]
    --csv    also write per-date store-style CSVs (legacy, no longer consumed)
    --skip-json    skip the JSON update (not recommended)
"""
import csv, os, sys
from collections import defaultdict

# Single source of truth: compute-layer config (Inflations/Codes/EpeyKatfg)
_INFLATION_ITEMS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .../InflationItems
_PROJECT_ROOT = os.path.dirname(_INFLATION_ITEMS)      # repo root
_TUIK_DIR = os.path.join(_PROJECT_ROOT, "Inflations", "Codes", "EpeyKatfg")
sys.path.insert(0, _TUIK_DIR)
from tuik_config import EPEY_CATEGORY_TO_TUIK as CAT_MAP  # noqa: E402


def materialize(series_csv, out_dir, days=45, all_dates=False, write_csvs=False):
    if not write_csvs:
        return
    os.makedirs(out_dir, exist_ok=True)
    bydate = defaultdict(list)
    with open(series_csv, encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd, None)
        for url, cat, pid, date, price, rng in rd:
            if not date:
                continue
            bydate[date].append((url, cat, pid, date, price, rng))
    from datetime import datetime as _dt
    dates = sorted(bydate, key=lambda s: _dt.strptime(s, "%d.%m.%Y"))
    if not all_dates and len(dates) > days:
        dates = dates[-days:]
    for d in dates:
        iso = _dt.strptime(d, "%d.%m.%Y").strftime("%Y-%m-%d")  # aggregator token format
        path = os.path.join(out_dir, f"epeykatfg_{iso}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["product_name", "price", "Tarih", "UrunID", "tuik_category"])
            seen = {}  # pid -> [min_price, row]
            for row in bydate[d]:
                url, cat, pid, date, price, rng = row
                pval = float(price)
                if pid not in seen or pval < seen[pid][0]:
                    seen[pid] = [pval, row]
            for _, row in seen.values():
                url, cat, pid, date, price, rng = row
                name = url.split("/")[4].replace(".html", "").replace("-", " ") if "/" in url else pid
                w.writerow([name, price, date, pid, CAT_MAP.get(cat, "")])
    print(f"materialized {len(dates)} dates -> {out_dir} (last {len(dates)}d)")


if __name__ == "__main__":
    argc = len(sys.argv)
    all_dates = "--all" in sys.argv
    skip_json = "--skip-json" in sys.argv
    write_csvs = "--csv" in sys.argv
    days = int(sys.argv[argc - 1]) if argc > 1 and sys.argv[1].isdigit() and not all_dates else 45
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # InflationItems/
    series = os.path.join(base, "Datas", "EpeyKatfg", "series.csv")
    out = os.path.join(base, "Datas", "EpeyKatfg")
    materialize(series, out, days=days, all_dates=all_dates, write_csvs=write_csvs)
    if not skip_json:
        import build_prices_json
        json_path = os.path.join(base, "prices_json", "EpeyKatfg.json")
        build_prices_json.build_json(series, json_path, update=True)
