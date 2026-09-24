"""pull.py — probe + katfg backfill for a list of epey product URLs.

Per product: GET page -> extract id=...&fiyat=... (+ #fiyatgecmisi check)
             -> POST /kat/fg/ -> daily series rows -> append to series.csv
Politeness: sleep between products; stop on repeated 403/429.

Usage: python pull.py urls.txt series.csv [--sleep 1.2]
"""
import csv, os, re, sys, time

import httpx

HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Referer": "https://www.epey.com/"}
FG_RE = re.compile(r"id=(\d+)&fiyat=([\d.]+)")
HIST_RE = re.compile(r'id="fiyatgecmisi"')


def probe_product(url):
    """GET product page; return (pid, fiyat) if price history exists else None."""
    r = httpx.get(url, headers=HDRS, timeout=30, follow_redirects=True)
    if r.status_code != 200:
        return None, r.status_code
    html = r.text
    if not HIST_RE.search(html):
        return None, "no-history"
    m = FG_RE.search(html)
    if not m:
        m2 = re.search(r'data-id="(\d+)"', html)
        return None, "no-fg-params"
    return (m.group(1), m.group(2)), 200


def pull_history(pid, fiyat):
    """POST katfg; return list of [date, price, range] or None."""
    r = httpx.post("https://www.epey.com/kat/fg/",
                   data={"id": pid, "fiyat": fiyat}, headers=HDRS, timeout=30, follow_redirects=True)
    if r.status_code != 200:
        return None, r.status_code
    try:
        return r.json(), 200
    except Exception:
        return None, "not-json"


def run(urls, out_csv, sleep_s=1.2, max_products=None):
    seen = set()
    if os.path.exists(out_csv):
        with open(out_csv, encoding="utf-8") as f:
            seen = {row[0] for row in csv.reader(f) if row}  # first col = url (or key)
    with open(out_csv, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if os.path.getsize(out_csv) == 0:
            w.writerow(["url", "category", "pid", "date", "price_tl", "range_id"])
        done, errors, skips = 0, 0, 0
        for url in urls:
            if max_products and done >= max_products:
                break
            if url in seen:
                skips += 1
                continue
            pidf, st = probe_product(url)
            if not pidf:
                errors += 1
                if isinstance(st, int) and st in (403, 429):
                    print(f"BLOCKED at {st} on {url}; stopping.")
                    break
                time.sleep(sleep_s)
                continue
            pid, fiyat = pidf
            data, st2 = pull_history(pid, fiyat)
            if not data:
                errors += 1
                if isinstance(st2, int) and st2 in (403, 429):
                    print(f"BLOCKED at {st2} on katfg; stopping.")
                    break
                time.sleep(sleep_s)
                continue
            cat = url.split("/")[3]
            for d, p, rng in data:
                w.writerow([url, cat, pid, d, p, rng])
            done += 1
            if done % 10 == 0:
                print(f"  pulled {done} (urls={len(urls)}, err={errors}, skip={skips})")
            time.sleep(sleep_s)
        f.flush()
    print(f"done: pulled={done} errors={errors} skipped(already have)={skips}")


if __name__ == "__main__":
    urls = [u.strip() for u in open(sys.argv[1]) if u.strip()]
    run(urls, sys.argv[2], sleep_s=float(sys.argv[3]) if len(sys.argv) > 3 else 1.2)
