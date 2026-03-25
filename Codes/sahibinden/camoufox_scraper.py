import os
import csv
import re
import json
import random
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from camoufox.async_api import AsyncCamoufox

# ============================================================
# YAPILANDIRMA
# ============================================================

DEFAULT_BRACKETS = [
    (0,       19_999),
    (20_000,  39_999),
    (40_000,  59_999),
    (60_000,  99_999),
    (100_000, 9_999_999),
]

CITIES = {
    "kayseri": {"folder": "Kayseri", "brackets": DEFAULT_BRACKETS},
    "sivas":   {"folder": "Sivas",   "brackets": DEFAULT_BRACKETS},
    "tokat":   {"folder": "Tokat",   "brackets": DEFAULT_BRACKETS},
}

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_BASE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../Datas/HousesRent/"))

# ============================================================
# SPEED PROFILE
# ============================================================

FAST_MODE = True

if FAST_MODE:
    NAV_WAIT              = (2.0,  4.0)   # after page.goto()
    PAGE_PAUSE            = (2.0,  4.0)   # pause between listing pages
    BRACKET_BREAK         = (1.0,  2.0)   # pause between brackets
    CHALLENGE_WAIT        = (4.0,  6.0)   # interval between challenge poll iterations
    TURNSTILE_IFRAME      = (0.5,  1.0)   # wait between iframe scan attempts
    CHALLENGE_RETRIES     = 8             # max challenge poll iterations
    POST_CLOSE_WAIT       = 10            # seconds after closing browser
    HOMEPAGE_WARMUP_WAIT  = (1.5,  2.5)   # initial warmup page sleep
    WARMUP_STEP_WAIT_1    = (0.5,  1.0)   # warmup mid-step 1
    WARMUP_STEP_WAIT_2    = (0.5,  1.0)   # warmup mid-step 2
    HUMAN_SCROLLS_MINMAX  = (1, 2)        # scroll count range for human_scroll
    HUMAN_MOVE_PROB       = 0.4           # probability to call human_random_move
    MAX_CONCURRENT_CITIES = 3             # max simultaneous browser instances
else:
    NAV_WAIT              = (8.0, 12.0)   # after page.goto()
    PAGE_PAUSE            = (8.0, 12.0)   # pause between listing pages
    BRACKET_BREAK         = (4.0,  6.0)   # pause between brackets
    CHALLENGE_WAIT        = (8.0, 11.0)   # interval between challenge poll iterations
    TURNSTILE_IFRAME      = (1.0,  2.0)   # wait between iframe scan attempts
    CHALLENGE_RETRIES     = 15            # max challenge poll iterations
    POST_CLOSE_WAIT       = 30            # seconds after closing browser
    HOMEPAGE_WARMUP_WAIT  = (3.0,  5.0)   # initial warmup page sleep
    WARMUP_STEP_WAIT_1    = (1.0,  2.5)   # warmup mid-step 1
    WARMUP_STEP_WAIT_2    = (1.5,  3.0)   # warmup mid-step 2
    HUMAN_SCROLLS_MINMAX  = (2, 4)        # scroll count range for human_scroll
    HUMAN_MOVE_PROB       = 1.0           # probability to call human_random_move
    MAX_CONCURRENT_CITIES = 2             # max simultaneous browser instances

TURNSTILE_WIDGET_WAIT = (6.0,  9.0)       # wait for Turnstile widget to be ready


def checkpoint_path(city_url_name: str) -> str:
    return os.path.join(SCRIPT_DIR, f"scraper_checkpoint_{city_url_name}.json")


# ============================================================
# CHECKPOINT SYSTEM
# ============================================================

def load_checkpoint(city_url_name):
    path = checkpoint_path(city_url_name)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            print(f"📌 Checkpoint yüklendi → şehir: {data.get('city')}, "
                  f"bracket: {data.get('bracket_index')}, sayfa: {data.get('page_num')}")
            return data
        except Exception as e:
            print(f"⚠️ Checkpoint okunamadı, sıfırdan başlanıyor: {e}")
    return {}


