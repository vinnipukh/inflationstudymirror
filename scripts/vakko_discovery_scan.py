"""Discovery scan for the Vakko category tree (strategy C experiment).

Replays ALL categories from the merged list (local XML + live sitemap) in
parents-first topological order, with FULL pagination, and records:

- per-category NEW-product counts (=> the survivor list = minimal dominating set)
- whether union(survivors) == union(all categories)  (completeness proof)
- page counts => runtime projection at the scraper's default pacing
- price conflicts: same Stok Kodu seen with a different price in another category
- diff against the latest CSV (expect only intra-day churn)

Writes the survivor list to Codes/ClothingStores/Vakko/vakko_survivor_categories.json

Run:  python scripts/vakko_discovery_scan.py
"""
import json
import re
import time
from collections import defaultdict, deque
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
VAKKO_DIR = ROOT / "Codes" / "ClothingStores" / "Vakko"
XML_PATH = VAKKO_DIR / "vakko_categories.xml"
CSV_PATH = ROOT / "InflationItems" / "Datas" / "ClothingStores" / "Vakko" / "vakko_2026-08-18.csv"
API_URL = "https://api.vakko.com/occ/v2/vsite/products/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Platform": "WEB",
    "Origin": "https://www.vakko.com",
    "Referer": "https://www.vakko.com/",
}
PAGE_BEKLEME = 0.25  # fast test pacing


def parse_xml(xml_metni):
    """(grup, kat_id, url) — same filter logic as the scraper."""
    cikti = []
    for link in re.findall(r"<loc>(.*?)</loc>", xml_metni):
        link = link.strip()
        m = re.search(r"-c-([a-zA-Z0-9_-]+)/?$", link)
        if not m:
            continue
        kat_id = m.group(1)
        if "/kadin" in link and "/outlet" not in link:
            grup = "Kadin"
        elif "/erkek" in link and "/outlet" not in link:
            grup = "Erkek"
        elif ("/ayakkabi-canta" in link or "/shoes-bags" in link) and "/outlet" not in link:
            grup = "Shoes_Bags"
        else:
            continue
        if (grup, kat_id) not in {(g, k) for g, k, _ in cikti}:
            cikti.append((grup, kat_id, link))
    return cikti


def parent_id(url):
    """Ebeveyn = -c- ID'si olan en yakın önceki URL segmenti (yoksa None = kök)."""
    segments = url.split("/")
    for seg in reversed(segments[:-1]):
        m = re.search(r"-c-([a-zA-Z0-9_-]+)/?$", seg)
        if m:
            return m.group(1)
    return None


def topological_sort(entries):
    """Ebeveynler önce gelecek şekilde sırala (URL ağacından)."""
    ids = [e[1] for e in entries]
    id_set = set(ids)
    parent_of = {e[1]: (parent_id(e[2]) if parent_id(e[2]) in id_set else None) for e in entries}
    children = defaultdict(list)
    for e in entries:
        p = parent_of[e[1]]
        if p:
            children[p].append(e[1])
    indeg = {i: 0 for i in ids}
    for p, kids in children.items():
        for k in kids:
            indeg[k] += 1
    q = deque(sorted(i for i in ids if indeg[i] == 0))
    sirali = []
    while q:
        i = q.popleft()
        sirali.append(i)
        for k in sorted(children[i]):
            indeg[k] -= 1
            if indeg[k] == 0:
                q.append(k)
    if len(sirali) != len(ids):  # döngü olursa: uzunluk sıralı yedek
        sirali = sorted(ids, key=lambda x: (len(x), x))
    return sirali


