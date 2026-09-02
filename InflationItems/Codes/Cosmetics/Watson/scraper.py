import csv
import os
import re
import sys
import time
import random
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import traceback

from curl_cffi import requests

# ==================== YOL (PATH) AYARLARI ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
ITEMS_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
OUTPUT_DIR = os.path.join(ITEMS_ROOT, "Datas", "Cosmetics", "Watson")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================== CONFIGURATION ====================
SITEMAP_FILE = os.path.join(SCRIPT_DIR, "sitemap.xml")
API_URL = "https://api.watsons.com.tr/api/v2/wtctr-spa/search"
BASE_DOMAIN = "https://www.watsons.com.tr"

TARGET_CATEGORIES = [str(i) for i in range(100, 111)]

LANG = "tr_TR"
CURRENCY = "TRY"
# API'nin desteklediği en büyük pageSize -> istek sayısını ~yarıya indirir.
PAGE_SIZE = 60

# --- Hız / anti-bot profili ---
# Ölçüm: Akamai, tek IP'den API endpoint'ine PARALEL bağlantıları (eş zamanlı
# in-flight istekleri) bayraklıyor. Sıralı ~1 istek/sn ise 120+ istekte bile
# 0 adet 403 alındı. Bu yüzden istekler SIRALI ve ritmik gönderilir:
#   * Paralel 12 thread + küçük jitter  -> ~280 istekte 403 yağmuru
#   * Sıralı ~0.85 istek/sn             -> 120/120 başarılı
# Hız buradan gelir: pageSize=60 ile tam veri ~170 sayfa -> ~3 dk, eski kodun
# (50 sayfa cap + 8-18 sn bekleme = ~40-60 dk) aksine eksiksiz ve hızlı.
BASE_INTERVAL = 0.55   # istek başlatma arası sn (~1 istek/sn)
MIN_INTERVAL = 0.35
MAX_INTERVAL = 6.0
PAUSE_ON_BLOCK = 30.0  # 403/429 görülürse filoyu bu kadar saniye durdur
MAX_RETRIES = 4
BACKOFF_BASE = 2.0
BACKOFF_MAX = 12.0
REQUEST_TIMEOUT = 30

# Güvenlik sigortası (kategori başına en fazla bu sayfa):
MAX_PAGES_PER_CATEGORY = 500

import threading
print_lock = threading.Lock()

# --- Tek session (sıralı) + uyarlanabilir ritim ---
_next_start = 0.0
_interval = BASE_INTERVAL
_pause_until = 0.0
_rate_lock = threading.Lock()


def _wait_my_turn() -> None:
    global _next_start, _interval, _pause_until
    while True:
        with _rate_lock:
            now = time.time()
            if now < _pause_until:
                wait = _pause_until - now
                _next_start = now + _interval
            else:
                wait = max(0.0, _next_start - now)
        if wait > 0:
            time.sleep(wait)
            continue
        with _rate_lock:
            _next_start = max(_next_start, now) + _interval
        return


def _note_result(ok: bool, blocked: bool = False) -> None:
    global _interval, _pause_until
    with _rate_lock:
        if blocked:
            _pause_until = time.time() + PAUSE_ON_BLOCK
            _interval = min(MAX_INTERVAL, _interval * 3.0)
        elif not ok:
            _interval = min(MAX_INTERVAL, _interval * 1.5)


def tprint(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)


def create_session() -> requests.Session:
    session = requests.Session(impersonate="chrome124")
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": BASE_DOMAIN,
        "Origin": BASE_DOMAIN,
    })
    return session


def clean_name(name: Any) -> str:
    if name is None:
        return ""
    text = str(name).replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_price_to_float(raw_price: Any) -> Optional[float]:
    if raw_price is None or raw_price == "":
        return None
    if isinstance(raw_price, (int, float)):
        return float(raw_price)

    price = str(raw_price).strip().replace("\xa0", " ")
    price = re.sub(r"(?i)\bTRY\b|\bTL\b|₺", "", price)
    price = re.sub(r"[^0-9,.\-]", "", price)

    if not price:
        return None

    if "," in price and "." in price:
        price = price.replace(".", "").replace(",", ".")
    elif "," in price:
        price = price.replace(",", ".")
    else:
        parts = price.split(".")
        if len(parts) > 2:
            price = "".join(parts[:-1]) + "." + parts[-1]

    try:
        return float(price)
    except ValueError:
        return None


