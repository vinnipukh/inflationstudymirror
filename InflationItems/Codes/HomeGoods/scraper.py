import requests
from bs4 import BeautifulSoup
import json
import csv
from datetime import datetime
import time
import re
import random
import os
from html import unescape


# ---------------------------------------------------------------------------
# Site-structure helpers
#
# On 2026-08-13 chakra.com.tr (Akinon platform) stripped product names (and
# offers) from the JSON-LD ItemList: entries now carry only @type/position/url.
# The full catalog data (id, item_sku, name, price, brand, category) still
# ships server-side inside the hidden <div class="analytics-data"> as a
# 'productListViewed' analytics payload. Prices kept coming from the
# <pz-price> card fallback below, so only the name source had to change.
# ---------------------------------------------------------------------------


def extract_analytics_product_names(page_html):
    """Parse the hidden analytics-data div's productListViewed payload.

    Returns (names_by_id, entries) where names_by_id maps {product_id: name}
    and entries is a list of (product_id, name) pairs for URL-segment matching
    (variant URLs like /...-8699147026572-1/ truncate to an unusable id).

    The analytics-data div holds concatenated analytics JSON blobs whose raw
    text can contain HTML-ish sequences, so it must be scanned on the RAW
    response text — BeautifulSoup's parser mangles the blob into elements.
    """
    names = {}
    entries = []
    for match in re.finditer(
        r'"type"\s*:\s*"productListViewed".*?"payload"\s*:', page_html, re.S
    ):
        try:
            payload, _ = json.JSONDecoder().raw_decode(page_html[match.end():].lstrip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            for product in payload:
                product_id = product.get('id')
                name = product.get('name')
                if product_id and name:
                    clean_name = unescape(str(name)).strip()
                    names[str(product_id)] = clean_name
                    entries.append((str(product_id), clean_name))
    return names, entries


def find_product_wrapper(soup, product_id):
    """Locate the .product-item card for a product id (data-sku attribute).

    The href fallback only runs for real-length ids: variant URLs
    (/...-<ean>-1/) truncate to collision-prone ids like '1', where an
    anchored href match could hit an unrelated card.
    """
    wrapper = soup.find(attrs={'data-sku': product_id})
    if wrapper is None and len(product_id) >= 6:
        product_link = soup.find(
            'a', href=re.compile(re.escape('/' + product_id + '/') + r'$')
        )
        if product_link:
            wrapper = product_link.find_parent('div', class_=re.compile(r'product-item'))
    return wrapper


def extract_name_from_card(wrapper):
    """Server-rendered product name: the card's image alt attribute."""
    img = wrapper.find('img', alt=True)
    if img:
        alt = (img.get('alt') or '').strip()
        if alt:
            return alt
    return ''


def humanize_slug(product_url):
    """Last-resort name from the URL slug.

    /bled-tekli-koltuk-88x92x69-cm-bej-8682313223325/ ->
    'Bled Tekli Koltuk 88x92x69 Cm Bej'
    """
    match = re.search(r'/([^/]+?)(?:-\d+)?/?$', product_url)
    if not match:
        return ''
    slug = match.group(1)
    return ' '.join(word for word in slug.split('-') if word).title()


def scrape_chakra_category(base_url, category_name):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    page = 1
    category_products = []
    seen_ids = set()
    retry_delays = [5, 15, 30]

    print(f"\n--- {category_name.upper()} Taraması Başlıyor ---")

    while True:
        url = f"{base_url}?page={page}"
        print(f"İstek atılıyor: {url}")

        request_success = False

        for attempt, delay in enumerate(retry_delays):
            try:
                response = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
                response.raise_for_status()
                request_success = True
                break
            except requests.exceptions.RequestException as e:
                print(f"Hata ({e}). {delay} saniye bekleniyor... (Deneme {attempt + 1}/3)")
                time.sleep(delay)

        if not request_success:
            print(f"Uyarı: {url} sayfasına 3 denemede de ulaşılamadı. Sayfa atlanıyor.")
            page += 1
            continue

        if response.history:
            print(f"Yönlendirme tespit edildi. {category_name} kategorisi bitti.")
            break

        soup = BeautifulSoup(response.text, 'html.parser')

        # Product names moved out of the JSON-LD on 2026-08-13; read the
        # analytics payload once per page instead (raw text, not the soup:
        # the parser mangles the analytics JSON blob).
        analytics_names, analytics_entries = extract_analytics_product_names(response.text)

        ld_json_script = soup.find('script', type='application/ld+json')

        if not ld_json_script:
            print("JSON verisi bulunamadı, sayfa yapısı farklı veya sayfalama sonu. Döngü kırılıyor.")
            break

        try:
            data = json.loads(ld_json_script.string)
        except json.JSONDecodeError:
            print("JSON ayrıştırma hatası, döngü kırılıyor.")
            break

        items = data.get('itemListElement', [])
        if not items:
            print("Sayfada ürün bulunamadı, döngü kırılıyor.")
            break

        new_items_found = False

        for item in items:
            product_url = item.get('url', '')
            match = re.search(r'-(\d+)/?$', product_url)
            product_id = match.group(1) if match else product_url

            # Name resolution order: analytics payload (current site) ->
            # JSON-LD name (pre-2026-08-13 structure) -> card image alt ->
            # URL slug -> explicit fallback.
            name = analytics_names.get(product_id, '')
            if not name:
                # Variant URLs (/...-<ean>-1/) truncate the id to something
                # unusable ('1'); match payload entries by URL segment instead,
                # longest id first so a shorter id can't shadow a longer one.
                for payload_id, payload_name in sorted(
                    analytics_entries, key=lambda t: len(t[0]), reverse=True
                ):
                    if re.search(r'-' + re.escape(payload_id) + r'(?:-\d+)?/?$', product_url):
                        name = payload_name
                        break
            if not name:
                name = item.get('name', '').strip()
            wrapper = None
            if not name:
                wrapper = find_product_wrapper(soup, product_id)
                name = extract_name_from_card(wrapper) if wrapper else ''
            if not name:
                name = humanize_slug(product_url)
            if not name:
                name = 'İsimsiz Ürün'

            offers = item.get('offers')
            if isinstance(offers, list) and len(offers) > 0:
                price_val = offers[0].get('price')
            elif isinstance(offers, dict):
                price_val = offers.get('price')
            else:
                price_val = None

            if price_val is None or str(price_val).strip() == "":
                price = '0'
            else:
                price = str(price_val).strip()

            if price == '0' or price == 'None':
                if wrapper is None:
                    wrapper = find_product_wrapper(soup, product_id)

                if wrapper:
                    for pz_price_tag in wrapper.find_all('pz-price'):
                        text = pz_price_tag.get_text(strip=True)
                        if text:
                            raw_price = text.replace(' TL', '').replace(' tl', '').replace('.', '').replace(',', '.')
                            price = raw_price.strip()
                            break

            if product_id not in seen_ids:
                seen_ids.add(product_id)
                new_items_found = True

                category_products.append({
                    'name': name,
                    'price': price,
                    'url': product_url,
                    'id': product_id
                })

        if not new_items_found:
            print(f"Uyarı: {page}. sayfadaki tüm ürünler zaten taranmış. Sınır aşıldı, döngü kırılıyor.")
            break

        print(f"Sayfa {page} başarıyla çekildi. Bekleniyor...")
        page += 1
        time.sleep(random.uniform(1, 3))

    return category_products


if __name__ == "__main__":
    targets = [
        {"url": "https://www.chakra.com.tr/mobilya/", "name": "mobilya"},
        {"url": "https://www.chakra.com.tr/yatak-odasi/", "name": "yatak_odasi"},
        {"url": "https://www.chakra.com.tr/ev-dekorasyonu/", "name": "ev_dekorasyonu"}
    ]

    all_scraped_data = []

    # Tüm kategorileri gez ve verileri tek bir ana listeye ekle
    for target in targets:
        data = scrape_chakra_category(target["url"], target["name"])
        all_scraped_data.extend(data)

        # Tarama bittikten sonra tek bir CSV'ye kaydet
        if all_scraped_data:
            # Scriptin bulunduğu klasörü (InflationItems/Codes/HomeGoods) bul ve 2 üst dizine (InflationItems) çık
            script_dir = os.path.dirname(os.path.abspath(__file__))
            output_dir = os.path.abspath(os.path.join(script_dir, "..", "..", "Datas", "HomeGoods"))

            # Hedef klasör yoksa hata vermemesi için oluştur
            os.makedirs(output_dir, exist_ok=True)

            date_str = datetime.now().strftime("%Y_%m_%d")
            filename = f"chakra_all_categories_{date_str}.csv"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['name', 'price', 'url', 'id'])
                writer.writeheader()
                writer.writerows(all_scraped_data)

            print(f"\nBAŞARILI: Toplam {len(all_scraped_data)} benzersiz ürün tek CSV olarak buraya kaydedildi:")
            print(f"-> {filepath}\n")
        else:
            print("\nUyarı: Hiçbir kategoriden ürün çekilemedi, CSV oluşturulmadı.\n")