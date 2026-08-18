"""Replay the scraper's scan order over the 261 categories (page 1 each) and
count how many categories add NEW products vs. return pure duplicates.
"""
import re
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "Datas" / "ClothingStores" / "Vakko" / "vakko_2026-08-18.csv"
XML_PATH = ROOT / "Codes" / "ClothingStores" / "Vakko" / "vakko_categories.xml"
API_URL = "https://api.vakko.com/occ/v2/vsite/products/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Platform": "WEB",
    "Origin": "https://www.vakko.com",
    "Referer": "https://www.vakko.com/",
}


def xml_kategorileri(xml_metni):
    kategoriler = {"Kadin": [], "Erkek": [], "Shoes_Bags": []}
    for link in re.findall(r"<loc>(.*?)</loc>", xml_metni):
        link = link.strip()
        match = re.search(r"-c-([a-zA-Z0-9_-]+)/?$", link)
        if match:
            kat_id = match.group(1)
            if "/kadin" in link and "/outlet" not in link and kat_id not in kategoriler["Kadin"]:
                kategoriler["Kadin"].append(kat_id)
            elif "/erkek" in link and "/outlet" not in link and kat_id not in kategoriler["Erkek"]:
                kategoriler["Erkek"].append(kat_id)
            elif ("/ayakkabi-canta" in link or "/shoes-bags" in link) and "/outlet" not in link \
                    and kat_id not in kategoriler["Shoes_Bags"]:
                kategoriler["Shoes_Bags"].append(kat_id)
    return kategoriler


def main():
    # Rebuild the merged category list exactly like the scraper does
    yerel = xml_kategorileri(XML_PATH.read_text(encoding="utf-8"))
    req = requests.get("https://www.vakko.com/sitemap.xml", headers=HEADERS, timeout=30)
    cat_urls = [u.strip() for u in re.findall(r"<loc>(.*?)</loc>", req.text)
                if u.strip().endswith("/sitemap/Category.xml")]
    tr = [u for u in cat_urls if not re.search(r"/(en|el-gr|en-gr|en-eu)/", u)]
    resp = requests.get((tr or cat_urls)[0], headers=HEADERS, timeout=30)
    canli = xml_kategorileri(resp.text)

    birlesik = {}
    for grup in yerel:
        eski_set = set(yerel[grup])
        yeni_liste = canli.get(grup, [])
        birlesik[grup] = list(yerel[grup]) + [i for i in yeni_liste if i not in eski_set]
    for grup in canli:
        if grup not in birlesik:
            birlesik[grup] = list(canli[grup])

    session = requests.Session()
    session.headers.update(HEADERS)
    gorulen = set()
    yeni_ekleyen = []
    dupe = []
    for grup, ids in birlesik.items():
        for kat_id in ids:
            params = {
                "fields": "FULL,facets,breadcrumbs,pagination(DEFAULT),sorts(DEFAULT)",
                "query": f":relevance:allCategories:{kat_id}",
                "pageSize": "48", "lang": "tr", "curr": "TRY", "currentPage": "0",
            }
            r = session.get(API_URL, params=params, timeout=30)
            if r.status_code != 200:
                print(f"  {kat_id}: HTTP {r.status_code}")
                continue
            d = r.json()
            codes = [p.get("code") for p in d.get("products", [])]
            total = d.get("pagination", {}).get("totalResults", 0)
            yeni = [c for c in codes if c not in gorulen]
            gorulen.update(codes)
            bc = ", ".join(b.get("facetValueName", "") for b in d.get("breadcrumbs", [])[:2])
            if yeni:
                yeni_ekleyen.append((grup, kat_id, total, len(yeni), bc))
            else:
                dupe.append((grup, kat_id, total, bc))
            time.sleep(0.3)

    print(f"\nToplam kategori: {len(yeni_ekleyen) + len(dupe)}")
    print(f"YENI ürün ekleyen: {len(yeni_ekleyen)}")
    for g, k, t, n, bc in yeni_ekleyen:
        print(f"   {g:9s} {k:8s} total={t:6d} page1'de yeni: {n:3d}  {bc}")
    print(f"\nSaf tekrar (page 1'de sıfır yeni): {len(dupe)}")
    for g, k, t, bc in dupe[:15]:
        print(f"   {g:9s} {k:8s} total={t:6d}  {bc}")
    if len(dupe) > 15:
        print(f"   ... ve {len(dupe) - 15} kategori daha")


if __name__ == "__main__":
    main()