def parse_sitemap(sitemap_path: str, category_filter: Optional[List[str]] = None) -> List[str]:
    category_codes = set()
    url_pattern = re.compile(r'/c/(\d+(?:_\d+)?)|/b/(\d+)')

    try:
        with open(sitemap_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()

        xml_content = re.sub(r'\s+xmlns[^=]*="[^"]*"', '', xml_content)
        xml_content = re.sub(r'<([^>]+):', '<', xml_content)
        xml_content = re.sub(r'</([^>]+):', '</', xml_content)

        root = ET.fromstring(xml_content)
        url_elements = root.findall('.//url')

        print(f"[INFO] Found {len(url_elements)} URL elements in sitemap.")

        for url_elem in url_elements:
            loc_elem = url_elem.find('loc')
            if loc_elem is not None and loc_elem.text:
                url = loc_elem.text
                match = url_pattern.search(url)
                if match:
                    code = match.group(1) or match.group(2)
                    if code:
                        if category_filter is None or code in category_filter:
                            category_codes.add(code)

        print(f"[INFO] Found {len(category_codes)} matching category codes.")
        return sorted(list(category_codes))

    except FileNotFoundError:
        print(f"[ERROR] Sitemap file '{sitemap_path}' not found.")
        return []
    except ET.ParseError as e:
        print(f"[ERROR] Failed to parse sitemap XML: {e}")
        return []


def fetch_api_page(session: requests.Session, category_code: str, page: int) -> Optional[Dict[str, Any]]:
    params = {
        "fields": "FULL",
        "searchType": "PRODUCT",
        "categoryCode": category_code,
        "lang": LANG,
        "curr": CURRENCY,
        "currentPage": page,
        "pageSize": PAGE_SIZE,
    }

    backoff = BACKOFF_BASE
    for attempt in range(MAX_RETRIES):
        _wait_my_turn()

        try:
            response = session.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)

            if response.status_code in (429, 403):
                _note_result(ok=False, blocked=True)
                tprint(f"[WARN] {response.status_code} on category {category_code} page {page} "
                       f"(attempt {attempt + 1}). Backing off {min(backoff, BACKOFF_MAX):.1f}s.")
                time.sleep(min(backoff, BACKOFF_MAX))
                backoff *= 2
                continue

            if response.status_code >= 500:
                _note_result(ok=False)
                tprint(f"[WARN] HTTP {response.status_code} on category {category_code} page {page}. Retrying...")
                time.sleep(min(backoff, BACKOFF_MAX))
                backoff *= 2
                continue

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            _note_result(ok=False)
            tprint(f"[WARN] Timeout on category {category_code} page {page}. Retrying...")
            time.sleep(min(backoff, BACKOFF_MAX))
            backoff *= 2
        except Exception as e:
            _note_result(ok=False)
            tprint(f"[WARN] Error on category {category_code} page {page}: {e}")
            time.sleep(min(backoff, BACKOFF_MAX))
            backoff *= 2

    tprint(f"[ERROR] Exhausted retries for category {category_code} page {page}.")
    return None


def extract_products(data: Dict[str, Any], seen_codes: Set[str]) -> List[Tuple[str, float]]:
    rows = []
    products = data.get("products", [])

    for product in products:
        try:
            code = product.get("code") or product.get("defaultSku") or product.get(
                "url") or f"unknown-{len(seen_codes)}"

            if code in seen_codes:
                continue
            seen_codes.add(code)

            name = clean_name(product.get("name"))
            price_value = None
            price_obj = product.get("price", {})

            if isinstance(price_obj, dict):
                price_value = clean_price_to_float(price_obj.get("value"))
                if price_value is None:
                    price_value = clean_price_to_float(price_obj.get("formattedValue"))

            if price_value is None:
                other_prices = product.get("otherPrices", [])
                if other_prices and isinstance(other_prices[0], dict):
                    price_value = clean_price_to_float(other_prices[0].get("value"))
                    if price_value is None:
                        price_value = clean_price_to_float(other_prices[0].get("formattedValue"))

            if not name or price_value is None:
                continue

            rows.append((name, float(price_value)))

        except Exception:
            continue

    return rows


def remove_duplicate_rows(rows: List[Tuple[str, float]]) -> Tuple[List[Tuple[str, float]], int]:
    seen = set()
    unique_rows = []
    duplicates_removed = 0

    for name, price in rows:
        key = (name, price)
        if key not in seen:
            seen.add(key)
            unique_rows.append((name, price))
        else:
            duplicates_removed += 1

    return unique_rows, duplicates_removed


def generate_output_filename() -> str:
    today = datetime.now()
    date_str = today.strftime("%d-%m-%Y")
    return os.path.join(OUTPUT_DIR, f"watsons_{date_str}.csv")


