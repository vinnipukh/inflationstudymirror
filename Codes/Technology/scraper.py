import csv
import os
import random
import sys
import time
from datetime import datetime

import requests
from seleniumbase import SB

# ==================== PATH SETUP ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Script is in Codes/Technology. Go up 2 levels to reach inflationstudymirror.
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Datas", "Technology")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_stealth_cookies(target_url):
    print(f"Fetch cookies: {target_url}")
    with SB(uc=True, headless=True) as sb:
        sb.uc_open_with_reconnect(target_url, reconnect_time=5)
        sb.sleep(8)
        sb.execute_script("window.scrollBy(0, 300)")
        sb.sleep(2)

        raw_cookies = sb.get_cookies()
        print("Cookies good.")
        return {c['name']: c['value'] for c in raw_cookies}


def scrape_beymen():
    base_api_url = "https://www.beymen.com/api/product/list"
    target_web_url = "https://www.beymen.com/tr/teknoloji-95935"

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = os.path.join(OUTPUT_DIR, f"beymen_tech_{date_str}.csv")

    print(f"Save location: {filename}")

    try:
        cookies = get_stealth_cookies(target_web_url)
    except Exception as e:
        print(f"Cookie fail: {e}")
        sys.exit(1)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    # Context manager handles saving and closing automatically on break
    with open(filename, mode="w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["product-name", "product-price"])

        with requests.Session() as session:
            session.headers.update(headers)
            session.cookies.update(cookies)

            for page in range(1, 201):
                params = {
                    "languageCode": "tr",
                    "sayfa": page,
                    "categoryId": "95935",
                    "includeDocuments": "true"
                }

                try:
                    response = session.get(base_api_url, params=params, timeout=15)

                    if response.status_code == 403:
                        print(f"403 fail at page {page}. Cookies dead. Save data and stop.")
                        break

                    response.raise_for_status()
                    json_data = response.json()

                    inner_data = json_data.get("data", {})
                    products = inner_data.get("productList") or inner_data.get("products") or []

                    if not products:
                        print(f"No products page {page}. Done. File saves automatically.")
                        break

                    for item in products:
                        name = item.get("displayName", "")
                        price = item.get("actualPrice")

                        if price is not None:
                            try:
                                price_str = f"{float(price):.2f}"
                            except ValueError:
                                price_str = ""
                        else:
                            price_str = ""

                        writer.writerow([name, price_str])

                    file.flush()
                    print(f"Page {page} saved. {len(products)} items. File updated.")
                    time.sleep(random.uniform(1.5, 3.5))

                except Exception as e:
                    print(f"Loop fail (Page {page}): {e}. Save data and stop.")
                    break

    print(f"Scrape complete. File ready: {filename}")


if __name__ == "__main__":
    scrape_beymen()