import os
import time
import csv
import json
import gzip
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests

# --- KLASÖR VE LOG YAPILANDIRMASI ---
# Görseldeki ağaç yapısına birebir uyumlu yollar
DATA_DIR = "Datas/Cosmetics/Watson"
LOG_DIR = "logs"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

today_str = datetime.now().strftime('%Y-%m-%d')
# Loglar kök dizindeki logs klasörüne, veriler Datas içine
LOG_FILE = os.path.join(LOG_DIR, f"watsons_scraper_{today_str}.log")
CSV_FILE = os.path.join(DATA_DIR, f"{today_str}_watsons_fiyatlar.csv")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def fetch_sitemap_urls(client):
    """Sitemap'ten tüm ürün URL'lerini çeker."""
    logging.info("Sitemap analizi yapılıyor...")
    urls = []
    try:
        res = client.get("https://www.watsons.com.tr/sitemap.xml", timeout=30)
        soup = BeautifulSoup(res.content, 'xml')
        sitemaps = [loc.text for loc in soup.find_all('loc') if "Product" in loc.text]

        for s_url in sitemaps:
            s_res = client.get(s_url, timeout=30)
            content = s_res.content
            if content.startswith(b'\x1f\x8b'):  # GZIP açma
                content = gzip.decompress(content)

            sub_soup = BeautifulSoup(content, 'xml')
            for url_node in sub_soup.find_all('url'):
                loc = url_node.find('loc').text
                if loc and "media.watsons.com.tr" not in loc:
                    urls.append(loc.strip())

        urls = list(set(urls))  # Tekrarları önle
        logging.info(f"Sitemap'te {len(urls)} benzersiz ürün bulundu.")
        return urls
    except Exception as e:
        logging.error(f"Sitemap çekme hatası: {e}")
        return []


def run_daily_scraper():
    logging.info("=== GÜNLÜK SCRAPER BAŞLATILDI ===")

    client = requests.Session(impersonate="chrome110")
    urls = fetch_sitemap_urls(client)

    if not urls:
        print("❌ Sitemap'ten URL çekilemedi, logları kontrol et.")
        return

    scraped_count = 0
    failed_count = 0

    # Bekleme süreleri: Eğer 3'ü de biterse döngü kendiliğinden sonraki ürüne geçer (Pas geçme).
    retry_delays = [10, 30, 60]

    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=['item_id', 'name', 'price', 'url'])
        writer.writeheader()

        for idx, url in enumerate(urls, 1):
            success = False
            item_id = url.split('/p/')[-1] if '/p/' in url else "N/A"

            for attempt, delay in enumerate(retry_delays):
                try:
                    # Zaman aşımını (timeout) kısa tutuyoruz ki limitleri zorlamayalım
                    res = client.get(url, timeout=15)

                    if res.status_code == 403:
                        logging.warning(f"403 Blok! URL: {url} | Bekleniyor: {delay}s")
                        time.sleep(delay)
                        continue

                    soup = BeautifulSoup(res.text, 'html.parser')
                    name, price = "N/A", "N/A"

                    # İsim çıkarma
                    for script in soup.find_all('script', type='application/ld+json'):
                        if script.string and url in script.string:
                            data = json.loads(script.string)
                            for entry in data.get('@graph', []):
                                if entry.get('@type') == 'Product':
                                    name = entry.get('name', 'N/A')

                    # Fiyat çıkarma
                    p_el = soup.select_one('span.price__default-value')
                    if p_el:
                        price = p_el.text.strip()

                    writer.writerow({
                        'item_id': item_id,
                        'name': name,
                        'price': price,
                        'url': url
                    })
                    f.flush()  # Veri kaybını önlemek için anında yaz

                    success = True
                    scraped_count += 1
                    break  # Başarılıysa retry döngüsünden çık

                except Exception as e:
                    logging.error(f"Hata ({url}) Deneme {attempt + 1}: {e} | Bekleniyor: {delay}s")
                    time.sleep(delay)

            if not success:
                failed_count += 1
                logging.error(f"❌ ATLANDI (3 deneme başarısız): {url}")

            if idx % 50 == 0:
                print(f"🔄 İşleniyor: {idx}/{len(urls)}... (Başarılı: {scraped_count}, Başarısız: {failed_count})")

            time.sleep(0.5)

    print(f"✅ Bitti! Başarılı: {scraped_count}, Başarısız: {failed_count}")
    logging.info(f"Tamamlandı. Başarılı: {scraped_count}, Başarısız: {failed_count}")


if __name__ == "__main__":
    run_daily_scraper()