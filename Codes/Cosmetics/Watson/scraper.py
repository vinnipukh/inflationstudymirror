import csv
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import traceback

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

# ==================== YOL (PATH) AYARLARI ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 3 klasör yukarı çıkarak ana dizine (inflationstudymirror) ulaşıyoruz
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))

# Burayı görselde işaretlediğin Datas/Cosmetics/Watson klasörüne yönlendirdik
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Datas", "Cosmetics", "Watson")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================== CONFIGURATION ====================
SITEMAP_FILE = os.path.join(SCRIPT_DIR, "sitemap.xml")
API_URL = "https://api.watsons.com.tr/api/v2/wtctr-spa/search"
BASE_DOMAIN = "https://www.watsons.com.tr"

# Categories to scrape (100-110)
TARGET_CATEGORIES = [str(i) for i in range(100, 111)]

LANG = "tr_TR"
CURRENCY = "TRY"
PAGE_SIZE = 28
MAX_PAGES_PER_CATEGORY = 50

NUM_BROWSERS = 3
MAX_WORKERS = NUM_BROWSERS

BACKOFF_BASE = 2.0
BACKOFF_MAX = 30.0
MAX_RETRIES = 5

COOKIE_SELECTORS = [
    (By.ID, "onetrust-accept-btn-handler"),
    (By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"),
    (By.XPATH, "//button[contains(., 'Kabul')]"),
    (By.XPATH, "//button[contains(., 'Accept')]"),
    (By.XPATH, "//button[contains(., 'Tümünü Kabul')]"),
]

CHALLENGE_KEYWORDS = [
    "captcha", "turnstile", "perimeterx", "px-captcha",
    "access denied", "verify you are human", "challenge"
]

progress_lock = threading.Lock()
print_lock = threading.Lock()


# ==================== THREAD-SAFE PRINT ====================
def tprint(*args, **kwargs):
    thread_name = threading.current_thread().name
    with print_lock:
        print(f"[{thread_name}]", *args, **kwargs)


# ==================== DATA CLEANING ====================
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


# ==================== SITEMAP PARSING ====================
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


# ==================== SELENIUM BROWSER SETUP ====================
def wait_for_page_ready(driver: webdriver.Chrome, timeout: int = 30) -> None:
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def accept_cookies_if_present(driver: webdriver.Chrome) -> None:
    for by, selector in COOKIE_SELECTORS:
        try:
            elements = driver.find_elements(by, selector)
            if elements:
                elements[0].click()
                time.sleep(1.0)
                print(f"[INFO] Cookie banner accepted.")
                return
        except Exception:
            continue


def page_looks_like_challenge(driver: webdriver.Chrome) -> bool:
    try:
        text = f"{driver.title} {driver.current_url} {driver.page_source[:5000]}".lower()
        return any(keyword in text for keyword in CHALLENGE_KEYWORDS)
    except Exception:
        return False


def create_driver(browser_index: int) -> webdriver.Chrome:
    options = Options()
    # GitHub Actions için headless ve güvenlik ayarları
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    options.add_argument("--lang=tr-TR")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def build_session_from_driver(driver: webdriver.Chrome, browser_index: int) -> requests.Session:
    session = requests.Session()

    try:
        user_agent = driver.execute_script("return navigator.userAgent;")
    except Exception:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": BASE_DOMAIN,
        "Origin": BASE_DOMAIN,
        "Connection": "keep-alive",
    })

    cookie_count = 0
    for cookie in driver.get_cookies():
        try:
            session.cookies.set(
                name=cookie["name"],
                value=cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )
            cookie_count += 1
        except Exception:
            continue

    print(f"[INFO] Browser {browser_index}: Captured {cookie_count} cookies into session.")
    return session


def setup_browser_session(browser_index: int, max_retries: int = 3) -> Optional[
    Tuple[webdriver.Chrome, requests.Session]]:
    # Captcha'ya takılırsa max_retries kadar baştan dener
    for attempt in range(max_retries):
        print(f"\n[INFO] Opening browser {browser_index + 1}/{NUM_BROWSERS} (Deneme {attempt + 1}/{max_retries})...")
        driver = create_driver(browser_index)

        try:
            driver.get(f"{BASE_DOMAIN}/makyaj/c/100")
            wait_for_page_ready(driver, timeout=30)
            time.sleep(2)

            accept_cookies_if_present(driver)

            if page_looks_like_challenge(driver):
                print(f"[WARN] Browser {browser_index + 1} captcha'ya yakalandı. Sürücü yeniden başlatılıyor...")
                driver.quit()
                time.sleep(3)
                continue  # Döngünün başına dönüp tekrar dener

            session = build_session_from_driver(driver, browser_index + 1)
            return driver, session

        except Exception as e:
            print(f"[ERROR] Failed to set up browser {browser_index + 1}: {e}")
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(3)

    print(f"[ERROR] Browser {browser_index + 1} art arda {max_retries} kez captcha'yı aşamadı. Atlanıyor.")
    return None


