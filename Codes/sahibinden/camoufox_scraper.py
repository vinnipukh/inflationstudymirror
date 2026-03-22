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

# BUG FIX 5 — Üç şehir de aynı bracket'ları kullanıyor, tek yerde tanımla.
# Biri değiştirilince üçü birden değişir.
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
    """Checkpoint dosyası varsa yükle, yoksa boş dict döndür."""
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
    """Mevcut ilerlemeyi checkpoint dosyasına yaz.

    BUG FIX 4 — Önceki versiyonda checkpoint sayfa BAŞINDA yazılıyordu.
    Sayfa henüz çekilmemişken blok gelirse o sayfa "tamamlandı" sayılıp
    bir sonraki başlatmada atlanıyor, veri kaybı oluşuyordu.

    Artık checkpoint sayfa SONUNDA (CSV'ye yazıldıktan sonra) çağrılıyor.
    """
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
    """Tüm şehirler tamamlanınca checkpoint'i sil."""
    if os.path.isfile(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("🗑️ Checkpoint temizlendi.")


def get_resume_point(checkpoint, city_url_name):
    """Checkpoint'ten bu şehir için kaldığı yeri döndürür."""
    if checkpoint.get("city") == city_url_name:
        return checkpoint.get("bracket_index", 0), checkpoint.get("page_num", 1)
    return 0, 1


# ============================================================
# BROWSER LIFECYCLE
# ============================================================

class BrowserBlockedError(Exception):
    """safe_goto tüm denemelerde başarısız olunca fırlatılır."""
    pass


def close_and_wait(label, reason="normal"):
    """Tarayıcı kapatıldıktan sonra her zaman çağrılır — 30s sabit bekleme."""
    if reason == "engel":
        print(f"🚫 {label} tarayıcısı engel nedeniyle kapatıldı — temizlendi.")
    else:
        print(f"🧹 {label} tarayıcısı kapatıldı — çerezler ve oturum temizlendi.")
    print("⏳ Sonraki açılış için 30 saniye bekleniyor...")
    time.sleep(30)


# ============================================================
# SES UYARISI
# winsound.Beep() eski PC speaker (Beep.sys) kullanır — modern
# Windows'ta devre dışıdır. PlaySound + SND_ALIAS ses kartından çalar.
# ============================================================

def beep_alert():
    """Cloudflare doğrulama gelince sesli uyarı verir."""
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
        print("\a\a\a")  # Windows dışı


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
# PROTECTION HANDLERS
# ============================================================

def handle_browser_check(page):
    """
    Sahibinden'in Cloudflare Turnstile sayfasını geçer.

    BUG FIX 3 — Önceki versiyonda geçilemezse sadece print yapıp
    dönüyordu. safe_goto başarılı sanıyor, boş sayfa üzerinde
    devam ediyordu. Artık BrowserBlockedError fırlatıyor.

    REFACTOR 1 — get_page_content'in döndürdüğü HTML'i döndürüyor.
    safe_goto içinde tekrar get_page_content çağrısına gerek kalmıyor.
    """
    html = get_page_content(page)
    if "tarayıcınızı kontrol ediyoruz" not in html.lower():
        return html   # Turnstile yok, sayfanın HTML'ini döndür

    print("🤖 Browser check sayfası tespit edildi, Turnstile bekleniyor...")
    beep_alert()
    try:
        page.wait_for_selector("#turnStileWidget", timeout=25_000)
        print("   ⏳ Turnstile token bekleniyor (shadow DOM)...")
        time.sleep(random.uniform(13.0, 17.0))
        page.wait_for_selector("#btn-continue", timeout=15_000)
        page.click("#btn-continue")
        print("✅ 'Devam Et' butonuna tıklandı, sayfa geçişi bekleniyor...")
        page.wait_for_function(
            "() => !document.body.innerText.toLowerCase().includes('tarayıcınızı kontrol ediyoruz')",
            timeout=25_000,
        )
        time.sleep(random.uniform(4.0, 6.0))
        return get_page_content(page)   # Geçiş sonrası güncel HTML
    except Exception as e:
        raise BrowserBlockedError(f"Turnstile geçilemedi: {e}") from e


def is_waiting_page(html):
    lower = html.lower()
    return any(s in lower for s in ["bir dakika lütfen", "lütfen bekleyiniz"])


def is_login_page(html):
    """
    BUG FIX 2 — Önceki eşik sum >= 1'di. Sahibinden'in normal
    footer'ında "giriş yap" geçtiği için her sayfada yanlış
    pozitif veriyordu. Eşik 2'ye çıkarıldı.
    """
    lower = html.lower()
    signals = ["giriş yap", "üye girişi", "captcha", "güvenlik doğrulama", "robot olmadığınızı"]
    return sum(1 for s in signals if s in lower) >= 2 and "searchresultstable" not in lower


def wait_for_challenge(page, iterations=15):
    """
    BUG FIX 1 — Önceki versiyonda max_wait=30 (saniye) geçiliyordu
    ama aslında range(30//2)=15 iterasyon × 8-11s ≈ 120-165s bekliyordu.
    Parametre adı 'max_wait' yanıltıcıydı.

    Artık 'iterations' parametresi — kaç kez kontrol edeceğini açıkça belirtir.
    Her iterasyon 8-11s bekler → toplam max ~165s.
    """
    print(f"⏳ Challenge sayfasının çözülmesi bekleniyor ({iterations} kontrol × ~9s)...")
    for i in range(iterations):
        time.sleep(random.uniform(8.0, 11.0))
        html = get_page_content(page)
        if not is_waiting_page(html):
            print(f"✅ Challenge {i + 1}. kontrolde çözüldü.")
            return html   # Güncel HTML'i döndür
    print("⏰ Challenge çözülmedi.")
    return None   # Başarısız → çağıran None'a göre karar verir


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
    """page.goto() timeout hatalarına karşı retry ile sarar."""
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
                    print("   ❌ Tüm goto denemeleri tükendi — tarayıcı yeniden başlatılacak.")
                    raise BrowserBlockedError(f"Kalıcı goto timeout: {url}") from e
            else:
                raise BrowserBlockedError(f"goto hatası: {e}") from e


def safe_goto(page, url):
    """
    Sahibinden'in tüm koruma katmanlarını yöneterek URL'ye gider.

    REFACTOR 1 — handle_browser_check artık HTML döndürüyor.
    Önceden her adımda ayrı get_page_content çağrısı vardı (2x parse).
    Şimdi her fonksiyon döndürdüğü HTML'i bir sonrakine aktarıyor.
    """
    goto_with_retry(page, url)
    time.sleep(random.uniform(8.0, 12.0))

    html = handle_browser_check(page)   # HTML döndürüyor artık

    # Login / CAPTCHA duvarı
    if is_login_page(html):
        print("🔄 Login sayfasına yönlendirildi, tekrar deneniyor...")
        time.sleep(random.uniform(10, 15))
        goto_with_retry(page, url)
        time.sleep(random.uniform(8, 12))
        html = handle_browser_check(page)

    # Cloudflare kendi kendine çözülen waiting page
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

    # Son kontrol — hâlâ login/captcha sayfasındaysa yeniden dene
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
            print("❌ Yeniden denemeden sonra hâlâ engellendi — tarayıcı yeniden başlatılacak.")
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
    """Tablo başlığından 'Oda' sütununun indeksini dinamik bulur."""
    headers = [
        th.get_text(strip=True)
        for th in soup.select("#searchResultsTable thead th.searchResultsAttributeHeader")
    ]
    for idx, header in enumerate(headers):
        if "oda" in header.lower().replace("ı", "i"):
            return idx
    return None


def extract_rooms(attributes, room_index):
    """Oda bilgisini dinamik index veya fallback ile çeker."""
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
    """
    Tüm bracket + sayfalamaları dolaşır. Her sayfa anında CSV'ye yazılır.
    Checkpoint ile kaldığı bracket + sayfadan devam edebilir.
    """
    total_saved = 0

    for bracket_index, (min_price, max_price) in enumerate(brackets):

        # Checkpoint: tamamlanmış bracket'ları atla
        if bracket_index < start_bracket:
            print(f"   ⏭️ Bracket {min_price}-{max_price} TL daha önce tamamlandı, atlanıyor.")
            continue

        print(f"\n🔍 Bracket {min_price}-{max_price} TL taranıyor...")

        # Bracket arası nefes molası (ilk/devam bracket'ı hariç)
        if bracket_index > start_bracket:
            wait = random.uniform(4.0, 6.0)
            print(f"   😮‍💨 Bracket molası: {wait:.1f}s")
            time.sleep(wait)

        page_num    = start_page if bracket_index == start_bracket else 1
        current_url = (
            f"https://www.sahibinden.com/kiralik/{city_url_name}"
            f"?pagingSize=50&price_min={min_price}&price_max={max_price}"
        )

        # Checkpoint sayfasına doğru offset hesapla
        if page_num > 1:
            current_url += f"&pagingOffset={(page_num - 1) * 50}"
            print(f"   📌 Checkpoint'ten devam: sayfa {page_num}")

        while True:
            safe_goto(page, current_url)

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

            # BUG FIX 4 — Checkpoint'i sayfa BAŞINDA değil SONUNDA yaz.
            # CSV'ye yazıldıktan sonra işaretleme yapılınca veri kaybı olmaz.
            save_checkpoint(city_url_name, bracket_index, page_num)

            next_button = soup.find("a", title="Sonraki")
            if next_button and "href" in next_button.attrs:
                current_url = "https://www.sahibinden.com" + next_button["href"]
                page_num   += 1
                time.sleep(random.uniform(8.0, 12.0))
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

    REFACTOR 2 — Önceki versiyonda start_bracket/start_page hem
    fonksiyon başında hem BrowserBlockedError except'inde ayrı ayrı
    hesaplanıyordu. Artık get_resume_point() ile tek noktadan alınıyor.

    Camoufox parametreleri:
      humanize=True       → C++ tabanlı insan-benzeri mouse hareketi
      disable_coop=True   → Turnstile cross-origin iframe tıklaması
      os="windows"        → Windows fingerprint
      locale="tr-TR"      → Türkçe locale
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
                os="windows",
                locale="tr-TR",
            ) as browser:
                page  = browser.new_page()
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
            # Disk'teki güncel checkpoint'ten kaldığı yeri al
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

    # Checkpoint'teki şehirden öncekileri atla
    start_city = checkpoint.get("city")
    start_idx  = 0
    if start_city:
        for i, (city_url_name, _) in enumerate(city_list):
            if city_url_name == start_city:
                start_idx = i
                break

    for city_url_name, city_data in city_list[start_idx:]:
        scrape_city(city_url_name, city_data, checkpoint)
        checkpoint = {}   # Sonraki şehir baştan başlar

    clear_checkpoint()
    print("\n✅ Tüm şehirler tamamlandı.")


if __name__ == "__main__":
    main()