def main():
    # --- merged category list (same as the scraper) ---
    yerel = parse_xml(XML_PATH.read_text(encoding="utf-8"))
    idx = requests.get("https://www.vakko.com/sitemap.xml", headers=HEADERS, timeout=30)
    cat_urls = [u.strip() for u in re.findall(r"<loc>(.*?)</loc>", idx.text)
                if u.strip().endswith("/sitemap/Category.xml")]
    tr = [u for u in cat_urls if not re.search(r"/(en|el-gr|en-gr|en-eu)/", u)]
    canli = parse_xml(requests.get((tr or cat_urls)[0], headers=HEADERS, timeout=30).text)

    eski_ids = {(g, k) for g, k, _ in yerel}
    birlestik = list(yerel) + [(g, k, u) for g, k, u in canli if (g, k) not in eski_ids]
    print(f"Toplam kategori: {len(birlestik)}")

    sirali = topological_sort(birlestik)
    url_of = {(g, k): u for g, k, u in birlestik}
    grup_of = {(g, k): g for g, k, _ in birlestik}

    session = requests.Session()
    session.headers.update(HEADERS)

    gorulen: dict[str, str] = {}          # code -> ilk görülen fiyat
    yeni_sayisi = {}                      # (grup,id) -> yeni ürün sayısı
    sayfa_sayisi = {}                     # (grup,id) -> çekilen sayfa sayısı
    toplam_sayisi = {}                    # (grup,id) -> API totalResults
    fiyat_cakismalari = []                # aynı kod, farklı fiyat
    baslangic = time.time()
    toplam_ham = 0

    for kat_id in sirali:
        anahtar = next(k for k in url_of if k[1] == kat_id)
        grup = grup_of[anahtar]
        params = {
            "fields": "FULL,facets,breadcrumbs,pagination(DEFAULT),sorts(DEFAULT)",
            "query": f":relevance:allCategories:{kat_id}",
            "pageSize": "48", "lang": "tr", "curr": "TRY", "currentPage": "0",
        }
        sayfa = 0
        toplam_sayfa = 1
        sayfalar = 0
        toplam = 0
        yeni = 0
        while sayfa < toplam_sayfa:
            params["currentPage"] = str(sayfa)
            try:
                r = session.get(API_URL, params=params, timeout=30)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(5)
                    r = session.get(API_URL, params=params, timeout=30)
                if r.status_code != 200:
                    break
            except requests.RequestException:
                break
            d = r.json()
            toplam_sayfa = d.get("pagination", {}).get("totalPages", 1)
            toplam = d.get("pagination", {}).get("totalResults", 0)
            for p in d.get("products", []):
                kod = p.get("code")
                fiyat = (p.get("price") or {}).get("formattedValue") or "Fiyat Yok"
                toplam_ham += 1
                if kod not in gorulen:
                    gorulen[kod] = fiyat
                    yeni += 1
                elif gorulen[kod] != fiyat:
                    fiyat_cakismalari.append((kod, kat_id, gorulen[kod], fiyat))
            sayfa += 1
            sayfalar += 1
            if sayfa < toplam_sayfa:
                time.sleep(PAGE_BEKLEME)
        yeni_sayisi[kat_id] = yeni
        sayfa_sayisi[kat_id] = sayfalar
        toplam_sayisi[kat_id] = toplam

    gecen = time.time() - baslangic

    # --- sonuçlar ---
    survivor = [k for k in sirali if yeni_sayisi[k] > 0]
    sayfa_toplam = sum(sayfa_sayisi.values())
    sayfa_survivor = sum(sayfa_sayisi[k] for k in survivor)

    print(f"\n{'='*70}")
    print(f"Süre (test hızı, {PAGE_BEKLEME}s/sayfa): {gecen:.0f}s")
    print(f"Toplam benzersiz ürün (tüm kategoriler): {len(gorulen)}")
    print(f"Ham ürün (sayfa tekrarlarıyla): {toplam_ham}")
    print(f"Çekilen sayfa: {sayfa_toplam} | Survivor set sayfa: {sayfa_survivor}")
    print(f"\nSURVIVOR KATEGORİLER ({len(survivor)}):")
    for k in survivor:
        print(f"   {grup_of[next(x for x in url_of if x[1]==k)]:9s} {k:8s} "
              f"toplam={toplam_sayisi[k]:6d} yeni={yeni_sayisi[k]:6d} sayfa={sayfa_sayisi[k]:3d}")

    # projeksiyon: varsayılan hız (3.2-4.8s sayfa + 3.7-5.5s kategori)
    ortalama_sayfa = (3.2 + 4.8) / 2 + 0.8  # +istek süresi
    ortalama_kat = (3.7 + 5.5) / 2 + 0.8
    tam_sure = sayfa_toplam * ortalama_sayfa + len(sirali) * ortalama_kat
    sur_sure = sayfa_survivor * ortalama_sayfa + len(survivor) * ortalama_kat
    print(f"\nVarsayılan hızda projeksiyon:")
    print(f"   Tümü tara:    {tam_sure/60:.0f} dk  ({sayfa_toplam} sayfa, {len(sirali)} kategori)")
    print(f"   Survivor:     {sur_sure/60:.0f} dk  ({sayfa_survivor} sayfa, {len(survivor)} kategori)")

    # --- CSV ile karşılaştırma ---
    import pandas as pd
    csv_df = pd.read_csv(CSV_PATH)
    csv_codes = set(csv_df["Stok Kodu"].astype(str))
    eksik = csv_codes - set(gorulen)
    fazla = set(gorulen) - csv_codes
    print(f"\nCSV ile karşılaştırma (CSV {len(csv_codes)} ürün):")
    print(f"   CSV'de olup taramada yok: {len(eksik)} | taramada olup CSV'de yok: {len(fazla)}")

    print(f"\nFiyat çakışması (aynı kod, farklı kategori fiyatı): {len(fiyat_cakismalari)}")
    for kod, kat, f1, f2 in fiyat_cakismalari[:10]:
        print(f"   {kod}: {f1} vs {f2} (kategori {kat})")

    # --- survivor listesini kaydet ---
    cikti = {
        "tarih": time.strftime("%Y-%m-%d"),
        "survivor_kategoriler": [
            {"grup": grup_of[next(x for x in url_of if x[1] == k)],
             "id": k, "url": url_of[next(x for x in url_of if x[1] == k)]}
            for k in survivor
        ],
        "istatistik": {
            "toplam_benzersiz": len(gorulen),
            "sayfa_tumu": sayfa_toplam,
            "sayfa_survivor": sayfa_survivor,
            "test_suresi_sn": round(gecen),
        },
    }
    hedef = VAKKO_DIR / "vakko_survivor_categories.json"
    hedef.write_text(json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSurvivor listesi kaydedildi: {hedef}")


if __name__ == "__main__":
    main()
