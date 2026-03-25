import os
import csv
import re
import json
import time
import random
from datetime import datetime
from bs4 import BeautifulSoup
from camoufox.sync_api import Camoufox

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

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
DATA_BASE_DIR   = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../Datas/HousesRent/"))
CHECKPOINT_FILE = os.path.join(SCRIPT_DIR, "scraper_checkpoint.json")


# ============================================================
# CHECKPOINT SYSTEM
# ============================================================

def load_checkpoint():
    if os.path.isfile(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, encoding="utf-8") as f:
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
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Checkpoint yazılamadı: {e}")


def clear_checkpoint():
    if os.path.isfile(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("🗑️ Checkpoint temizlendi.")


def get_resume_point(checkpoint, city_url_name):
    if checkpoint.get("city") == city_url_name:
        return checkpoint.get("bracket_index", 0), checkpoint.get("page_num", 1)
    return 0, 1


# ============================================================
# BROWSER LIFECYCLE
# ============================================================

class BrowserBlockedError(Exception):
    pass


def close_and_wait(label, reason="normal"):
    if reason == "engel":
        print(f"🚫 {label} tarayıcısı engel nedeniyle kapatıldı — temizlendi.")
    else:
        print(f"🧹 {label} tarayıcısı kapatıldı — çerezler ve oturum temizlendi.")
    print("⏳ Sonraki açılış için 30 saniye bekleniyor...")
    time.sleep(30)


# ============================================================
# SES UYARISI — sadece Windows'ta çalışır, Linux'ta sessiz
# ============================================================

def beep_alert():
    try:
        import winsound
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


# ============================================================
# PAGE CONTENT HELPER
# ============================================================

def get_page_content(page, timeout=10_000):
    """Navigasyon bitmeden page.content() çağrısını önler."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass
    try:
        return page.content()
    except Exception:
        time.sleep(3)
        return page.content()


# ============================================================
# İNSANSI DAVRANIŞLAR
# ============================================================

def human_scroll(page, scrolls=3):
    """Sayfayı rastgele miktarda, rastgele aralıklarla aşağı kaydırır."""
    for _ in range(scrolls):
        amount = random.randint(200, 600)
        page.mouse.wheel(0, amount)
        time.sleep(random.uniform(0.4, 1.2))


def human_random_move(page):
    """Ekranın rastgele bir noktasına mouse'u hareket ettirir."""
    x = random.randint(200, 1000)
    y = random.randint(150, 600)
    page.mouse.move(x, y)
    time.sleep(random.uniform(0.2, 0.6))


def warmup_homepage(page):
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
        page.goto("https://www.sahibinden.com", wait_until="domcontentloaded", timeout=60_000)
        time.sleep(random.uniform(3.0, 5.0))

        # Ana sayfada da managed challenge çıkabilir
        if is_managed_challenge(page):
            print("🛡️ Ana sayfada Managed Challenge — otomatik çözülmesi bekleniyor...")
            wait_for_challenge(page)

        html = handle_browser_check(page)

        # Ana sayfada insan gibi davran
        human_scroll(page, scrolls=random.randint(2, 4))
        time.sleep(random.uniform(1.0, 2.5))
        human_random_move(page)
        time.sleep(random.uniform(1.5, 3.0))
        human_random_move(page)

        print("✅ Ana sayfa ısınma turu tamamlandı.")
    except BrowserBlockedError:
        # Ana sayfa da engellenirse devam et — scrape denenecek
        print("⚠️ Ana sayfa ısınmasında engel, scrape'e devam ediliyor...")
    except Exception as e:
        print(f"⚠️ Ana sayfa ısınma hatası (önemsiz): {e}")


# ============================================================
# OTOMATİK TURNSTİLE BYPASS
# ============================================================

def try_auto_turnstile(page):
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
        for _ in range(15):
            time.sleep(1)
            for frame in page.frames:
                if frame.url.startswith("https://challenges.cloudflare.com"):
                    frame_element  = frame.frame_element()
                    bounding_box   = frame_element.bounding_box()
                    if not bounding_box:
                        continue

                    # Checkbox iframe içinde sol-orta konumda
                    checkbox_x = bounding_box["x"] + bounding_box["width"] / 9
                    checkbox_y = bounding_box["y"] + bounding_box["height"] / 2

                    # humanize=True sayesinde hareket eğri yoldan gider
                    page.mouse.click(checkbox_x, checkbox_y)
                    print(f"   ✅ Turnstile checkbox'ına tıklandı "
                          f"({checkbox_x:.0f}, {checkbox_y:.0f})")

                    # Doğrulamanın işlenmesini bekle
                    time.sleep(random.uniform(5.0, 8.0))
                    return True

        print("   ℹ️ Cloudflare iframe bulunamadı (otomatik bypass atlandı).")
        return False
    except Exception as e:
        print(f"   ⚠️ Otomatik bypass hatası: {e}")
        return False


# ============================================================
# PROTECTION HANDLERS
# ============================================================

def handle_browser_check(page):
    """
    Sahibinden'in Cloudflare Turnstile sayfasını geçer.

    1. Önce otomatik bypass dener (iframe koordinat tıklaması)
    2. Otomatik başarısız olursa 'Devam Et' butonunu bekler
    3. O da başarısız olursa BrowserBlockedError fırlatır
    """
    html = get_page_content(page)
    lower = html.lower()
    is_check_page = (
        "tarayıcınızı kontrol ediyoruz" in lower
        or ("güvenlik doğrulaması" in lower and "cf-turnstile" in lower)
        or is_managed_challenge(page)
    )
    if not is_check_page:
        return html

    print("🤖 Cloudflare koruma sayfası tespit edildi...")
    beep_alert()

    # Adım 1: Otomatik bypass dene
    auto_success = try_auto_turnstile(page)

    if auto_success:
        # Bypass sonrası sayfanın tam yüklenmesini bekle
        try:
            page.wait_for_function(
                "() => !document.body.innerText.toLowerCase()"
                ".includes('tarayıcınızı kontrol ediyoruz')",
                timeout=20_000,
            )
            time.sleep(random.uniform(4.0, 6.0))
            html = get_page_content(page)
            if "tarayıcınızı kontrol ediyoruz" not in html.lower():
                print("✅ Otomatik Turnstile bypass başarılı!")
                return html
        except Exception:
            pass
        print("   ⚠️ Otomatik bypass sonrası hâlâ check sayfasında, fallback'e geçiliyor...")

    # Adım 2: Devam Et butonunu bekle (yarı-manuel)
    print("   ⏳ 'Devam Et' butonu bekleniyor (Turnstile token shadow DOM)...")
    try:
        page.wait_for_selector("#turnStileWidget", timeout=25_000)
        time.sleep(random.uniform(13.0, 17.0))
        page.wait_for_selector("#btn-continue", timeout=15_000)
        page.click("#btn-continue")
        print("✅ 'Devam Et' butonuna tıklandı.")
        page.wait_for_function(
            "() => !document.body.innerText.toLowerCase()"
            ".includes('tarayıcınızı kontrol ediyoruz')",
            timeout=25_000,
        )
        time.sleep(random.uniform(4.0, 6.0))
        return get_page_content(page)
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


def try_click_managed_challenge(page):
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
    time.sleep(random.uniform(4.0, 6.0))
    human_random_move(page)
    time.sleep(random.uniform(1.0, 2.0))
    human_random_move(page)
    time.sleep(random.uniform(0.5, 1.5))

    # Strateji 1: challenges.cloudflare.com iframe (Turnstile JS inject eder)
    try:
        for frame in page.frames:
            if "challenges.cloudflare.com" in frame.url:
                frame_el = frame.frame_element()
                bb = frame_el.bounding_box()
                if bb:
                    cx = bb["x"] + bb["width"] * 0.1
                    cy = bb["y"] + bb["height"] * 0.5
                    page.mouse.move(cx, cy)
                    time.sleep(random.uniform(0.4, 0.8))
                    page.mouse.click(cx, cy)
                    print(f"   ✅ Cloudflare iframe checkbox'ına tıklandı ({cx:.0f}, {cy:.0f})")
                    time.sleep(random.uniform(3.0, 5.0))
                    return True
    except Exception as e:
        print(f"   ⚠️ iframe stratejisi hatası: {e}")

    # Strateji 2: input[name="cf-turnstile-response"] container'ına tıkla
    try:
        el = page.query_selector("input[name='cf-turnstile-response']")
        if el:
            bb = el.bounding_box()
            if bb:
                # Checkbox input'un solunda ~40px
                cx = max(bb["x"] - 40, 10)
                cy = bb["y"] + bb["height"] * 0.5
                page.mouse.move(cx, cy)
                time.sleep(random.uniform(0.4, 0.8))
                page.mouse.click(cx, cy)
                print(f"   ✅ Turnstile container'ına tıklandı ({cx:.0f}, {cy:.0f})")
                time.sleep(random.uniform(3.0, 5.0))
                return True
    except Exception as e:
        print(f"   ⚠️ Container stratejisi hatası: {e}")

    # Strateji 3: Viewport fallback — widget genellikle sol-orta bölgede
    try:
        vp = page.viewport_size or {"width": 1280, "height": 720}
        cx = vp["width"]  * 0.36
        cy = vp["height"] * 0.37
        page.mouse.move(cx, cy)
        time.sleep(random.uniform(0.4, 0.8))
        page.mouse.click(cx, cy)
        print(f"   🖱️ Fallback viewport tıklaması ({cx:.0f}, {cy:.0f})")
        time.sleep(random.uniform(3.0, 5.0))
        return True
    except Exception as e:
        print(f"   ⚠️ Fallback tıklama hatası: {e}")

    return False


def wait_for_challenge(page, iterations=15):
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
        try_click_managed_challenge(page)

    for i in range(iterations):
        time.sleep(random.uniform(8.0, 11.0))

        # Hâlâ managed challenge sayfasındaysa tekrar tıklamayı dene
        if is_managed_challenge(page):
            print(f"   [{i+1}/{iterations}] Hâlâ challenge sayfasında...")
            # Her 3 iterasyonda bir tekrar tıkla
            if i % 3 == 2:
                try_click_managed_challenge(page)
            # Arada insan gibi davran
            human_random_move(page)
            continue

        html = get_page_content(page)
        if not is_waiting_page(html):
            print(f"✅ Challenge {i + 1}. kontrolde geçildi.")
            return html

    print("⏰ Challenge geçilemedi.")
    return None


def wait_for_listings(page, timeout=20_000):
    try:
        page.wait_for_selector(
            "#searchResultsTable tbody tr.searchResultsItem",
            timeout=timeout,
        )
        return True
    except Exception:
        return False


def goto_with_retry(page, url, retries=3, timeout=60_000):
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return
        except Exception as e:
            if "timeout" in str(e).lower():
                print(f"   ⏱️ page.goto timeout (deneme {attempt}/{retries})")
                if attempt < retries:
                    wait = random.uniform(13.0, 18.0)
                    print(f"   {wait:.1f}s bekleniyor...")
                    time.sleep(wait)
                else:
                    raise BrowserBlockedError(f"Kalıcı goto timeout: {url}") from e
            else:
                raise BrowserBlockedError(f"goto hatası: {e}") from e


def safe_goto(page, url):
    """Sahibinden'in tüm koruma katmanlarını yöneterek URL'ye gider."""
    goto_with_retry(page, url)
    time.sleep(random.uniform(8.0, 12.0))

    # Managed Challenge kontrolü — secure.sahibinden.com/cs/checkLoading
    # Bu sayfa otomatik çözülür, sadece redirect'i bekliyoruz
    if is_managed_challenge(page):
        print("🛡️ Cloudflare Managed Challenge tespit edildi — otomatik çözülmesi bekleniyor...")
        beep_alert()
        result = wait_for_challenge(page)
        if result is None:
            raise BrowserBlockedError(f"Managed challenge çözülmedi: {url}")
        print("✅ Managed Challenge geçildi, devam ediliyor.")

    # Sayfaya girdikten sonra kısa insan davranışı
    human_random_move(page)

    html = handle_browser_check(page)

    if is_login_page(html):
        print("🔄 Login sayfasına yönlendirildi, tekrar deneniyor...")
        time.sleep(random.uniform(10, 15))
        goto_with_retry(page, url)
        time.sleep(random.uniform(8, 12))
        html = handle_browser_check(page)

    if is_waiting_page(html):
        result = wait_for_challenge(page)
        if result is not None:
            html = result
            html = handle_browser_check(page) or html
        else:
            print("🔄 Challenge takılı kaldı, tekrar yükleniyor...")
            goto_with_retry(page, url)
            time.sleep(random.uniform(8, 12))
            html = handle_browser_check(page)
            if is_waiting_page(html):
                result = wait_for_challenge(page)
                if result is not None:
                    html = result

    if is_login_page(html):
        print("🔄 Login/CAPTCHA sayfası, tekrar deneniyor...")
        time.sleep(random.uniform(8, 12))
        goto_with_retry(page, url)
        time.sleep(random.uniform(8, 12))
        html = handle_browser_check(page)

        if is_waiting_page(html):
            result = wait_for_challenge(page)
            if result is not None:
                html = result

        if is_login_page(html):
            raise BrowserBlockedError(f"Kalıcı engel: {url}")

    wait_for_listings(page)
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

def scrape_city_brackets(page, city_url_name, folder_name, brackets,
                         start_bracket=0, start_page=1):
    total_saved = 0

    for bracket_index, (min_price, max_price) in enumerate(brackets):

        if bracket_index < start_bracket:
            print(f"   ⏭️ Bracket {min_price}-{max_price} TL daha önce tamamlandı, atlanıyor.")
            continue

        print(f"\n🔍 Bracket {min_price}-{max_price} TL taranıyor...")

        if bracket_index > start_bracket:
            wait = random.uniform(4.0, 6.0)
            print(f"   😮‍💨 Bracket molası: {wait:.1f}s")
            time.sleep(wait)
            human_random_move(page)

        page_num    = start_page if bracket_index == start_bracket else 1
        current_url = (
            f"https://www.sahibinden.com/kiralik/{city_url_name}"
            f"?pagingSize=50&price_min={min_price}&price_max={max_price}"
        )

        if page_num > 1:
            current_url += f"&pagingOffset={(page_num - 1) * 50}"
            print(f"   📌 Checkpoint'ten devam: sayfa {page_num}")

        while True:
            safe_goto(page, current_url)

            # Sayfa yüklendi — insan gibi davran
            human_random_move(page)
            human_scroll(page, scrolls=random.randint(1, 3))
            human_random_move(page)

            html     = get_page_content(page)
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
                human_random_move(page)
                time.sleep(random.uniform(8.0, 12.0))
                human_random_move(page)
            else:
                print(f"   Son sayfa — bracket {min_price}-{max_price} TL tamamlandı.")
                break

    return total_saved


# ============================================================
# PER-CITY SCRAPE
# ============================================================

def scrape_city(city_url_name, city_data, checkpoint):
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
            with Camoufox(
                headless=False,
                humanize=True,
                disable_coop=True,
                i_know_what_im_doing=True,
                os="windows",
                locale="tr-TR",
            ) as browser:
                page = browser.new_page()

                # Ana sayfa ısınma turu — Cloudflare trust score'unu artırır
                warmup_homepage(page)
                time.sleep(random.uniform(3.0, 5.0))

                total = scrape_city_brackets(
                    page, city_url_name, folder_name, brackets,
                    start_bracket=start_bracket,
                    start_page=start_page,
                )
                print(f"\n✅ {folder_name} tamamlandı — toplam {total} kayıt kaydedildi.")

            close_and_wait(folder_name, reason="normal")
            break

        except BrowserBlockedError as e:
            print(f"   Engel detayı: {e}")
            start_bracket, start_page = get_resume_point(
                load_checkpoint(), city_url_name
            )
            if attempt < max_restarts:
                print(f"🔄 Yeniden başlatılıyor (deneme {attempt + 1}/{max_restarts})...")
                close_and_wait(folder_name, reason="engel")
            else:
                print(f"❌ {max_restarts} denemeden sonra {folder_name} atlandı.")
                close_and_wait(folder_name, reason="engel")


# ============================================================
# MAIN
# ============================================================

def main():
    checkpoint = load_checkpoint()
    city_list  = list(CITIES.items())

    start_city = checkpoint.get("city")
    start_idx  = 0
    if start_city:
        for i, (city_url_name, _) in enumerate(city_list):
            if city_url_name == start_city:
                start_idx = i
                break

    for city_url_name, city_data in city_list[start_idx:]:
        scrape_city(city_url_name, city_data, checkpoint)
        checkpoint = {}

    clear_checkpoint()
    print("\n✅ Tüm şehirler tamamlandı.")


if __name__ == "__main__":
    main()  