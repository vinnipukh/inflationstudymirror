import csv
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import traceback
import random

from curl_cffi import requests

# ==================== YOL (PATH) AYARLARI ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Datas", "Cosmetics", "Watson")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================== CONFIGURATION ====================
SITEMAP_FILE = os.path.join(SCRIPT_DIR, "sitemap.xml")
API_URL = "https://api.watsons.com.tr/api/v2/wtctr-spa/search"
BASE_DOMAIN = "https://www.watsons.com.tr"

TARGET_CATEGORIES = [str(i) for i in range(100, 111)]

LANG = "tr_TR"
CURRENCY = "TRY"
PAGE_SIZE = 28
MAX_PAGES_PER_CATEGORY = 50
MAX_WORKERS = 1
MAX_RETRIES = 5
BACKOFF_BASE = 2.0
BACKOFF_MAX = 30.0
MIN_DELAY = 8.0
MAX_DELAT = 18.0

progress_lock = threading.Lock()
print_lock = threading.Lock()


def tprint(*args, **kwargs):
    thread_name = threading.current_thread().name
    with print_lock:
        print(f"[{thread_name}]", *args, **kwargs)


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


def create_session() -> requests.Session:
    session = requests.Session(impersonate="chrome124")
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": BASE_DOMAIN,
        "Origin": BASE_DOMAIN,
    })
    return session


def fetch_api_page(session: requests.Session, category_code: str, page: int) -> Optional[Dict[str, Any]]:
    backoff = BACKOFF_BASE
    attempts = 0

    while attempts < MAX_RETRIES:
        try:
            params = {
                "fields": "FULL",
                "searchType": "PRODUCT",
                "categoryCode": category_code,
                "lang": LANG,
                "curr": CURRENCY,
                "currentPage": page,
                "pageSize": PAGE_SIZE,
            }

            response = session.get(API_URL, params=params, timeout=30)

            if response.status_code == 429:
                tprint(f"[WARN] 429 Rate Limited on category {category_code} page {page}. Sleeping {backoff:.1f}s.")
                time.sleep(min(backoff, BACKOFF_MAX))
                backoff *= 2
                attempts += 1
                continue

            if response.status_code == 403:
                tprint(f"[WARN] 403 Forbidden on category {category_code} page {page}. Retrying in {backoff:.1f}s.")
                time.sleep(min(backoff, BACKOFF_MAX))
                backoff *= 2
                attempts += 1
                continue

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            tprint(f"[WARN] Timeout on category {category_code} page {page}. Retrying...")
            attempts += 1
            time.sleep(1.0)

        except Exception as e:
            tprint(f"[WARN] Error on category {category_code} page {page}: {e}")
            attempts += 1
            time.sleep(2.0)

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

            seen_codes.add(code)
            rows.append((name, float(price_value)))

        except Exception:
            continue

    return rows


def scrape_category(category_code: str, seen_codes: Set[str], category_num: int, total_categories: int) -> Tuple[
    List[Tuple[str, float]], str, bool]:
    tprint(f"Starting Category {category_num}/{total_categories}: Code={category_code}")

    session = create_session()
    category_rows = []
    failed = False

    for page in range(0, MAX_PAGES_PER_CATEGORY):
        # Human delay before every page fetch (skip first page)
        if page > 0:
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            tprint(f"Sleeping {delay:.2f}s to mimic human...")
            time.sleep(delay)

        data = fetch_api_page(session, category_code, page)

        if data is None:
            tprint(f"[WARN] Failed category {category_code} page {page}. Stopping category.")
            failed = True
            break

        with progress_lock:
            page_rows = extract_products(data, seen_codes)

        category_rows.extend(page_rows)

        pagination = data.get("pagination", {})
        total_pages = int(pagination.get("totalPages", 1))

        tprint(f"[Cat {category_code}] Page {page + 1}/{total_pages}: +{len(page_rows)} products")

        if page >= total_pages - 1:
            break

    tprint(f"Category {category_code} done: {len(category_rows)} products")

    # Extra delay between categories
    cat_delay = random.uniform(15.0, 25.0)
    tprint(f"Category finished. Sleeping {cat_delay:.2f}s before next category...")
    time.sleep(cat_delay)

    return category_rows, category_code, failed


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
    all_rows = []
    seen_codes = set()
    failed_categories = []

    try:
        start_time = time.time()

        print(f"[INFO] Parsing sitemap: {SITEMAP_FILE}")
        category_codes = parse_sitemap(SITEMAP_FILE, category_filter=TARGET_CATEGORIES)

        if not category_codes:
            print("[ERROR] No category codes found. Exiting.")
            return

        print(f"[INFO] Total categories: {len(category_codes)}")
        print(f"[INFO] Starting parallel scraping with {MAX_WORKERS} workers using curl_cffi...")
        print("=" * 60)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="Scraper") as executor:
            future_to_category = {
                executor.submit(scrape_category, cat_code, seen_codes, idx, len(category_codes)): cat_code
                for idx, cat_code in enumerate(category_codes, 1)
            }

            for future in as_completed(future_to_category):
                category_code = future_to_category[future]
                try:
                    category_rows, cat_code, failed = future.result()
                    with progress_lock:
                        all_rows.extend(category_rows)
                        if failed:
                            failed_categories.append(cat_code)
                except Exception as e:
                    print(f"[ERROR] Category {category_code} raised exception: {e}")
                    traceback.print_exc()
                    failed_categories.append(category_code)

        print("\n" + "=" * 60)
        print("[INFO] POST-PROCESSING: Removing duplicates...")
        print("=" * 60)

        total_before = len(all_rows)
        all_rows, duplicates_removed = remove_duplicate_rows(all_rows)
        total_after = len(all_rows)

        output_file = generate_output_filename()
        if Path(output_file).exists():
            timestamp = datetime.now().strftime("%H%M%S")
            output_file = os.path.join(OUTPUT_DIR,
                                       f"watsons_ideal_prices_{datetime.now().strftime('%Y-%m-%d')}_{timestamp}.csv")

        print(f"\n[INFO] Writing {len(all_rows)} products to {output_file}...")
        write_csv(all_rows, output_file)

        elapsed = time.time() - start_time
        minutes, seconds = divmod(elapsed, 60)

        print("\n" + "=" * 60)
        print("SCRAPING COMPLETE")
        print("=" * 60)
        print(f"Total products (unique)    : {len(all_rows)}")
        print(f"Categories processed       : {len(category_codes) - len(failed_categories)}/{len(category_codes)}")
        print(f"Time elapsed               : {int(minutes)}m {int(seconds)}s")
        print(f"Output file                : {output_file}")
        print("=" * 60)

    except KeyboardInterrupt:
        if all_rows:
            all_rows, dupes = remove_duplicate_rows(all_rows)
            out = generate_output_filename()
            write_csv(all_rows, out)

    except Exception as e:
        traceback.print_exc()
        if all_rows:
            all_rows, dupes = remove_duplicate_rows(all_rows)
            out = generate_output_filename()
            write_csv(all_rows, out)


if __name__ == "__main__":
    main()