def write_csv(rows: List[Tuple[str, float]], output_file: str) -> None:
    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["product-name", "product-price"])
        for name, price in rows:
            writer.writerow([name, f"{price:.2f}"])


def main() -> None:
    all_rows: List[Tuple[str, float]] = []
    seen_codes: Set[str] = set()
    coverage: Dict[str, List[int]] = {}  # category -> [ok, failed]

    try:
        start_time = time.time()

        print(f"[INFO] Parsing sitemap: {SITEMAP_FILE}")
        category_codes = parse_sitemap(SITEMAP_FILE, category_filter=TARGET_CATEGORIES)

        if not category_codes:
            print("[ERROR] No category codes found. Exiting.")
            return

        print(f"[INFO] Total categories: {len(category_codes)}")
        print(f"[INFO] Probing categories (pageSize={PAGE_SIZE})...")
        print("=" * 60)

        session = create_session()

        # Kategori başına sayfa planını kur (page 0 = pagination öğrenme).
        tasks: List[Tuple[str, int]] = []
        for idx, cat_code in enumerate(category_codes, 1):
            tprint(f"Probing Category {idx}/{len(category_codes)}: Code={cat_code}")
            data = fetch_api_page(session, cat_code, 0)
            if data is None:
                tprint(f"[WARN] Category {cat_code} page 0 failed; skipping category.")
                continue

            total_pages = int(data.get("pagination", {}).get("totalPages", 1))
            total_results = data.get("pagination", {}).get("totalResults", "?")
            pages = min(total_pages, MAX_PAGES_PER_CATEGORY)
            tprint(f"[Cat {cat_code}] totalResults={total_results} -> {pages} pages")

            # page 0 satırlarını da topla
            rows = extract_products(data, seen_codes)
            all_rows.extend(rows)
            coverage[cat_code] = [1, 0]

            for page in range(1, pages):
                tasks.append((cat_code, page))

        if not tasks:
            print("[ERROR] No pages to fetch. Exiting.")
            return

        print(f"[INFO] Fetching {len(tasks)} more pages serially at ~{1/BASE_INTERVAL:.0f} req/s "
              f"(Akamai parallel-connection guard) ...")
        print("=" * 60)

        total = len(tasks)
        for i, (cat_code, page) in enumerate(tasks, 1):
            if i % 25 == 0 or i == total:
                tprint(f"[Progress] {i}/{total} pages")

            data = fetch_api_page(session, cat_code, page)
            if data is None:
                coverage[cat_code][1] += 1
                continue

            rows = extract_products(data, seen_codes)
            all_rows.extend(rows)
            with print_lock:
                coverage[cat_code][0] += 1

        print("\n" + "=" * 60)
        print("PAGE FETCH REPORT")
        print("=" * 60)
        for cat in category_codes:
            if cat in coverage:
                ok, fail = coverage[cat]
                print(f"  Cat {cat}: {ok} pages OK, {fail} failed ({'COMPLETE' if fail == 0 else 'MISSING PAGES'})")
        print("=" * 60)

        print("[INFO] POST-PROCESSING: Removing duplicates...")
        total_before = len(all_rows)
        all_rows, duplicates_removed = remove_duplicate_rows(all_rows)

        output_file = generate_output_filename()
        if Path(output_file).exists():
            timestamp = datetime.now().strftime("%H%M%S")
            output_file = os.path.join(OUTPUT_DIR,
                                       f"watsons_ideal_prices_{datetime.now().strftime('%Y-%m-%d')}_{timestamp}.csv")

        print(f"\n[INFO] Writing {len(all_rows)} products to {output_file}...")
        write_csv(all_rows, output_file)

        elapsed = time.time() - start_time
        minutes, seconds = divmod(elapsed, 60)

        categories_ok = len([c for c in coverage if coverage[c][1] == 0])

        print("\n" + "=" * 60)
        print("SCRAPING COMPLETE")
        print("=" * 60)
        print(f"Raw rows extracted             : {total_before}")
        print(f"Duplicates removed             : {duplicates_removed}")
        print(f"Total products (unique)        : {len(all_rows)}")
        print(f"Categories fully scraped       : {categories_ok}/{len(category_codes)}")
        print(f"Time elapsed                   : {int(minutes)}m {int(seconds)}s")
        print(f"Output file                    : {output_file}")
        print("=" * 60)

    except KeyboardInterrupt:
        if all_rows:
            all_rows, _ = remove_duplicate_rows(all_rows)
            write_csv(all_rows, generate_output_filename())

    except Exception as e:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