# ==================== SESSION POOL ====================
class SessionPool:
    def __init__(self, sessions: List[requests.Session]):
        self._sessions = list(sessions)
        self._available = list(sessions)
        self._lock = threading.Condition()
        self._dead_sessions: Set[int] = set()

    def acquire(self) -> Optional[requests.Session]:
        with self._lock:
            while True:
                self._available = [
                    s for s in self._available
                    if id(s) not in self._dead_sessions
                ]
                if self._available:
                    session = self._available.pop(0)
                    return session

                alive = [s for s in self._sessions if id(s) not in self._dead_sessions]
                if not alive:
                    return None

                self._lock.wait(timeout=1.0)

    def release(self, session: requests.Session) -> None:
        with self._lock:
            if id(session) not in self._dead_sessions:
                self._available.append(session)
            self._lock.notify_all()

    def mark_dead(self, session: requests.Session) -> None:
        with self._lock:
            self._dead_sessions.add(id(session))
            self._available = [
                s for s in self._available
                if id(s) not in self._dead_sessions
            ]
            self._lock.notify_all()
        tprint(f"[WARN] Session marked as dead. Remaining alive: {self.alive_count()}")

    def alive_count(self) -> int:
        with self._lock:
            return len([s for s in self._sessions if id(s) not in self._dead_sessions])

    def has_alive_sessions(self) -> bool:
        return self.alive_count() > 0


# ==================== API FETCHING ====================
def fetch_api_page_with_pool(pool: SessionPool, category_code: str, page: int) -> Optional[Dict[str, Any]]:
    backoff = BACKOFF_BASE
    attempts = 0

    while attempts < MAX_RETRIES:
        if not pool.has_alive_sessions():
            tprint(f"[ERROR] No alive sessions left. Cannot fetch category {category_code} page {page}.")
            return None

        session = pool.acquire()
        if session is None:
            tprint(f"[ERROR] Could not acquire session from pool.")
            return None

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
                tprint(
                    f"[WARN] 429 Rate Limited on category {category_code} page {page}. Sleeping {backoff:.1f}s before retry...")
                pool.release(session)
                time.sleep(min(backoff, BACKOFF_MAX))
                backoff *= 2
                attempts += 1
                continue

            if response.status_code == 403:
                tprint(f"[WARN] 403 Forbidden on category {category_code} page {page}. Marking session as dead.")
                pool.mark_dead(session)
                attempts += 1
                backoff = min(backoff * 2, BACKOFF_MAX)
                continue

            response.raise_for_status()

            data = response.json()
            pool.release(session)
            return data

        except requests.exceptions.Timeout:
            tprint(f"[WARN] Timeout on category {category_code} page {page}. Retrying...")
            pool.release(session)
            attempts += 1
            time.sleep(1.0)

        except requests.exceptions.ConnectionError:
            tprint(f"[WARN] Connection error on category {category_code} page {page}. Retrying...")
            pool.release(session)
            attempts += 1
            time.sleep(2.0)

        except Exception as e:
            tprint(f"[WARN] Unexpected error on category {category_code} page {page}: {e}")
            pool.release(session)
            attempts += 1

    tprint(f"[ERROR] Exhausted retries for category {category_code} page {page}.")
    return None


# ==================== PRODUCT EXTRACTION ====================
def extract_products(data: Dict[str, Any], seen_codes: Set[str]) -> List[Tuple[str, float]]:
    rows: List[Tuple[str, float]] = []
    products = data.get("products", [])

    for product in products:
        try:
            code = (
                    product.get("code") or
                    product.get("defaultSku") or
                    product.get("url") or
                    f"unknown-{len(seen_codes)}"
            )

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


