"""Coverage check: every category the Vakko scraper queries, vs the latest CSV.

For each category from vakko_categories.xml (using the scraper's exact parsing),
fetch page 1 of products from the Vakko API and test how many of those product
codes appear in the latest CSV. Categories with 0% membership are missing from
the output (either never queried or dedup'd out wrongly).

Run:  python scripts/check_vakko_coverage.py [csv_path]
"""
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
XML_PATH = ROOT / "Codes" / "ClothingStores" / "Vakko" / "vakko_categories.xml"
CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else max(
    (ROOT / "Datas" / "ClothingStores" / "Vakko").glob("vakko_*.csv")
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


def scraper_categories(xml_text: str) -> list[tuple[str, str]]:
    """Mirror vakko_master_scraper.py category extraction (order preserved)."""
    cats: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for link in re.findall(r"<loc>(.*?)</loc>", xml_text):
        link = link.strip()
        m = re.search(r"-c-([a-zA-Z0-9_-]+)/?$", link)
        if not m:
            continue
        kat_id = m.group(1)
        if "/kadin" in link and "/outlet" not in link:
            group = "Kadin"
        elif "/erkek" in link and "/outlet" not in link:
            group = "Erkek"
        elif ("/ayakkabi-canta" in link or "/shoes-bags" in link) and "/outlet" not in link:
            group = "Shoes_Bags"
        else:
            continue
        if (group, kat_id) not in seen:
            seen.add((group, kat_id))
            cats.append((group, kat_id))
    return cats


def main() -> None:
    csv_df = pd.read_csv(CSV_PATH)
    csv_codes = set(csv_df["Stok Kodu"].astype(str))
    print(f"CSV: {CSV_PATH.name} | unique products: {len(csv_codes)}")

    xml_text = XML_PATH.read_text(encoding="utf-8")
    cats = scraper_categories(xml_text)
    print(f"Categories the scraper queries: {len(cats)}\n")

    session = requests.Session()
    session.headers.update(HEADERS)

    missing_any = False
    for group, kat_id in cats:
        params = {
            "fields": "FULL,facets,breadcrumbs,pagination(DEFAULT),sorts(DEFAULT)",
            "query": f":relevance:allCategories:{kat_id}",
            "pageSize": "48",
            "lang": "tr",
            "curr": "TRY",
            "currentPage": "0",
        }
        try:
            r = session.get(API_URL, params=params, timeout=30)
            if r.status_code != 200:
                print(f"  {group:9s} {kat_id:8s} HTTP {r.status_code}  (skipped by scraper)")
                continue
            data = r.json()
            prods = data.get("products", [])
            total = data.get("pagination", {}).get("totalResults", 0)
            codes = [p.get("code") for p in prods]
            in_csv = sum(1 for c in codes if c in csv_codes)
            pct = 100.0 * in_csv / len(codes) if codes else 0.0
            flag = "" if pct == 100.0 or total == 0 else "  <<< NOT FULLY IN CSV"
            if pct < 100.0 and total > 0:
                missing_any = True
            bc = ", ".join(b.get("facetValueName", "") for b in data.get("breadcrumbs", [])[:2])
            print(f"  {group:9s} {kat_id:8s} total={total:6d} page1={in_csv:3d}/{len(codes):3d} ({pct:5.1f}%)  {bc}{flag}")
        except Exception as e:  # noqa: BLE001
            print(f"  {group:9s} {kat_id:8s} ERROR {e}")
        time.sleep(0.6)

    print()
    if missing_any:
        print("RESULT: some queried categories have products NOT in the CSV.")
    else:
        print("RESULT: every queried category's products are fully present in the CSV.")
    print("(Categories never in the XML sitemap are not checked — compare with the live site.)")


if __name__ == "__main__":
    main()