def save_checkpoint(city_url_name, bracket_index, page_num):
    """CSV'ye yazıldıktan SONRA çağrılır — veri kaybını önler."""
    data = {
        "city":          city_url_name,
        "bracket_index": bracket_index,
        "page_num":      page_num,
        "saved_at":      datetime.now().isoformat(),
    }
    try:
        with open(checkpoint_path(city_url_name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Checkpoint yazılamadı: {e}")


def clear_checkpoint(city_url_name):
    path = checkpoint_path(city_url_name)
    if os.path.isfile(path):
        os.remove(path)
        print(f"🗑️ Checkpoint temizlendi ({city_url_name}).")


def get_resume_point(checkpoint, city_url_name):
    if checkpoint.get("city") == city_url_name:
        return checkpoint.get("bracket_index", 0), checkpoint.get("page_num", 1)
    return 0, 1


# ============================================================
# BROWSER LIFECYCLE
# ============================================================

class BrowserBlockedError(Exception):
    pass


async def close_and_wait(label, reason="normal"):
    if reason == "engel":
        print(f"🚫 {label} tarayıcısı engel nedeniyle kapatıldı — temizlendi.")
    else:
        print(f"🧹 {label} tarayıcısı kapatıldı — çerezler ve oturum temizlendi.")
    print(f"⏳ Sonraki açılış için {POST_CLOSE_WAIT} saniye bekleniyor...")
    await asyncio.sleep(POST_CLOSE_WAIT)


# ============================================================
# SES UYARISI — sadece Windows'ta çalışır, Linux'ta sessiz
# ============================================================

async def beep_alert():
    def _beep():
        try:
            import winsound
            import time
            for sound in ["SystemExclamation", "SystemHand", "SystemExclamation"]:
                try:
                    winsound.PlaySound(sound, winsound.SND_ALIAS | winsound.SND_SYNC)
                    time.sleep(0.3)
                except Exception:
                    try:
                        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                        time.sleep(0.3)
                    except Exception:
                        pass
        except Exception:
            print("\a\a\a")
    await asyncio.to_thread(_beep)


# ============================================================
# PAGE CONTENT HELPER
# ============================================================

async def get_page_content(page, timeout=10_000):
    """Navigasyon bitmeden page.content() çağrısını önler."""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass
    try:
        return await page.content()
    except Exception:
        await asyncio.sleep(3)
        return await page.content()


# ============================================================
# İNSANSI DAVRANIŞLAR
# ============================================================

async def human_scroll(page, scrolls=3):
    """Sayfayı rastgele miktarda, rastgele aralıklarla aşağı kaydırır."""
    for _ in range(scrolls):
        amount = random.randint(200, 600)
        await page.mouse.wheel(0, amount)
        await asyncio.sleep(random.uniform(0.4, 1.2))


async def human_random_move(page):
    """Ekranın rastgele bir noktasına mouse'u hareket ettirir."""
    x = random.randint(200, 1000)
    y = random.randint(150, 600)
    await page.mouse.move(x, y)
    await asyncio.sleep(random.uniform(0.2, 0.6))


async def maybe_human_move(page, prob=HUMAN_MOVE_PROB):
    """Calls human_random_move with probability `prob` to reduce overhead in fast mode."""
    if random.random() < prob:
        await human_random_move(page)


async def warmup_homepage(page):
    """
    Sahibinden ana sayfasına gider, insan gibi davranır, sonra döner.

    Doğrudan bracket URL'ine gitmek yerine önce ana sayfayı ziyaret etmek:
    - Cloudflare'ın behavioral analysis'ine gerçek kullanıcı gibi görünür
    - cf_clearance cookie'sini ana sayfada alarak arama sayfalarında
      doğrulama çıkma ihtimalini azaltır
    - Referrer header'ı doğal görünür (sahibinden.com içinden geziyor)
    """
    print("🏠 Ana sayfa ısınma turu başlıyor...")
    try:
        await page.goto("https://www.sahibinden.com", wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(random.uniform(*HOMEPAGE_WARMUP_WAIT))

        # Ana sayfada da managed challenge çıkabilir
        if is_managed_challenge(page):
            print("🛡️ Ana sayfada Managed Challenge — otomatik çözülmesi bekleniyor...")
            await wait_for_challenge(page)

        html = await handle_browser_check(page)

        # Ana sayfada insan gibi davran
        await human_scroll(page, scrolls=random.randint(*HUMAN_SCROLLS_MINMAX))
        await asyncio.sleep(random.uniform(*WARMUP_STEP_WAIT_1))
        await human_random_move(page)
        await asyncio.sleep(random.uniform(*WARMUP_STEP_WAIT_2))
        await human_random_move(page)

        print("✅ Ana sayfa ısınma turu tamamlandı.")
    except BrowserBlockedError:
        # Ana sayfa da engellenirse devam et — scrape denenecek
        print("⚠️ Ana sayfa ısınmasında engel, scrape'e devam ediliyor...")
    except Exception as e:
        print(f"⚠️ Ana sayfa ısınma hatası (önemsiz): {e}")


# ============================================================
# OTOMATİK TURNSTİLE BYPASS
# ============================================================

async def try_auto_turnstile(page):
    """
    Cloudflare Turnstile checkbox'ını otomatik olarak tıklamayı dener.

    Yaklaşım: Sayfadaki tüm frame'leri tara, challenges.cloudflare.com
    URL'ine sahip olanı bul, bounding box'tan checkbox koordinatını
    hesapla, humanize=True ile insan gibi tıkla.

    Başarılı olursa True, başarısız olursa False döner.
    False durumunda handle_browser_check() manuel beklemeye geçer.
    """
    print("   🤖 Otomatik Turnstile bypass deneniyor...")
    try:
        # Iframe'in yüklenmesi için bekle
        for _ in range(10):
            await asyncio.sleep(random.uniform(*TURNSTILE_IFRAME))
            for frame in page.frames:
                if frame.url.startswith("https://challenges.cloudflare.com"):
                    frame_element  = await frame.frame_element()
                    bounding_box   = frame_element.bounding_box()
                    if not bounding_box:
                        continue

                    # Checkbox iframe içinde sol-orta konumda
                    checkbox_x = bounding_box["x"] + bounding_box["width"] / 9
                    checkbox_y = bounding_box["y"] + bounding_box["height"] / 2

                    # humanize=True sayesinde hareket eğri yoldan gider
                    await page.mouse.click(checkbox_x, checkbox_y)
                    print(f"   ✅ Turnstile checkbox'ına tıklandı "
                          f"({checkbox_x:.0f}, {checkbox_y:.0f})")

                    # Doğrulamanın işlenmesini bekle
                    await asyncio.sleep(random.uniform(3.5, 6.0))
                    return True

        print("   ℹ️ Cloudflare iframe bulunamadı (otomatik bypass atlandı).")
        return False
    except Exception as e:
        print(f"   ⚠️ Otomatik bypass hatası: {e}")
        return False


# ============================================================
# PROTECTION HANDLERS
# ============================================================

async def handle_browser_check(page):
    """
    Sahibinden'in Cloudflare Turnstile sayfasını geçer.

    1. Önce otomatik bypass dener (iframe koordinat tıklaması)
    2. Otomatik başarısız olursa 'Devam Et' butonunu bekler
    3. O da başarısız olursa BrowserBlockedError fırlatır
    """
    html = await get_page_content(page)
    lower = html.lower()
    is_check_page = (
        "tarayıcınızı kontrol ediyoruz" in lower
        or ("güvenlik doğrulaması" in lower and "cf-turnstile" in lower)
        or is_managed_challenge(page)
    )
    if not is_check_page:
        return html

    print("🤖 Cloudflare koruma sayfası tespit edildi...")
    await beep_alert()

    # Adım 1: Otomatik bypass dene
    auto_success = await try_auto_turnstile(page)

    if auto_success:
        # Bypass sonrası sayfanın tam yüklenmesini bekle
        try:
            await page.wait_for_function(
                "() => !document.body.innerText.toLowerCase()"
                ".includes('tarayıcınızı kontrol ediyoruz')",
                timeout=20_000,
            )
            await asyncio.sleep(random.uniform(4.0, 6.0))
            html = await get_page_content(page)
            if "tarayıcınızı kontrol ediyoruz" not in html.lower():
                print("✅ Otomatik Turnstile bypass başarılı!")
                return html
        except Exception:
            pass
        print("   ⚠️ Otomatik bypass sonrası hâlâ check sayfasında, fallback'e geçiliyor...")

    # Adım 2: Devam Et butonunu bekle (yarı-manuel)
    print("   ⏳ 'Devam Et' butonu bekleniyor (Turnstile token shadow DOM)...")
    try:
        await page.wait_for_selector("#turnStileWidget", timeout=25_000)
        await asyncio.sleep(random.uniform(*TURNSTILE_WIDGET_WAIT))
        await page.wait_for_selector("#btn-continue", timeout=15_000)
        await page.click("#btn-continue")
        print("✅ 'Devam Et' butonuna tıklandı.")
        await page.wait_for_function(
            "() => !document.body.innerText.toLowerCase()"
            ".includes('tarayıcınızı kontrol ediyoruz')",
            timeout=25_000,
        )
        await asyncio.sleep(random.uniform(4.0, 6.0))
        return await get_page_content(page)
    except Exception as e:
        raise BrowserBlockedError(f"Turnstile geçilemedi: {e}") from e


def is_managed_challenge(page):
    """
    sahibinden.com/cs/checkLoading sayfasını tespit eder.
    URL: www.sahibinden.com/cs/checkLoading veya secure.sahibinden.com
    HTML incelemesinden: cf-turnstile + güvenlik doğrulaması içerir.
    """
    try:
        url = page.url.lower()
        if "/cs/checkloading" in url or "secure.sahibinden.com" in url:
            return True
        # HTML yedek kontrol
        html = page.content()
        lower = html.lower()
        return "güvenlik doğrulaması" in lower and "cf-turnstile" in lower
    except Exception:
        return False


def is_waiting_page(html):
    lower = html.lower()
    return any(s in lower for s in [
        "bir dakika lütfen",
        "lütfen bekleyiniz",
        "doğrulanıyor",           # Managed challenge widget metni
        "güvenlik doğrulaması",   # Managed challenge başlık metni
    ])


def is_login_page(html):
    """Eşik 2 — footer'daki tek 'giriş yap' yanlış pozitif vermesin."""
    lower = html.lower()
    signals = ["giriş yap", "üye girişi", "captcha", "güvenlik doğrulama", "robot olmadığınızı"]
    return sum(1 for s in signals if s in lower) >= 2 and "searchresultstable" not in lower


async def try_click_managed_challenge(page):
    """
    www.sahibinden.com/cs/checkLoading sayfasındaki Turnstile
    checkbox'ına insan gibi tıklamayı dener.

    HTML incelemesinden öğrenilenler:
    - Widget iframe'siz, DOM'a inject ediliyor (div#AOzYg6 gibi)
    - Turnstile JS sonradan challenges.cloudflare.com iframe'i yaratır
    - Container: input[name="cf-turnstile-response"] içeren div

    Tıklama stratejileri (sırayla):
    1. Turnstile JS'in iframe inject etmesi için 4-6s bekle
    2. challenges.cloudflare.com iframe'i bul → checkbox koordinatına tıkla
    3. input[name="cf-turnstile-response"] container'ına göre tıkla
    4. Viewport'un sol-orta kısmına fallback tıklama
    """
    print("   🖱️ Turnstile checkbox'ına tıklanmaya çalışılıyor...")

    # Turnstile JS'in iframe'i inject etmesi için bekle
    await asyncio.sleep(random.uniform(4.0, 6.0))
    await human_random_move(page)
    await asyncio.sleep(random.uniform(1.0, 2.0))
    await human_random_move(page)
    await asyncio.sleep(random.uniform(0.5, 1.5))

    # Strateji 1: challenges.cloudflare.com iframe (Turnstile JS inject eder)
    try:
        for frame in page.frames:
            if "challenges.cloudflare.com" in frame.url:
                frame_el = await frame.frame_element()
                bb = frame_el.bounding_box()
                if bb:
                    cx = bb["x"] + bb["width"] * 0.1
                    cy = bb["y"] + bb["height"] * 0.5
                    await page.mouse.move(cx, cy)
                    await asyncio.sleep(random.uniform(0.4, 0.8))
                    await page.mouse.click(cx, cy)
                    print(f"   ✅ Cloudflare iframe checkbox'ına tıklandı ({cx:.0f}, {cy:.0f})")
                    await asyncio.sleep(random.uniform(3.0, 5.0))
                    return True
    except Exception as e:
        print(f"   ⚠️ iframe stratejisi hatası: {e}")

    # Strateji 2: input[name="cf-turnstile-response"] container'ına tıkla
    try:
        el = await page.query_selector("input[name='cf-turnstile-response']")
        if el:
            bb = el.bounding_box()
            if bb:
                # Checkbox input'un solunda ~40px
                cx = max(bb["x"] - 40, 10)
                cy = bb["y"] + bb["height"] * 0.5
                await page.mouse.move(cx, cy)
                await asyncio.sleep(random.uniform(0.4, 0.8))
                await page.mouse.click(cx, cy)
                print(f"   ✅ Turnstile container'ına tıklandı ({cx:.0f}, {cy:.0f})")
                await asyncio.sleep(random.uniform(3.0, 5.0))
                return True
    except Exception as e:
        print(f"   ⚠️ Container stratejisi hatası: {e}")

    # Strateji 3: Viewport fallback — widget genellikle sol-orta bölgede
    try:
        vp = page.viewport_size or {"width": 1280, "height": 720}
        cx = vp["width"]  * 0.36
        cy = vp["height"] * 0.37
        await page.mouse.move(cx, cy)
        await asyncio.sleep(random.uniform(0.4, 0.8))
        await page.mouse.click(cx, cy)
        print(f"   🖱️ Fallback viewport tıklaması ({cx:.0f}, {cy:.0f})")
        await asyncio.sleep(random.uniform(3.0, 5.0))
        return True
    except Exception as e:
        print(f"   ⚠️ Fallback tıklama hatası: {e}")

    return False


async def wait_for_challenge(page, iterations=CHALLENGE_RETRIES):
    """
    Cloudflare challenge sayfalarını bekler ve geçmeye çalışır.

    Sıra:
    1. İnsan gibi bekle + mouse gezdirme
    2. Widget'a tıklamayı dene (managed challenge için)
    3. Her iterasyonda URL + HTML kontrolü — geçildi mi?
    4. Tüm iterasyonlar dolunca başarısız döner
    """
    print(f"⏳ Challenge sayfasının çözülmesi bekleniyor ({iterations} kontrol)...")

    # İlk tıklama denemesi — hemen değil, biraz bekledikten sonra
    if is_managed_challenge(page):
        await try_click_managed_challenge(page)

    for i in range(iterations):
        await asyncio.sleep(random.uniform(*CHALLENGE_WAIT))

        # Hâlâ managed challenge sayfasındaysa tekrar tıklamayı dene
        if is_managed_challenge(page):
            print(f"   [{i+1}/{iterations}] Hâlâ challenge sayfasında...")
            # Her 3 iterasyonda bir tekrar tıkla
            if i % 3 == 2:
                await try_click_managed_challenge(page)
            # Arada insan gibi davran
            await human_random_move(page)
            continue

        html = await get_page_content(page)
        if not is_waiting_page(html):
            print(f"✅ Challenge {i + 1}. kontrolde geçildi.")
            return html

    print("⏰ Challenge geçilemedi.")
    return None


async def wait_for_listings(page, timeout=20_000):
    try:
        await page.wait_for_selector(
            "#searchResultsTable tbody tr.searchResultsItem",
            timeout=timeout,
        )
        return True
    except Exception:
        return False


async def goto_with_retry(page, url, retries=3, timeout=60_000):
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return
        except Exception as e:
            if "timeout" in str(e).lower():
                print(f"   ⏱️ page.goto timeout (deneme {attempt}/{retries})")
                if attempt < retries:
                    wait = random.uniform(8.0, 12.0)
                    print(f"   {wait:.1f}s bekleniyor...")
                    await asyncio.sleep(wait)
                else:
                    raise BrowserBlockedError(f"Kalıcı goto timeout: {url}") from e
            else:
                raise BrowserBlockedError(f"goto hatası: {e}") from e


async def safe_goto(page, url):
    """Sahibinden'in tüm koruma katmanlarını yöneterek URL'ye gider."""
    await goto_with_retry(page, url)
    await asyncio.sleep(random.uniform(*NAV_WAIT))

    # Managed Challenge kontrolü — secure.sahibinden.com/cs/checkLoading
    # Bu sayfa otomatik çözülür, sadece redirect'i bekliyoruz
    if is_managed_challenge(page):
        print("🛡️ Cloudflare Managed Challenge tespit edildi — otomatik çözülmesi bekleniyor...")
        await beep_alert()
        result = await wait_for_challenge(page)
        if result is None:
            raise BrowserBlockedError(f"Managed challenge çözülmedi: {url}")
        print("✅ Managed Challenge geçildi, devam ediliyor.")

    # Sayfaya girdikten sonra kısa insan davranışı
    await maybe_human_move(page)

    html = await handle_browser_check(page)

    if is_login_page(html):
        print("🔄 Login sayfasına yönlendirildi, tekrar deneniyor...")
        await asyncio.sleep(random.uniform(5, 8))
        await goto_with_retry(page, url)
        await asyncio.sleep(random.uniform(*NAV_WAIT))
        html = await handle_browser_check(page)

    if is_waiting_page(html):
        result = await wait_for_challenge(page)
        if result is not None:
            html = result
            html = await handle_browser_check(page) or html
        else:
            print("🔄 Challenge takılı kaldı, tekrar yükleniyor...")
            await goto_with_retry(page, url)
            await asyncio.sleep(random.uniform(*NAV_WAIT))
            html = await handle_browser_check(page)
            if is_waiting_page(html):
                result = await wait_for_challenge(page)
                if result is not None:
                    html = result

    if is_login_page(html):
        print("🔄 Login/CAPTCHA sayfası, tekrar deneniyor...")
        await asyncio.sleep(random.uniform(5, 8))
        await goto_with_retry(page, url)
        await asyncio.sleep(random.uniform(*NAV_WAIT))
        html = await handle_browser_check(page)

        if is_waiting_page(html):
            result = await wait_for_challenge(page)
            if result is not None:
                html = result

        if is_login_page(html):
            raise BrowserBlockedError(f"Kalıcı engel: {url}")

    await wait_for_listings(page)
    return True


# ============================================================
# PRICE NORMALIZATION
# ============================================================

def normalize_price(price_text):
    if not price_text or price_text == "N/A":
        return None
    cleaned = price_text.lower().replace("tl", "").replace("₺", "").strip()
    cleaned = re.sub(r"[^\d,.]", "", cleaned)
    if not cleaned:
        return None
    if "." in cleaned and "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 1 and all(p.isdigit() for p in parts):
            if all(len(p) == 3 for p in parts[1:]):
                cleaned = "".join(parts)
    try:
        return float(cleaned)
    except ValueError:
        return None


# ============================================================
# ROOMS HELPERS
# ============================================================

def resolve_rooms_index(soup):
    headers = [
        th.get_text(strip=True)
        for th in soup.select("#searchResultsTable thead th.searchResultsAttributeHeader")
    ]
    for idx, header in enumerate(headers):
        if "oda" in header.lower().replace("ı", "i"):
            return idx
    return None


def extract_rooms(attributes, room_index):
    if room_index is not None and len(attributes) > room_index:
        return attributes[room_index].text.strip()
    if len(attributes) > 1:
        return attributes[1].text.strip()
    if len(attributes) == 1:
        return attributes[0].text.strip()
    return "N/A"


# ============================================================
# CSV HELPER
# ============================================================

def save_to_csv_incremental(folder_name, data_batch):
    today_str  = datetime.now().strftime("%Y-%m-%d")
    target_dir = os.path.join(DATA_BASE_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)
    file_path  = os.path.join(target_dir, f"{today_str}.csv")

    file_exists = os.path.isfile(file_path)
    with open(file_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["District", "Rooms", "Price"])
        if not file_exists:
            writer.writeheader()
        writer.writerows(data_batch)

    print(f"   💾 {len(data_batch)} kayıt eklendi → {file_path}")


# ============================================================
# CORE SCRAPE
# ============================================================

async def scrape_city_brackets(page, city_url_name, folder_name, brackets,
                              start_bracket=0, start_page=1):
    total_saved = 0

    for bracket_index, (min_price, max_price) in enumerate(brackets):

        if bracket_index < start_bracket:
            print(f"   ⏭️ Bracket {min_price}-{max_price} TL daha önce tamamlandı, atlanıyor.")
            continue

        print(f"\n🔍 Bracket {min_price}-{max_price} TL taranıyor...")

        if bracket_index > start_bracket:
            wait = random.uniform(*BRACKET_BREAK)
            print(f"   😮‍💨 Bracket molası: {wait:.1f}s")
            await asyncio.sleep(wait)
            await maybe_human_move(page)

        page_num    = start_page if bracket_index == start_bracket else 1
        current_url = (
            f"https://www.sahibinden.com/kiralik/{city_url_name}"
            f"?pagingSize=50&price_min={min_price}&price_max={max_price}"
        )

        if page_num > 1:
            current_url += f"&pagingOffset={(page_num - 1) * 50}"
            print(f"   📌 Checkpoint'ten devam: sayfa {page_num}")

        while True:
            await safe_goto(page, current_url)

            # Sayfa yüklendi — insan gibi davran
            await maybe_human_move(page)
            await human_scroll(page, scrolls=random.randint(*HUMAN_SCROLLS_MINMAX))
            await maybe_human_move(page)

            html     = await get_page_content(page)
            soup     = BeautifulSoup(html, "html.parser")
            listings = soup.select("#searchResultsTable tbody tr.searchResultsItem")

            if not listings:
                html_lower = html.lower()
                if "ilan bulunamadı" in html_lower or "bulunamamıştır" in html_lower:
                    print(f"   Bu bracket'ta ilan yok.")
                else:
                    print(f"   Sayfa {page_num}'de ilan bulunamadı, bracket tamamlandı.")
                break

            room_index = resolve_rooms_index(soup)
            batch = []

            for row in listings:
                try:
                    price_elem = row.select_one(".searchResultsPriceValue")
                    price      = normalize_price(price_elem.text.strip() if price_elem else None)

                    location_elem = row.select_one(".searchResultsLocationValue")
                    district = " / ".join(location_elem.stripped_strings) if location_elem else "N/A"

                    attributes = row.select(".searchResultsAttributeValue")
                    rooms      = extract_rooms(attributes, room_index)

                    if price is not None and district != "N/A":
                        batch.append({"District": district, "Rooms": rooms, "Price": price})
                except Exception as e:
                    print(f"   ⚠️ Satır parse hatası: {e}")
                    continue

            if batch:
                save_to_csv_incremental(folder_name, batch)
                total_saved += len(batch)
                print(f"   ✔ Sayfa {page_num}: {len(batch)} kayıt yazıldı (toplam: {total_saved})")
            else:
                print(f"   ⚠️ Sayfa {page_num}: parse edilebilir kayıt yok.")

            # CSV'ye yazıldıktan SONRA checkpoint güncelle
            save_checkpoint(city_url_name, bracket_index, page_num)

            next_button = soup.find("a", title="Sonraki")
            if next_button and "href" in next_button.attrs:
                current_url = "https://www.sahibinden.com" + next_button["href"]
                page_num   += 1
                # Sayfa geçişi öncesi: insan gibi gez, sıkılmış gibi bekle
                await maybe_human_move(page)
                await asyncio.sleep(random.uniform(*PAGE_PAUSE))
                await maybe_human_move(page)
            else:
                print(f"   Son sayfa — bracket {min_price}-{max_price} TL tamamlandı.")
                break

    return total_saved


# ============================================================
# PER-CITY SCRAPE
# ============================================================

async def scrape_city(city_url_name, city_data, checkpoint):
    """
    Her şehir için bağımsız Camoufox örneği başlatır.

    Turnstile için:
      1. Önce otomatik iframe koordinat tıklaması dener
      2. Başarısız olursa #btn-continue butonunu bekler

    Her şehir açılışında önce ana sayfaya gidip "ısınma turu" yapılır.
    """
    folder_name  = city_data["folder"]
    brackets     = city_data["brackets"]
    max_restarts = 3

    start_bracket, start_page = get_resume_point(checkpoint, city_url_name)
    if start_bracket > 0 or start_page > 1:
        print(f"📌 {folder_name} için checkpoint: bracket {start_bracket}, sayfa {start_page}")

    for attempt in range(1, max_restarts + 1):
        print(f"\n{'=' * 50}")
        print(f"ŞEHİR: {folder_name.upper()} — clean slate tarayıcı başlatılıyor 🧹"
              + (f" (deneme {attempt}/{max_restarts})" if attempt > 1 else ""))
        print(f"{'=' * 50}")

        try:
            async with AsyncCamoufox(
                headless=False,
                humanize=True,
                disable_coop=True,
                i_know_what_im_doing=True,
                os="windows",
                locale="tr-TR",
            ) as browser:
                page = await browser.new_page()

                # Ana sayfa ısınma turu — Cloudflare trust score'unu artırır
                await warmup_homepage(page)
                await asyncio.sleep(random.uniform(3.0, 5.0))

                total = await scrape_city_brackets(
                    page, city_url_name, folder_name, brackets,
                    start_bracket=start_bracket,
                    start_page=start_page,
                )
                print(f"\n✅ {folder_name} tamamlandı — toplam {total} kayıt kaydedildi.")

            await close_and_wait(folder_name, reason="normal")
            break

        except BrowserBlockedError as e:
            print(f"   Engel detayı: {e}")
            start_bracket, start_page = get_resume_point(
                load_checkpoint(city_url_name), city_url_name
            )
            if attempt < max_restarts:
                print(f"🔄 Yeniden başlatılıyor (deneme {attempt + 1}/{max_restarts})...")
                await close_and_wait(folder_name, reason="engel")
            else:
                print(f"❌ {max_restarts} denemeden sonra {folder_name} atlandı.")
                await close_and_wait(folder_name, reason="engel")


# ============================================================
# MAIN
# ============================================================

async def main():
    city_list = list(CITIES.items())
    semaphore = asyncio.Semaphore(min(MAX_CONCURRENT_CITIES, len(city_list)))

    async def run_city(city_url_name, city_data):
        async with semaphore:
            checkpoint = load_checkpoint(city_url_name)
            await scrape_city(city_url_name, city_data, checkpoint)
            clear_checkpoint(city_url_name)

    await asyncio.gather(*(run_city(city, data) for city, data in city_list))
    print("\n✅ Tüm şehirler tamamlandı (asenkron).")


if __name__ == "__main__":
    asyncio.run(main())