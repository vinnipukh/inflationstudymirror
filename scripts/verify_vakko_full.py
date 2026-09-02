"""Definitive check: full product+price comparison of the latest Vakko CSV
against the live API (all pages of the categories that appear in the CSV).

Run:  python scripts/verify_vakko_full.py [csv_path]
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else max(
    (ROOT / "InflationItems" / "Datas" / "ClothingStores" / "Vakko").glob("vakko_*.csv")
)

API_URL = "https://api.vakko.com/occ/v2/vsite/products/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Platform": "WEB",
    "Origin": "https://www.vakko.com",
    "Referer": "https://www.vakko.com/",
}


def main() -> None:
    csv_df = pd.read_csv(CSV_PATH)
    csv_map = dict(zip(csv_df["Stok Kodu"].astype(str), csv_df["product-price"].astype(str)))
    print(f"CSV: {CSV_PATH.name} | products: {len(csv_map)}")

    cats = sorted(csv_df["Kategori ID"].astype(str).unique().tolist())
    print(f"Categories in CSV: {cats}\n")

    session = requests.Session()
    session.headers.update(HEADERS)

    api_map: dict[str, str] = {}
    for kat_id in cats:
        page = 0
        total_pages = 1
        while page < total_pages:
            params = {
                "fields": "FULL,facets,breadcrumbs,pagination(DEFAULT),sorts(DEFAULT)",
                "query": f":relevance:allCategories:{kat_id}",
                "pageSize": "48",
                "lang": "tr",
                "curr": "TRY",
                "currentPage": str(page),
            }
            r = session.get(API_URL, params=params, timeout=30)
            if r.status_code != 200:
                print(f"  cat {kat_id} page {page}: HTTP {r.status_code} — aborting this category")
                break
            data = r.json()
            total_pages = data.get("pagination", {}).get("totalPages", 1)
            for p in data.get("products", []):
                price = (p.get("price") or {}).get("formattedValue") or "Fiyat Yok"
                api_map[p.get("code")] = price
            page += 1
            if page < total_pages:
                time.sleep(0.25)
        print(f"  cat {kat_id}: fetched {len([c for c in api_map])} total so far")

    api_codes = set(api_map)
    csv_codes = set(csv_map)
    print(f"\nAPI unique: {len(api_codes)} | CSV unique: {len(csv_codes)}")
    print(f"Only in CSV (not on API now): {len(csv_codes - api_codes)}")
    print(f"Only on API now (not in CSV): {len(api_codes - csv_codes)}")

    # Price comparison for products present in both
    common = csv_codes & api_codes
    diffs = [(c, csv_map[c], api_map[c]) for c in common if csv_map[c] != api_map[c]]
    print(f"Common: {len(common)} | price differences: {len(diffs)}")
    for c, a, b in diffs[:15]:
        print(f"    {c}: CSV={a} API={b}")

    if diffs:
        changed = len({c for c, _, _ in diffs if "Fiyat Yok" not in (csv_map[c], api_map[c])})
        print(f"  of which real price changes (not 'Fiyat Yok'): {changed}")


if __name__ == "__main__":
    main()
