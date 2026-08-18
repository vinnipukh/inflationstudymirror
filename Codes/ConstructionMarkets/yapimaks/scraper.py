#!/usr/bin/env python3
"""
Yapimaks.com Product Scraper — API Edition (tarayıcısız)

Çalışma mantığı (2026-08-19 revizyonu):
- Sitemap (products1.xml) ürün kataloğunun TAMAMINI ve her ürünün <lastmod>
  (son değişiklik / fiyat güncelleme) tarihini içerir.
- Günlük dosya, dünkü anlık görüntünün üzerine inşa edilir:
  * Dünün satırları AYNEN taşınır — sitemap geçici olarak küçülse bile
    ürün kaybedilmez. Yalnızca GRACE_DAYS gün üst üste sitemap'te
    görünmeyen ürünler düşürülür (gerçekten kaldırılmış ürünler).
  * Sitemap'teki <lastmod> değeri satırın scraped_at tarihinden yeniyse
    ürün YENİDEN çekilir → fiyat değişiklikleri yakalanır.
  * Boş fiyatlı satırlar (geçmişteki hatalı kayıtlar) yeniden çekilir.
- API hatalarında (429/5xx/ağ) BOŞ SATIR YAZILMAZ:
  * Mevcut ürün yenilenemezse eski satırı korunur (scraped_at eski kalır,
    sonraki çalıştırmada lastmod karşılaştırması yine tetiklenir → self-heal).
  * Yeni ürün çekilemezse bugün atlanır, yarın tekrar denenir.
- 429 yanıtlarında Retry-After / üstel geri çekilme uygulanır.
- Sitemap indirilemez veya geçersizse çalışma durdurulur, veriye dokunulmaz.

Kullanım:
  python scraper.py                 # normal günlük çalışma
  python scraper.py --limit 10      # test: en fazla 10 ürün çek
  python scraper.py --out-dir PATH  # test: çıktıyı farklı dizine yaz
"""

import argparse
import csv
import json
import logging
import os
import re
import signal
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta

import requests

# ─── DİZİN YAPISI ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Datas", "ConstructionSuppliesMarkets", "yapimaks")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# ─── AYARLAR ─────────────────────────────────────────────────────────────────
SITEMAP_URL = "https://yapimaks.com/sitemap/products1.xml"
SITE_URL = "https://yapimaks.com"
API_BASE = "https://yapimaks.com/api/tr/v1/layouts/b2c/products/{product_id}.json"
DELAY = 2.0
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 30.0        # 429: 30s, 60s, 120s (Retry-After varsa o kullanılır)
RETRY_MAX_SECONDS = 300.0
GRACE_DAYS = 7                   # sitemap'te görünmeyen ürün kaç gün taşınır
STATE_FILE = "last_seen.json"    # {url: "YYYY-MM-DD"} — sitemap'te son görülme
# İlk iki sütun istendiği gibi ayarlandı, geri kalanlar arkasına eklendi.
FIELDNAMES = ["product-name", "product-price", "product_id", "sku", "marka_id",
              "stok_durumu", "birim", "vat_rate", "currency", "url", "scraped_at"]
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")

# ─────────────────────────────────────────────────────────────────────────────

# ── LOGGING ──────────────────────────────────────────────────────────────────
def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    # Windows konsolunda Turkce karakterler icin hata olusmamasi adina
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
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

def get_latest_csv(exclude_path: str = None) -> str:
    if not os.path.exists(OUTPUT_DIR):
        return None
    csv_files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".csv")])
    if not csv_files:
        return None
    latest = os.path.join(OUTPUT_DIR, csv_files[-1])
    if exclude_path and latest == exclude_path:
        if len(csv_files) < 2:
            return None
        return os.path.join(OUTPUT_DIR, csv_files[-2])
    return latest

def load_rows(csv_path: str) -> dict:
    """CSV'yi {url: row} sözlüğü olarak yükler (sıra korunur)."""
    rows = {}
    if not os.path.isfile(csv_path):
        return rows
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url", "")
            if url:
                rows[url] = row
    return rows

