#!/usr/bin/env python3
"""
Yapimaks.com Product Scraper — API Edition, async (tarayıcısız)

Çalışma mantığı (2026-08-19 revizyonu, 2026-09-02 async revizyonu):
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
- 2026-09-02: çekim artık ASYNC (`aiohttp`) — WORKERS eşzamanlı işçi ve global
  RATE (saniyede istek) limiti ile çalışır. GitHub Actions'ın public repo
  job'ları için 6 saatlik donanımsal üst limiti vardır (timeout-minutes daha
  yüksek olsa bile); bu yüzden varsayılan olarak:
  * --refresh-budget: günde en fazla N ürün yenilenir (varsayılan 2500) —
    en bayat ürünler önce; tam katalog yaklaşık 3-4 günde tazelenir ve tek bir
    koşu asla saatlerce sürmez (catch-up günleri ~1-1.5 saat),
  * --max-duration (dk) varsayılan 240 ile koşu asla GitHub'ın 6 saatlik public
    repo job limitine takılmaz: süre dolunca yeni istek başlamaz, çekilemeyenler
    için dünkü satır korunur ve kalanlar YARIN (en eski scraped_at önce) devam
    eder (self-heal).
- Sitemap indirilemez veya geçersizse çalışma durdurulur, veriye dokunulmaz.

Kullanım:
  python scraper.py                     # normal günlük çalışma
  python scraper.py --limit 10          # test: en fazla 10 ürün çek
  python scraper.py --out-dir PATH      # test: çıktıyı farklı dizine yaz
  python scraper.py --workers 8 --rate 6 --max-duration 240
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import random
import re
import signal
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta

import aiohttp

# ─── DİZİN YAPISI ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", ".."))
ITEMS_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))
OUTPUT_DIR = os.path.join(ITEMS_ROOT, "Datas", "ConstructionSuppliesMarkets", "yapimaks")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# ─── AYARLAR ─────────────────────────────────────────────────────────────────
SITEMAP_URL = "https://yapimaks.com/sitemap/products1.xml"
SITE_URL = "https://yapimaks.com"
API_BASE = "https://yapimaks.com/api/tr/v1/layouts/b2c/products/{product_id}.json"
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 30.0        # 429: 30s, 60s, 120s (Retry-After varsa o kullanılır)
RETRY_MAX_SECONDS = 300.0
GRACE_DAYS = 7                   # sitemap'te görünmeyen ürün kaç gün taşınır
STATE_FILE = "last_seen.json"    # {url: "YYYY-MM-DD"} — sitemap'te son görülme
WORKERS = 8                      # eşzamanlı async işçi sayısı
# Global istek limiti (istek/saniye). Site 429'u normal koşullarda bile
# üretebiliyor (eski seri çalışmalarda da 429'lar vardı); asıl hayatta kalma
# mekanizması Retry-After + üstel geri çekilme. 429 görünce hız yarıya iner
# (0.2/sn taban), başarılı akışta tekrar yükselir.
RATE = 0.8                       # başlangıç hızı (saniyede istek)
REFRESH_BUDGET = 2500            # günlük yenileme bütçesi (0 = sınırsız)
MAX_DURATION_MINUTES = 300       # koşu bütçesi (dk); 0 = sınırsız
HTTP_TIMEOUT_SECONDS = 20.0      # tek istek zaman aşımı
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
    log.warning("Sinyal alindi, temiz kapatiliyor... (Mevcut istekler bitecek, yenisi baslamayacak)")
    _shutdown = True

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

# ── ASYNC SESSION ────────────────────────────────────────────────────────────
class SessionState:
    """aiohttp istemcisi + session yenileme. Cookie'ler sunucunun Set-Cookie
    yanitlarindan otomatik toplanir (eskiden hardcoded kurabiye vardi; sunucu
    ana sayfada taze kurabiye koyuyor, o yuzden artik gerek yok)."""

    def __init__(self):
        self.client = None
        self.refresh_lock = asyncio.Lock()

    async def acquire(self):
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS, connect=30.0)
        self.client = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "accept-language": "tr,en;q=0.9",
                "user-agent": USER_AGENT,
            },
        )
        await self._visit_homepage(first=True)

    async def _visit_homepage(self, first: bool = False):
        tag = "Cookie aliniyor" if first else "Session yenileniyor"
        log.info(f"Ana sayfa ziyaret ediliyor, {tag.lower()}...")
        # Ana sayfa da 429 dönebilir (site agresif limitliyor); web'i temiz
        # kapatmak yerine birkaç kez geri çekilerek deneriz.
        for attempt in range(1, MAX_RETRIES + 1):
            if _shutdown:
                raise RuntimeError("Kapanma sinyali alindi, ana sayfa denenmedi")
            try:
                async with self.client.get(SITE_URL, timeout=30) as r:
                    if r.status == 429:
                        wait = min(float(r.headers.get("Retry-After", "30") or 30), RETRY_MAX_SECONDS)
                        log.warning(f"Ana sayfa 429 (deneme {attempt}/{MAX_RETRIES}) — "
                                    f"{wait:.0f}s bekleniyor")
                        await asyncio.sleep(wait)
                        continue
                    r.raise_for_status()
                log.info("Cookie basariyla alindi.")
                return
            except aiohttp.ClientResponseError as e:
                log.warning(f"Ana sayfa hata {e.status} (deneme {attempt}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(15 * attempt)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.warning(f"Ana sayfa ag hatasi: {e} (deneme {attempt}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(10 * attempt)
        raise RuntimeError("Ana sayfa (cookie) alinamadi — calisma durduruldu, veriye dokunulmadi.")

    async def refresh(self):
        async with self.refresh_lock:
            self.client.cookie_jar.clear()
            await self._visit_homepage(first=False)

    async def close(self):
        if self.client is not None:
            await self.client.close()

# ── ASYNC RATE LIMITER ───────────────────────────────────────────────────────
class RateLimiter:
    """Token bucket: tüm işçiler ortak limiti paylaşır.

    ``rate`` saniyedeki istek sayısıdır. 429 görünce hız yarıya düşer (en düşük
    0.2 istek/sn), art arda başarılı isteklerde yavaşça eski hızına döner.
    """

    def __init__(self, rate: float, capacity: float = 3.0):
        # Kapasite bilinçli olarak küçük tutulur: 429 hız kestiğinde birikmiş
        # token'lar hemen biter, istekler yeni (düşük) hıza anında uyar.
        self.base_rate = max(0.2, float(rate))
        self.rate = self.base_rate
        self.capacity = float(capacity)
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()
        self.success_streak = 0

    async def acquire(self):
        while True:
            async with self.lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / max(self.rate, 0.01)
            await asyncio.sleep(wait)

    async def note_success(self):
        self.success_streak += 1
        if self.success_streak >= 25 and self.rate < self.base_rate:
            async with self.lock:
                self.rate = min(self.base_rate, self.rate * 1.25)
                self.success_streak = 0

    async def note_429(self):
        async with self.lock:
            self.rate = max(0.2, self.rate * 0.5)
            self.success_streak = 0

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
        log.info(f"State yaziliyor: {len(state)} url -> {state_path}")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception as e:
        log.error(f"State dosyasi yazilamadi: {e}")

# ── SİTEMAP FONKSIYONLARI ─────────────────────────────────────────────────────
async def fetch_sitemap(state: SessionState) -> str:
    log.info(f"Sitemap indiriliyor: {SITEMAP_URL}")
    for attempt in range(1, MAX_RETRIES + 1):
        if _shutdown:
            raise RuntimeError("Kapanma sinyali alindi, sitemap denenmedi")
        try:
            async with state.client.get(SITEMAP_URL, timeout=30) as r:
                if r.status == 429:
                    wait = min(float(r.headers.get("Retry-After", "30") or 30), RETRY_MAX_SECONDS)
                    log.warning(f"Sitemap 429 (deneme {attempt}/{MAX_RETRIES}) — {wait:.0f}s bekleniyor")
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                if "html" in ctype.lower():
                    raise RuntimeError(f"Sitemap yerine HTML yaniti geldi (status {r.status})")
                return await r.text()
        except aiohttp.ClientResponseError as e:
            log.warning(f"Sitemap hata {e.status} (deneme {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(15 * attempt)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning(f"Sitemap ag hatasi: {e} (deneme {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(10 * attempt)
    raise RuntimeError("Sitemap indirilemedi — calisma durduruldu, veriye dokunulmadi.")

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

# ── SCRAPE FONKSIYONU (async) ────────────────────────────────────────────────
def _retry_after_seconds(response, attempt: int) -> float:
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return min(float(raw), RETRY_MAX_SECONDS)
        except ValueError:
            pass
    return min(RETRY_BASE_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_SECONDS)

async def fetch_product(state: SessionState, limiter: RateLimiter, url: str) -> dict:
    """Ürünü API'den çeker. Başarısız olursa _ok=False döner (satır YAZILMAZ,
    eskisi korunur)."""
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
            await limiter.acquire()
            await asyncio.sleep(random.uniform(0.0, 0.15))  # doğal seyreltme (jitter)
            async with state.client.get(api_url, timeout=HTTP_TIMEOUT_SECONDS) as r:
                if r.status == 429:
                    await limiter.note_429()
                    wait = _retry_after_seconds(r, attempt)
                    log.warning(f"[{product_id}] 429 Too Many Requests — {wait:.0f}s bekleniyor "
                                f"(deneme {attempt}/{MAX_RETRIES}, hiz {limiter.rate:.1f}/sn)")
                    await asyncio.sleep(wait)
                    continue

                if not r.headers.get("content-type", "").startswith("application/json"):
                    log.warning(f"[{product_id}] Session suresi dolmus, yenileniyor "
                                f"(deneme {attempt}/{MAX_RETRIES})...")
                    await state.refresh()
                    continue

                r.raise_for_status()
                data = await r.json()
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            last_err = e
            log.warning(f"[{url}] Ag hatasi (deneme {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(3 * attempt)
            continue
        except Exception as e:
            # JSON parse vb. hatalar da deneme hakkı tüketir
            last_err = e
            log.warning(f"[{url}] Yanit islenemedi (deneme {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 * attempt)
            continue

        try:
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
            await limiter.note_success()
            log.info(f"[{product_id}] {result['product-name'][:40]!r} | "
                     f"{result['product-price']} TL | SKU: {result['sku']}")
            return result

        except Exception as e:
            last_err = e
            log.warning(f"[{url}] Urun parse hatasi (deneme {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 * attempt)

    log.error(f"[{url}] Tum denemeler basarisiz: {last_err}")
    return result  # _ok=False

# ── ASYNC ANA ÇEKİM ──────────────────────────────────────────────────────────
async def fetch_all(
    state: SessionState,
    limiter: RateLimiter,
    to_scrape: list,
    yesterday_rows: dict,
    csv_file,
    writer,
    max_duration: float,
) -> tuple:
    """İşçi havuzuyla ürünleri çeker; her sonuç gelir gelmez satır yazılır.

    ``max_duration`` (saniye) aşılırsa yeni istek başlatılmaz; kalan ürünler
    için dünkü satır korunur (yeni ürün ise bugün atlanır, yarın tekrar).
    """
    semaphore = asyncio.Semaphore(WORKERS)
    started_at = time.monotonic()
    refreshed = failed = kept = skipped = 0
    progress = {"done": 0, "total": len(to_scrape)}

    def _remaining_budget() -> float:
        return max_duration - (time.monotonic() - started_at) if max_duration > 0 else float("inf")

    async def one(url: str):
        nonlocal refreshed, failed, kept, skipped
        async with semaphore:
            if _shutdown or _remaining_budget() <= 0:
                # Bütçe/limit nedeniyle bu koşuda çekilemeyen ürünün dünkü
                # satırını yine de bugünkü dosyaya taşı (günlük anlık görüntü
                # eksik kalmasın). scraped_at eski kalır -> yarın yine öncelikli.
                skipped += 1
                old = yesterday_rows.get(url)
                if old is not None:
                    write_row(csv_file, writer, clean_row(dict(old)))
                    kept += 1
                progress["done"] += 1
                return
            data = await fetch_product(state, limiter, url)
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
            progress["done"] += 1
            if progress["done"] % 100 == 0:
                log.info(f"... ilerleme {progress['done']}/{progress['total']} "
                         f"(tazelenen {refreshed}, basarisiz {failed}, korunan {kept}, atlanan {skipped})")

    tasks = [asyncio.create_task(one(url)) for url in to_scrape]
    await asyncio.gather(*tasks, return_exceptions=True)
    return refreshed, failed, kept, skipped

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    global OUTPUT_DIR, WORKERS

    parser = argparse.ArgumentParser(description="Yapimaks fiyat takip scraper (async)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Test modu: en fazla bu kadar urun cek (0 = sinirsiz)")
    parser.add_argument("--out-dir", type=str, default=None,
                        help="Test modu: cikti dizinini degistir")
    parser.add_argument("--workers", type=int, default=WORKERS,
                        help=f"es zamanli async isci sayisi (varsayilan {WORKERS})")
    parser.add_argument("--rate", type=float, default=RATE,
                        help=f"kuresel istek limiti, istek/saniye (varsayilan {RATE})")
    parser.add_argument("--refresh-budget", type=int, default=REFRESH_BUDGET,
                        help=f"gunluk yenileme butcesi; 0 = sinirsiz (varsayilan {REFRESH_BUDGET})")
    parser.add_argument("--max-duration", type=int, default=MAX_DURATION_MINUTES,
                        help=f"kosu butcesi, dakika; 0 = sinirsiz (varsayilan {MAX_DURATION_MINUTES})")
    args = parser.parse_args()
    if args.out_dir:
        OUTPUT_DIR = os.path.abspath(args.out_dir)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    WORKERS = max(1, args.workers)
    rate = max(0.2, args.rate)
    max_duration = max(0, args.max_duration) * 60.0

    setup_logging()
    log.info("=" * 50)
    log.info("Yapimaks Scraper basliyor (async)")
    log.info("=" * 50)
    log.info(f"Parametreler: workers={WORKERS}, rate={rate}/sn, "
             f"max_duration={args.max_duration} dk")

    async def run():
        state = SessionState()
        try:
            await state.acquire()

            # 1) Sitemap indir + dogrula (hata olursa hicbir seye dokunma)
            try:
                new_xml = await fetch_sitemap(state)
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
            state_data = load_state()
            if not state_data and yesterday_rows:
                # İlk çalışma: dünkü satırları "dün görüldü" say, anında düşürme olmasın
                yesterday_str = (today_date - timedelta(days=1)).isoformat()
                state_data = {url: yesterday_str for url in yesterday_rows}
                log.info("State dosyasi yok, dunun satirlariyla baslatildi.")
            for url in sitemap:
                state_data[url] = today_str

            # 4) Taşıma: dünün satırları (grace süresi içindeyse korunur)
            rows = {}
            dropped = []
            for url, row in yesterday_rows.items():
                last_seen = state_data.get(url)
                try:
                    seen_days = (today_date - date.fromisoformat(last_seen)).days if last_seen else None
                except ValueError:
                    seen_days = None
                if url in sitemap or (seen_days is not None and seen_days <= GRACE_DAYS):
                    rows[url] = row
                else:
                    dropped.append(url)
            if dropped:
                log.warning(f"{len(dropped)} urun {GRACE_DAYS}+ gun sitemap'te gorunmuyor, "
                            f"dosyadan dusuruldu: {dropped[:5]}{'...' if len(dropped) > 5 else ''}")

            # 5) Çekilecekler: yeni ürünler + lastmod yenilenenler + boş fiyatlılar
            candidates = []
            for url, lastmod in sitemap.items():
                row = yesterday_rows.get(url)
                if row is None:
                    candidates.append((url, 0, ""))                     # yeni ürün
                elif not row.get("product-price", "").strip():
                    candidates.append((url, 1, row.get("scraped_at", "")))  # boş kayıt
                elif lastmod and lastmod > row.get("scraped_at", "")[:10]:
                    candidates.append((url, 1, row.get("scraped_at", "")))  # değişmiş
            # En eski scraped_at önce (en bayat ürünler önce tazelenir; koşu
            # bütçesi yetmezse kalanlar yarın devam eder — sürekli aynı kuyruk
            # başında kalma riski yok).
            to_scrape = [url for url, _, _ in sorted(candidates, key=lambda c: (c[1], c[2], c[0]))]

            if args.refresh_budget > 0:
                budget = min(args.refresh_budget, len(to_scrape))
                if budget < len(to_scrape):
                    log.warning(f"GUNLUK BUTCE: {len(to_scrape)} urun cekilmeye aday, "
                                f"ilk {budget} tazelenecek; kalan {len(to_scrape) - budget} "
                                f"yarin (en bayatlar önce) devam eder (self-heal).")
                    to_scrape = to_scrape[:budget]
                else:
                    log.info(f"GUNLUK BUTCE: {budget} urun aday — hepsi bu koşuda tazelenir.")

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

            refreshed = failed = kept = skipped = 0
            try:
                limiter = RateLimiter(rate)
                refreshed, failed, kept, skipped = await fetch_all(
                    state, limiter, to_scrape, yesterday_rows,
                    csv_file, writer, max_duration,
                )
            finally:
                csv_file.close()

            # 7) State kaydet
            save_state(state_data)

            status = "TIMEOUT" if skipped else "OK"
            log.info("=" * 50)
            log.info(f"Tamamlandi [{status}]! Tasinan: {written} | Tazelenen: {refreshed} | "
                     f"Basarisiz: {failed} | Korunan eski satir: {kept} | "
                     f"Atlanan (sure/limit): {skipped} | Dusurulen: {len(dropped)}")
            log.info(f"Dosya: {csv_path} (toplam {written + refreshed + kept} urun)")
            log.info("=" * 50)
        finally:
            await state.close()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Klavye ile kapatildi.")
        sys.exit(130)
    return 0

if __name__ == "__main__":
    main()