# ==================== CATEGORY SCRAPER ====================
def scrape_category(pool: SessionPool, category_code: str, seen_codes: Set[str], category_num: int,
                    total_categories: int) -> Tuple[List[Tuple[str, float]], str, bool]:
    tprint(f"Starting Category {category_num}/{total_categories}: Code={category_code}")

    category_rows = []
    failed = False

    for page in range(0, MAX_PAGES_PER_CATEGORY):
        data = fetch_api_page_with_pool(pool, category_code, page)

        if data is None:
            tprint(f"[WARN] Failed to fetch category {category_code} page {page}. Stopping this category.")
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

        if not pool.has_alive_sessions():
            tprint(f"[ERROR] No sessions left. Stopping category {category_code}.")
            failed = True
            break

    tprint(f"Category {category_code} done: {len(category_rows)} products")
    return category_rows, category_code, failed


# ==================== DUPLICATE REMOVAL ====================
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


# ==================== CSV OUTPUT ====================
def generate_output_filename() -> str:
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    return os.path.join(OUTPUT_DIR, f"watsons_ideal_prices_{date_str}.csv")


def write_csv(rows: List[Tuple[str, float]], output_file: str) -> None:
    # İstenen başlıklar ve ";" ayırıcı
    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["product-name", "product-price"])
        for name, price in rows:
            # Fiyatı noktayla kaydet
            writer.writerow([name, f"{price:.2f}"])


# ==================== MAIN ====================
def main() -> None:
    all_rows: List[Tuple[str, float]] = []
    seen_codes: Set[str] = set()
    failed_categories: List[str] = []
    drivers: List[webdriver.Chrome] = []

    try:
        start_time = time.time()

        print(f"[INFO] Parsing sitemap: {SITEMAP_FILE}")
        print(f"[INFO] Filtering for categories: {', '.join(TARGET_CATEGORIES)}")
        category_codes = parse_sitemap(SITEMAP_FILE, category_filter=TARGET_CATEGORIES)

        if not category_codes:
            print("[ERROR] No category codes found in sitemap. Exiting.")
            return

        print(f"[INFO] Total categories to scrape: {len(category_codes)}")

        print(f"\n[INFO] Opening {NUM_BROWSERS} headless browser(s) to collect cookies...")
        sessions: List[requests.Session] = []

        for i in range(NUM_BROWSERS):
            result = setup_browser_session(i)
            if result is not None:
                driver, session = result
                drivers.append(driver)
                sessions.append(session)
                print(f"[INFO] Browser {i + 1} session ready.")
            else:
                print(f"[WARN] Browser {i + 1} failed to initialize. Skipping.")

        if not sessions:
            print("[ERROR] No browser sessions could be established. Exiting.")
            return

        print(f"\n[INFO] {len(sessions)}/{NUM_BROWSERS} sessions ready.")

        pool = SessionPool(sessions)

        print(f"\n[INFO] Starting parallel scraping with {MAX_WORKERS} workers...")
        print("=" * 60)

        with ThreadPoolExecutor(
                max_workers=MAX_WORKERS,
                thread_name_prefix="Scraper"
        ) as executor:
            future_to_category = {
                executor.submit(
                    scrape_category, pool, cat_code, seen_codes, idx, len(category_codes)
                ): cat_code
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
                    print(f"[ERROR] Category {category_code} raised an exception: {e}")
                    traceback.print_exc()
                    failed_categories.append(category_code)

        print("\n" + "=" * 60)
        print("[INFO] POST-PROCESSING: Removing duplicates...")
        print("=" * 60)

        total_before = len(all_rows)
        all_rows, duplicates_removed = remove_duplicate_rows(all_rows)
        total_after = len(all_rows)

        print(f"[INFO] Products before deduplication : {total_before}")
        print(f"[INFO] Products after deduplication  : {total_after}")
        print(f"[INFO] Duplicates removed            : {duplicates_removed}")

        output_file = generate_output_filename()
        if Path(output_file).exists():
            timestamp = datetime.now().strftime("%H%M%S")
            output_file = os.path.join(OUTPUT_DIR,
                                       f"watsons_ideal_prices_{datetime.now().strftime('%Y-%m-%d')}_{timestamp}.csv")
            print(f"[WARN] File exists. Using: {output_file}")

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

    finally:
        print(f"\n[INFO] Closing {len(drivers)} browser(s)...")
        for i, driver in enumerate(drivers):
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()