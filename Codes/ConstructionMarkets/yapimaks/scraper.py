#!/usr/bin/env python3
"""
Yapimaks.com Product Scraper — API Edition (tarayıcısız)
- requests.Session ile otomatik cookie yönetimi
- Sitemap değişikliklerini takip eder
- Eski CSV'deki ürünleri güncel sitemap ile eşleştirip bugüne aktarır (Akıllı Kopyalama)
- O günkü CSV'de olan URL'leri atlar (kaldığı yerden devam)
- Her ürün anında CSV'ye yazılır (tarihli dosya adı)
"""

import csv
import logging
import os
import re
import signal
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

# ─── DİZİN YAPISI ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Datas", "yapimaks")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# ─── AYARLAR ─────────────────────────────────────────────────────────────────
SITEMAP_URL = "https://yapimaks.com/sitemap/products1.xml"
SITE_URL = "https://yapimaks.com"
API_BASE = "https://yapimaks.com/api/tr/v1/layouts/b2c/products/{product_id}.json"
DELAY = 2.0
FIELDNAMES = ["product_id", "name", "sku", "marka_id", "stok_durumu",
              "birim", "price", "vat_rate", "currency", "url", "scraped_at"]
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")


# ─────────────────────────────────────────────────────────────────────────────

# ── LOGGING ──────────────────────────────────────────────────────────────────
def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"yapimaks_{datetime.now().strftime('%Y-%m-%d')}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ]
    )


log = logging.getLogger(__name__)

# ── GRACEFUL SHUTDOWN ─────────────────────────────────────────────────────────
_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    log.warning("Sinyal alindi, temiz kapatiliyor...")
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ── SESSION ───────────────────────────────────────────────────────────────────
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "tr,en;q=0.9",
        "user-agent": USER_AGENT,
    })
    log.info("Ana sayfa ziyaret ediliyor, cookie aliniyor...")
    try:
        s.cookies.set('_epower_session',
                      'GYvSbyDJkg5sgnLQWU01iwOIh5aKd5yXy2xYIhe7sd%2Fq4eF0C8nVakyFPd2IxNbAXLECmkwMMgmiBQfxIyhzlRS%2F6MGvpi8TUKRdovL1RtACUmTeVtxOnwkEr2tOGdpW1eUhCSFUBRXgso4SwV%2F8tBYrUpBqskenZzHE3HE5oIoCGG3qPJAymsdI3eJF9MbqHwHcLOkvUuKeMhpF1g%3D%3D--a6fJ3AxXoHaccbtx--os%2BhYC4TEqlxZhSbLBPy4A%3D%3D',
                      domain='yapimaks.com')
        s.get(SITE_URL, timeout=30)
        log.info("Cookie basariyla alindi.")
    except Exception as e:
        log.error(f"Cookie alinamadi: {e}")
        sys.exit(1)

    s.headers.update({
        "accept": "application/json, text/plain, */*",
        "referer": SITE_URL,
    })
    return s


# ── CSV FONKSIYONLARI ─────────────────────────────────────────────────────────
def get_csv_path() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return os.path.join(OUTPUT_DIR, f"{today}.csv")


def get_latest_csv() -> str:
    if not os.path.exists(OUTPUT_DIR):
        return None
    csv_files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".csv")])
    if not csv_files:
        return None
    return os.path.join(OUTPUT_DIR, csv_files[-1])


def load_scraped_urls(csv_path: str) -> set:
    if not os.path.isfile(csv_path):
        return set()
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return {row["url"] for row in reader if row.get("url")}


