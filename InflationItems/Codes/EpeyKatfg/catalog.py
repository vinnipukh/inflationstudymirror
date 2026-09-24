"""catalog.py — epey product catalog from official sitemaps.

Pulls sitemap/urun_*.xml (robots-declared) -> catalog.csv (category, slug, url).
Run: python catalog.py [--refresh]
"""
import glob, os, re, sys, csv, time

import httpx

HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
BASE = "https://www.epey.com/sitemap"
CATALOG_CSV = "catalog.csv"
SITEMAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Datas", "EpeyKatfg")
SITEMAP_DIR = os.path.abspath(SITEMAP_DIR)


def shard_names():
    return [f"urun_{i}.xml" for i in range(1, 23)]


def download_shards(force=False):
    os.makedirs(SITEMAP_DIR, exist_ok=True)
    for name in shard_names():
        path = os.path.join(SITEMAP_DIR, name)
        if not force and os.path.exists(path) and os.path.getsize(path) > 100_000:
            continue
        for attempt in range(3):
            try:
                r = httpx.get(f"{BASE}/{name}", headers=HDRS, timeout=60, follow_redirects=True)
                if r.status_code == 200 and len(r.text) > 10_000:
                    open(path, "w", encoding="utf-8").write(r.text)
                    break
            except Exception:
                pass
            time.sleep(1 + attempt * 2)


def build_catalog():
    rows = []
    for path in sorted(glob.glob(os.path.join(SITEMAP_DIR, "urun_*.xml"))):
        txt = open(path, encoding="utf-8", errors="ignore").read()
        for u in re.findall(r"<loc>([^<]+)</loc>", txt):
            m = re.match(r"https://www\.epey\.com/([^/]+)/([^/]+\.html)$", u)
            if m:
                rows.append((m.group(1), m.group(2), u))
    with open(os.path.join(SITEMAP_DIR, CATALOG_CSV), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "slug", "url"])
        w.writerows(rows)
    print(f"catalog: {len(rows)} product pages -> {CATALOG_CSV}")


if __name__ == "__main__":
    os.chdir(SITEMAP_DIR)
    if "--refresh" in sys.argv:
        download_shards(force=True)
    else:
        download_shards()
    build_catalog()