def open_csv_writer(csv_path: str):
    # Dosya her çalıştırmada sıfırdan kurulur (rebuild semantics) — "w" modu
    f = open(csv_path, "w", newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    f.flush()
    return f, writer

def write_row(f, writer, data: dict):
    writer.writerow(data)
    f.flush()

def clean_row(row: dict) -> dict:
    """Eski sütun adlarını yeni şemaya taşır, yalnızca FIELDNAMES bırakır."""
    if "name" in row and "product-name" not in row:
        row["product-name"] = row.pop("name")
    if "price" in row and "product-price" not in row:
        row["product-price"] = row.pop("price").replace(",", ".")
    return {k: row.get(k, "") for k in FIELDNAMES}

# ── STATE (last_seen) ─────────────────────────────────────────────────────────
def load_state() -> dict:
    state_path = os.path.join(OUTPUT_DIR, STATE_FILE)
    if not os.path.isfile(state_path):
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning(f"State dosyasi okunamadi, sifirdan baslaniyor: {e}")
        return {}

def save_state(state: dict):
    state_path = os.path.join(OUTPUT_DIR, STATE_FILE)
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception as e:
        log.error(f"State dosyasi yazilamadi: {e}")

# ── SİTEMAP FONKSIYONLARI ─────────────────────────────────────────────────────
def fetch_sitemap(session: requests.Session) -> str:
    log.info(f"Sitemap indiriliyor: {SITEMAP_URL}")
    r = session.get(SITEMAP_URL, timeout=30)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if "html" in ctype.lower():
        raise RuntimeError(f"Sitemap yerine HTML yaniti geldi (status {r.status_code})")
    return r.text

def parse_urls(xml_text: str) -> list:
    """(url, lastmod) çiftlerini döndürür. Geçersiz/boş ise hata fırlatır."""
    xml_text = re.sub(r' xmlns="[^"]+"', "", xml_text)
    root = ET.fromstring(xml_text)
    urls = []
    for el in root.findall(".//url"):
        loc = el.findtext("loc", "").strip()
        if loc:
            urls.append((loc, el.findtext("lastmod", "").strip() or None))
    if not urls:
        raise RuntimeError("Sitemap hicbir URL icermiyor")
    return urls

def is_product_url(url: str) -> bool:
    return bool(re.search(r"-p\d+$", url.rstrip("/")))

def extract_product_id(url: str) -> str:
    m = re.search(r"-p(\d+)$", url.rstrip("/"))
    return m.group(1) if m else ""

# ── SCRAPE FONKSIYONU ─────────────────────────────────────────────────────────
def scrape_product(session: requests.Session, url: str) -> dict:
    """Ürünü API'den çeker. Başarısız olursa None döner (satır YAZILMAZ).

    Başarılı dönüşte result["_ok"] = True ayarlanır; hata durumunda dönen
    dict'te "_ok" = False olur ve çağıran satırı yazmaz.
    """
    product_id = extract_product_id(url)
    result = {
        "product-name": "",
        "product-price": "",
        "product_id": product_id,
        "sku": "",
        "marka_id": "",
        "stok_durumu": "",
        "birim": "",
        "vat_rate": "",
        "currency": "TRY",
        "url": url,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "_ok": False,
    }
    api_url = API_BASE.format(product_id=product_id)
    last_err = None

    for attempt in range(1, MAX_RETRIES + 1):
        if _shutdown:
            log.warning(f"[{product_id}] Kapanma sinyali, deneme durduruldu.")
            return result

        try:
            r = session.get(api_url, timeout=20)

            if r.status_code == 429:
                wait = _retry_after_seconds(r, attempt)
                log.warning(f"[{product_id}] 429 Too Many Requests — {wait:.0f}s bekleniyor "
                            f"(deneme {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                continue

            if not r.headers.get("content-type", "").startswith("application/json"):
                log.warning(f"[{product_id}] Session suresi dolmus, yenileniyor "
                            f"(deneme {attempt}/{MAX_RETRIES})...")
                session.cookies.clear()
                session.get(SITE_URL, timeout=30)
                continue

            r.raise_for_status()
            data = r.json()

            product = data.get("product", {}).get("data", {})
            attrs = product.get("attributes", {})
            included = data.get("product", {}).get("included", [])

            result["product-name"] = attrs.get("name", "")
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
                        result["product-price"] = f"{price_kdv:.2f}"
                    result["birim"] = str(unit_attrs.get("unit_id", ""))
                    break

            if not result["product-price"]:
                raise RuntimeError("API yanitinda fiyat bulunamadi")

            result["_ok"] = True
            log.info(f"[{product_id}] {result['product-name'][:40]!r} | "
                     f"{result['product-price']} TL | SKU: {result['sku']}")
            return result

        except Exception as e:
            last_err = e
            log.warning(f"[{url}] Deneme {attempt}/{MAX_RETRIES} hata: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(5 * attempt)

    log.error(f"[{url}] Tum denemeler basarisiz: {last_err}")
    return result  # _ok=False

def _retry_after_seconds(response, attempt: int) -> float:
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return min(float(raw), RETRY_MAX_SECONDS)
        except ValueError:
            pass
    return min(RETRY_BASE_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_SECONDS)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    global OUTPUT_DIR

    parser = argparse.ArgumentParser(description="Yapimaks fiyat takip scraper")
    parser.add_argument("--limit", type=int, default=0,
                        help="Test modu: en fazla bu kadar urun cek (0 = sinirsiz)")
    parser.add_argument("--out-dir", type=str, default=None,
                        help="Test modu: cikti dizinini degistir")
    args = parser.parse_args()
    if args.out_dir:
        OUTPUT_DIR = os.path.abspath(args.out_dir)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    setup_logging()
    log.info("=" * 50)
    log.info("Yapimaks Scraper basliyor")
    log.info("=" * 50)

    session = make_session()

    # 1) Sitemap indir + dogrula (hata olursa hicbir seye dokunma)
    try:
        new_xml = fetch_sitemap(session)
        sitemap_entries = parse_urls(new_xml)
    except Exception as e:
        log.error(f"Sitemap alinamadi/parse edilemedi: {e} — bugunku dosya OLUSTURULMAYACAK.")
        sys.exit(1)

    sitemap = {}
    for url, lastmod in sitemap_entries:
        if is_product_url(url):
            sitemap[url] = lastmod
    if not sitemap:
        log.error("Sitemap hicbir urun URL'si icermiyor — bugunku dosya OLUSTURULMAYACAK.")
        sys.exit(1)
    log.info(f"Sitemap'ten toplam {len(sitemap)} urun URL'si bulundu.")

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_date = date.today()
    csv_path = get_csv_path()

    # 2) Dünün anlık görüntüsü (bugünün dosyası hariç)
    yesterday_path = get_latest_csv(exclude_path=csv_path)
    if yesterday_path:
        log.info(f"Dunun dosyasi: {os.path.basename(yesterday_path)}")
    yesterday_rows = load_rows(yesterday_path) if yesterday_path else {}
    log.info(f"Dunun dosyasinda {len(yesterday_rows)} urun var.")

    # 3) State güncelle: bugün sitemap'te görünen her URL
    state = load_state()
    if not state and yesterday_rows:
        # İlk çalışma: dünkü satırları "dün görüldü" say, anında düşürme olmasın
        yesterday_str = (today_date - timedelta(days=1)).isoformat()
        state = {url: yesterday_str for url in yesterday_rows}
        log.info("State dosyasi yok, dunun satirlariyla baslatildi.")
    for url in sitemap:
        state[url] = today_str

    # 4) Taşıma: dünün satırları (grace süresi içindeyse korunur)
    rows = {}
    dropped = []
    for url, row in yesterday_rows.items():
        last_seen = state.get(url)
        try:
            seen_days = (today_date - date.fromisoformat(last_seen)).days if last_seen else None
        except ValueError:
            seen_days = None
        if url in sitemap or (seen_days is not None and seen_days <= GRACE_DAYS):
            rows[url] = row
        else:
            dropped.append(url)
    if dropped:
        log.warning(f"{len(dropped)} urun {GRACE_DAYS}+ gun sitemap'te gorunmuyor, dosyadan dusuruldu: "
                    f"{dropped[:5]}{'...' if len(dropped) > 5 else ''}")

    # 5) Çekilecekler: yeni ürünler + lastmod yenilenenler + boş fiyatlılar
    to_scrape = []
    for url, lastmod in sitemap.items():
        row = yesterday_rows.get(url)
        if row is None:
            to_scrape.append(url)                                   # yeni ürün
        elif not row.get("product-price", "").strip():
            to_scrape.append(url)                                   # boş kayıt (self-heal)
        elif lastmod and lastmod > row.get("scraped_at", "")[:10]:
            to_scrape.append(url)                                   # fiyatı değişmiş
    to_scrape = sorted(to_scrape)

    if args.limit > 0:
        log.warning(f"TEST MODU: --limit {args.limit} — yalnizca ilk {args.limit} urun cekilecek")
        to_scrape = to_scrape[:args.limit]

    log.info(f"Tasinacak (degismeyen) urun: {len(rows)} | Yeniden cekilecek: {len(to_scrape)}")

    # 6) Dosyayı kur: önce taşınan satırlar (taze çekilecekler HARİÇ),
    #    sonra çekilenler. Böylece aynı ürün iki kez yazılmaz.
    refresh_set = set(to_scrape)
    csv_file, writer = open_csv_writer(csv_path)
    written = 0
    for url, row in rows.items():
        if url in refresh_set:
            continue  # eski satır ancak çekme başarısız olursa yazılır
        write_row(csv_file, writer, clean_row(row))
        written += 1

    refreshed = 0
    failed = 0
    kept = 0
    try:
        for i, url in enumerate(to_scrape, 1):
            if _shutdown:
                log.warning(f"Erken cikis: {i - 1}/{len(to_scrape)} islendi.")
                break
            log.info(f"[{i}/{len(to_scrape)}] {url}")
            data = scrape_product(session, url)
            if data.get("_ok"):
                write_row(csv_file, writer, {k: data[k] for k in FIELDNAMES})
                refreshed += 1
            else:
                failed += 1
                old = yesterday_rows.get(url)
                if old is not None:
                    # Değişmiş ama çekilememiş ürün: eski satırı koru (self-heal;
                    # scraped_at eski kalır, yarın lastmod karşılaştırması yine tetikler)
                    write_row(csv_file, writer, clean_row(dict(old)))
                    kept += 1
                    log.warning(f"[{url}] Eski satir korundu, yarin tekrar denenir.")
            time.sleep(DELAY)
    finally:
        csv_file.close()

    # 7) State kaydet
    save_state(state)

    log.info("=" * 50)
    log.info(f"Tamamlandi! Tasinan: {written} | Tazelenen: {refreshed} | "
             f"Basarisiz: {failed} | Korunan eski satir: {kept} | Dusurulen: {len(dropped)}")
    log.info(f"Dosya: {csv_path} (toplam {written + refreshed + kept} urun)")
    log.info("=" * 50)

if __name__ == "__main__":
    main()