def open_csv_writer(csv_path: str):
    file_exists = os.path.isfile(csv_path)
    f = open(csv_path, "a", newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    if not file_exists:
        writer.writeheader()
        f.flush()
    return f, writer


def write_row(f, writer, data: dict):
    writer.writerow(data)
    f.flush()


# ── SİTEMAP FONKSIYONLARI ─────────────────────────────────────────────────────
def fetch_sitemap(session: requests.Session) -> str:
    log.info(f"Sitemap indiriliyor: {SITEMAP_URL}")
    r = session.get(SITEMAP_URL, timeout=30)
    r.raise_for_status()
    return r.text


def parse_urls(xml_text: str) -> list:
    xml_text = re.sub(r' xmlns="[^"]+"', "", xml_text)
    root = ET.fromstring(xml_text)
    return [el.findtext("loc", "").strip() for el in root.findall(".//url")]


def is_product_url(url: str) -> bool:
    return bool(re.search(r"-p\d+$", url.rstrip("/")))


def extract_product_id(url: str) -> str:
    m = re.search(r"-p(\d+)$", url.rstrip("/"))
    return m.group(1) if m else ""


# ── SCRAPE FONKSIYONU ─────────────────────────────────────────────────────────
def scrape_product(session: requests.Session, url: str) -> dict:
    product_id = extract_product_id(url)
    result = {
        "product_id": product_id,
        "url": url,
        "name": "",
        "sku": "",
        "marka_id": "",
        "stok_durumu": "",
        "birim": "",
        "price": "",
        "vat_rate": "",
        "currency": "TRY",
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        api_url = API_BASE.format(product_id=product_id)
        r = session.get(api_url, timeout=20)

        if not r.headers.get("content-type", "").startswith("application/json"):
            log.warning("Session süresi dolmus, yenileniyor...")
            session.cookies.clear()
            session.get(SITE_URL, timeout=30)
            r = session.get(api_url, timeout=20)

        r.raise_for_status()
        data = r.json()

        product = data.get("product", {}).get("data", {})
        attrs = product.get("attributes", {})
        included = data.get("product", {}).get("included", [])

        result["name"] = attrs.get("name", "")
        result["sku"] = attrs.get("sku", "")
        result["marka_id"] = str(attrs.get("brand_id", ""))
        result["stok_durumu"] = "Var" if attrs.get("b2c_in_stock") else "Yok"
        result["vat_rate"] = str(attrs.get("vat_rate", ""))

        for item in included:
            if item.get("type") == "unit":
                unit_attrs = item.get("attributes", {})
                price_raw = unit_attrs.get("b2c_price")
                if price_raw is not None:
                    vat = attrs.get("vat_rate", 0) / 100
                    price_kdv = price_raw * (1 + vat)
                    result["price"] = f"{price_kdv:.2f}".replace(".", ",")
                result["birim"] = str(unit_attrs.get("unit_id", ""))
                break

        log.info(f"[{product_id}] {result['name'][:40]!r} | {result['price']} TL | SKU: {result['sku']}")

    except Exception as e:
        log.error(f"[{url}] Hata: {e}")

    return result


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    setup_logging()
    log.info("=" * 50)
    log.info("Yapimaks Scraper basliyor")
    log.info("=" * 50)

    # 1. Session al
    session = make_session()

    # 2. Sitemap'i indir
    new_xml = fetch_sitemap(session)
    new_urls = set(parse_urls(new_xml))
    product_urls = sorted(u for u in new_urls if is_product_url(u))
    log.info(f"Sitemap'ten toplam {len(product_urls)} urun URL'si bulundu.")

    # 3. Yolları belirle
    csv_path = get_csv_path()
    latest_csv = get_latest_csv()
    scraped_today = load_scraped_urls(csv_path)

    # 4. AKILLI KOPYALAMA MANTIĞI
    # Eğer bugün hiç ürün çekilmemişse (veya dosya yoksa) ve elimizde dünden kalan bir dosya varsa:
    if not scraped_today and latest_csv and latest_csv != csv_path:
        log.info(f"Bugune ait veri yok. Eski veri ({os.path.basename(latest_csv)}) süzülerek bugune aktariliyor...")
        try:
            with open(latest_csv, "r", encoding="utf-8-sig") as f_in, \
                    open(csv_path, "w", newline="", encoding="utf-8-sig") as f_out:

                reader = csv.DictReader(f_in)
                writer = csv.DictWriter(f_out, fieldnames=FIELDNAMES)
                writer.writeheader()

                aktarilan = 0
                for row in reader:
                    # Sadece güncel sitemap'te hala var olan URL'leri kopyala
                    if row.get("url") in new_urls:
                        writer.writerow(row)
                        aktarilan += 1

            log.info(f"Basarili! {aktarilan} urun dunden bugune aktarildi.")
        except Exception as e:
            log.error(f"Kopyalama sirasinda hata olustu: {e}")

    # 5. Kopyalamadan sonra bugünün dosyasını tekrar oku ve eksikleri bul
    scraped_urls = load_scraped_urls(csv_path)
    remaining = [u for u in product_urls if u not in scraped_urls]

    if scraped_urls:
        log.info(
            f"Guncel dosyada hazir olan urun: {len(scraped_urls)} | Sifirdan cekilecek (yeni) urun: {len(remaining)}")

    if not remaining:
        log.info("Sitemap'teki tum urunler zaten dosyamizda var, cikiliyor.")
        return

    # 6. Kalanları Scrape et
    csv_file, writer = open_csv_writer(csv_path)
    log.info(f"{len(remaining)} yeni urun scrapelanacak -> {csv_path}")

    count = 0
    try:
        for i, url in enumerate(remaining, 1):
            if _shutdown:
                log.warning(f"Erken cikis: {count}/{len(remaining)} tamamlandi.")
                break
            log.info(f"[{i}/{len(remaining)}] {url}")
            data = scrape_product(session, url)
            write_row(csv_file, writer, data)
            count += 1
            time.sleep(DELAY)
    finally:
        csv_file.close()

    log.info(f"Tamamlandi! Toplam {count} yeni urun eklendi -> {csv_path}")


if __name__ == "__main__":
    main()