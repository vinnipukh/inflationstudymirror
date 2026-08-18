import os
import re
import time
import random
import datetime
import requests
import pandas as pd
from pathlib import Path

print("🚀 Vakko Master Scraper Başlatılıyor...\n")

# .env dosyası varsa elle oku (yalnızca webdriver devre dışıyken kullanılan yedek değişkenler)
try:
    _env_yolu = Path(__file__).resolve().parents[3] / ".env"
    if _env_yolu.exists():
        for satir in _env_yolu.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if satir and not satir.startswith("#") and "=" in satir:
                anahtar, deger = satir.split("=", 1)
                os.environ.setdefault(anahtar.strip(), deger.strip().strip('"').strip("'"))
except OSError:
    pass

# ==========================================
# 0. SABİTLER
# ==========================================
API_URL = "https://api.vakko.com/occ/v2/vsite/products/search"
SITEMAP_INDEX_URL = "https://www.vakko.com/sitemap.xml"
ANA_SAYFA_URL = "https://www.vakko.com/"

MAX_RETRY = 3                    # max 3 retry
RETRY_BASLANGIC_BEKLEME = 15     # +15 saniye artan: 15s, 30s, 45s

# Test/operasyon kolaylığı için opsiyonel geçersiz kılmalar (varsayılan: orijinal hız)
SAYFA_BEKLEME = float(os.getenv("VAKKO_PAGE_SLEEP", "3.2"))  # sayfa arası (random üst sınır: +1.6s)
KATEGORI_BEKLEME = float(os.getenv("VAKKO_CAT_SLEEP", "3.7"))  # kategori arası (random üst sınır: +1.8s)


# ==========================================
# 1. YARDIMCI: RETRY'LI GET
# ==========================================
def gecici_hata_mi(status_kodu):
    """429 ve 5xx + ağ hataları geçicidir; 400/403/404 kalıcıdır (retry edilmez)."""
    return status_kodu is None or status_kodu == 429 or status_kodu >= 500


def get_with_retry(session, url, params=None, etiket=""):
    """GET isteği — her başarısızlıkta +15s artan bekleme ile max 3 retry."""
    for deneme in range(MAX_RETRY + 1):
        try:
            yanit = session.get(url, params=params, timeout=30)
            if yanit.status_code == 200 or not gecici_hata_mi(yanit.status_code):
                return yanit
            hata = f"HTTP {yanit.status_code}"
        except requests.RequestException as e:
            hata = str(e)[:80]

        if deneme < MAX_RETRY:
            bekle = RETRY_BASLANGIC_BEKLEME * (deneme + 1)
            print(f"    ⚠️ {etiket} başarısız ({hata}) — {bekle}s sonra tekrar deneniyor "
                  f"(retry {deneme + 1}/{MAX_RETRY})")
            time.sleep(bekle)

    print(f"    ❌ {etiket} {MAX_RETRY} retry sonrası da başarısız: {hata}")
    return None


# ==========================================
# 2. YARDIMCI: CHROME WEBDRIVER İLE TAZE ÇEREZLER
# ==========================================
def taze_cerezler():
    """vakko.com'a Chrome webdriver ile girip o anki taze çerezleri + UA'yı alır.

    Cookie-factory deseni: tarayıcı siteyi bir kez gezer, çerezleri toplar,
    kapanır; toplanan çerezler API isteklerinde kullanılır.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    if os.getenv("VAKKO_HEADED") != "1":
        options.add_argument("--headless=new")

    surucu = webdriver.Chrome(options=options)
    try:
        surucu.get(ANA_SAYFA_URL)
        time.sleep(random.uniform(8, 12))  # ana sayfa ısınma + çerezlerin oturması
        cerezler = surucu.get_cookies()
        user_agent = surucu.execute_script("return navigator.userAgent")
    finally:
        surucu.quit()

    cerez_metni = "; ".join(f"{c['name']}={c['value']}" for c in cerezler)
    return cerez_metni, user_agent


# ==========================================
# 3. YARDIMCI: SITEMAP'LERDEN KATEGORİ ÇEKME
# ==========================================
def xml_kategorileri(xml_metni):
    """Sitemap XML'inden Kadin/Erkek/Shoes_Bags kategori ID'lerini ayıklar
    (Outlet hariç — orijinal filtre mantığı aynen korunur)."""
    kategoriler = {"Kadin": [], "Erkek": [], "Shoes_Bags": []}
    for link in re.findall(r"<loc>(.*?)</loc>", xml_metni):
        link = link.strip()
        match = re.search(r"-c-([a-zA-Z0-9_-]+)/?$", link)
        if match:
            kat_id = match.group(1)
            if "/kadin" in link and "/outlet" not in link and kat_id not in kategoriler["Kadin"]:
                kategoriler["Kadin"].append(kat_id)
            elif "/erkek" in link and "/outlet" not in link and kat_id not in kategoriler["Erkek"]:
                kategoriler["Erkek"].append(kat_id)
            elif ("/ayakkabi-canta" in link or "/shoes-bags" in link) and "/outlet" not in link \
                    and kat_id not in kategoriler["Shoes_Bags"]:
                kategoriler["Shoes_Bags"].append(kat_id)
    return kategoriler


def canli_sitemap_kategorileri(session):
    """O anki canlı sitemap'i indirir: sitemap.xml index -> TR Category sitemap'i."""
    idx = get_with_retry(session, SITEMAP_INDEX_URL, etiket="sitemap index")
    if idx is None:
        return None

    kategori_sitemap_url = [
        u.strip() for u in re.findall(r"<loc>(.*?)</loc>", idx.text)
        if u.strip().endswith("/sitemap/Category.xml")
    ]
    if not kategori_sitemap_url:
        return None

    # TR sürümü (locale öneki olmayan) tercih edilir
    tr_surumu = [u for u in kategori_sitemap_url if not re.search(r"/(en|el-gr|en-gr|en-eu)/", u)]
    hedef = (tr_surumu or kategori_sitemap_url)[0]

    yanit = get_with_retry(session, hedef, etiket="category sitemap")
    if yanit is None:
        return None
    return xml_kategorileri(yanit.text)


def kategorileri_birlestir(eski, yeni):
    """Eski liste önce, yeni sitemaptaki ekstra kategoriler sonra.

    - Eski sıra korunur -> 'Kategori ID' etiketleri geçmişle aynı kalır.
    - Sitemap'ten düşmüş ama API'de yaşayan kategoriler (vk13/vk18/vk421)
      kaybolmaz.
    - Sitemap'te yeni açılan kategoriler (Mare 30603 vb.) listeye eklenir.
    """
    birlesik = {}
    for grup in eski:
        eski_set = set(eski[grup])
        yeni_liste = yeni.get(grup, [])
        yeni_eklenen = [i for i in yeni_liste if i not in eski_set]
        birlesik[grup] = list(eski[grup]) + yeni_eklenen
    for grup in yeni:
        if grup not in birlesik:
            birlesik[grup] = list(yeni[grup])
    return birlesik


# ==========================================
# 4. ÇEREZLERİ AL (her çalıştırmada taze)
# ==========================================
session = requests.Session()

print("🍪 Chrome webdriver ile taze çerezler alınıyor...")
try:
    cerez_metni, gizli_user_agent = taze_cerezler()
    cerez_sayisi = len(cerez_metni.split("; ")) if cerez_metni else 0
    print(f"✅ Webdriver'dan {cerez_sayisi} çerez alındı. UA: {gizli_user_agent[:70]}...")
except Exception as e:
    print(f"⚠️ Webdriver çalışmadı ({str(e)[:100]}).")
    cerez_metni = os.getenv("VAKKO_COOKIE")
    gizli_user_agent = os.getenv("VAKKO_USER_AGENT")
    if cerez_metni:
        print("ℹ️  Env'deki VAKKO_COOKIE kullanılıyor (webdriver yerine).")
    else:
        print("ℹ️  Çerezsiz (anonim) devam ediliyor — API anonim istekleri kabul ediyor.")
    if not gizli_user_agent:
        gizli_user_agent = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

headers = {
    "User-Agent": gizli_user_agent,
    "Accept": "application/json, text/plain, */*",
    "Platform": "WEB",
    "Origin": "https://www.vakko.com",
    "Referer": "https://www.vakko.com/",
    "Cookie": cerez_metni,  # None ise requests bu başlığı göndermez
}
session.headers.update(headers)

# ==========================================
# 5. KATEGORİ LİSTESİ: CANLI SITEMAP (yerel XML yedek)
# ==========================================
mevcut_klasor = Path(__file__).parent
xml_dosya_yolu = mevcut_klasor / "vakko_categories.xml"

kategoriler = None
try:
    canli = canli_sitemap_kategorileri(session)
    if canli and sum(len(v) for v in canli.values()) > 0:
        toplam_canli = sum(len(v) for v in canli.values())
        try:
            with open(xml_dosya_yolu, "r", encoding="utf-8") as dosya:
                yerel = xml_kategorileri(dosya.read())
            kategoriler = kategorileri_birlestir(yerel, canli)
            print(f"✅ Canlı sitemap kullanıldı ({toplam_canli} kategori) — "
                  f"yerel XML ile birleştirildi.")
        except FileNotFoundError:
            kategoriler = canli
            print(f"✅ Canlı sitemap kullanıldı ({toplam_canli} kategori). "
                  f"Yerel XML bulunamadı, sitemap tek başına yeterli.")
    else:
        print("⚠️ Canlı sitemap'ten kategori alınamadı, yerel XML deneniyor...")
except Exception as e:
    print(f"⚠️ Canlı sitemap hatası: {str(e)[:100]}. Yerel XML deneniyor...")

if kategoriler is None:
    try:
        with open(xml_dosya_yolu, "r", encoding="utf-8") as dosya:
            xml_metni = dosya.read()
        kategoriler = xml_kategorileri(xml_metni)
        print(f"✅ Yerel XML kullanıldı ({sum(len(v) for v in kategoriler.values())} kategori).")
    except FileNotFoundError:
        print("❌ HATA: vakko_categories.xml bulunamadı ve canlı sitemap alınamadı!")
        exit()

toplam_kategori = sum(len(ids) for ids in kategoriler.values())
print(f"📂 Toplam {toplam_kategori} kategori taranacak.\n")

# ==========================================
# 6. API'DEN ÜRÜNLERİ ÇEKME (retry'li)
# ==========================================
tum_urunler_temiz = []
atlanan_kategoriler = []
islenen_kategori = 0

for ana_kategori, id_list in kategoriler.items():
    for kat_id in id_list:
        islenen_kategori += 1
        mevcut_sayfa = 0
        toplam_sayfa = 1
        kategori_basarili = True

        print(f"[{islenen_kategori}/{toplam_kategori}] Taraniyor -> {ana_kategori} | ID: {kat_id}")

        while mevcut_sayfa < toplam_sayfa:
            params = {
                "fields": "FULL,facets,breadcrumbs,pagination(DEFAULT),sorts(DEFAULT)",
                "query": f":relevance:allCategories:{kat_id}",
                "pageSize": "48",
                "lang": "tr",
                "curr": "TRY",
                "currentPage": str(mevcut_sayfa)
            }

            response = get_with_retry(session, API_URL, params=params,
                                      etiket=f"kategori {kat_id} sayfa {mevcut_sayfa}")

            if response is None or response.status_code != 200:
                print(f"    ⚠️ HATA! {kat_id} çekilemedi ({MAX_RETRY} retry denendi). Bu kategori atlanıyor.")
                kategori_basarili = False
                break

            data = response.json()
            toplam_sayfa = data.get('pagination', {}).get('totalPages', 1)
            urunler = data.get('products', [])

            for urun in urunler:
                # Kampanya kategorileri (vk60/vk61 vb.) bazen outlet ürünü içerebiliyor;
                # tasarım gereği outlet ürünleri veriye girmez.
                urun_kategorileri = urun.get('categories') or []
                if any((k.get('code') or '').startswith('312') or k.get('name') == 'Outlet'
                       for k in urun_kategorileri):
                    continue

                fiyat_sozlugu = urun.get('price', {})
                fiyat = fiyat_sozlugu.get('formattedValue', fiyat_sozlugu.get('value', 'Fiyat Yok'))

                tum_urunler_temiz.append({
                    "product-name": urun.get('name', 'İsimsiz'),
                    "product-price": fiyat,
                    "Ana Kategori": ana_kategori,
                    "Kategori ID": kat_id,
                    "Stok Kodu": urun.get('code', 'Kod Yok')
                })

            mevcut_sayfa += 1

            if mevcut_sayfa < toplam_sayfa:
                time.sleep(random.uniform(SAYFA_BEKLEME, SAYFA_BEKLEME + 1.6))

        if not kategori_basarili:
            atlanan_kategoriler.append(f"{ana_kategori}/{kat_id}")

        time.sleep(random.uniform(KATEGORI_BEKLEME, KATEGORI_BEKLEME + 1.8))

# ==========================================
# 7. VERİYİ TEMİZLEME VE CSV'YE KAYDETME
# ==========================================
print(f"\n✅ Tarama Bitti! Ham ürün sayısı: {len(tum_urunler_temiz)}")

if atlanan_kategoriler:
    print(f"⚠️ {len(atlanan_kategoriler)} kategori atlandı: {', '.join(atlanan_kategoriler)}")

mevcut_dosya = Path(__file__).resolve()
proje_koku = mevcut_dosya.parents[3]
hedef_klasor = proje_koku / "Datas" / "ClothingStores" / "Vakko"
hedef_klasor.mkdir(parents=True, exist_ok=True)

bugunun_tarihi = datetime.datetime.now().strftime("%Y-%m-%d")
tam_dosya_yolu = hedef_klasor / f"vakko_{bugunun_tarihi}.csv"

df = pd.DataFrame(tum_urunler_temiz)

if not df.empty:
    sutun_sirasi = ["product-name", "product-price", "Ana Kategori", "Kategori ID", "Stok Kodu"]
    df = df[sutun_sirasi]

    df.drop_duplicates(subset=['Stok Kodu'], inplace=True)

    # sep=',' olarak değiştirildi (virgül ayracı)
    df.to_csv(tam_dosya_yolu, index=False, sep=',', encoding="utf-8-sig")
    print(f"🧹 Temizlik sonrası benzersiz ürün sayısı: {len(df)}")
    print(f"📁 Dosya başarıyla kaydedildi:\n--> {tam_dosya_yolu}")
else:
    print("⚠️ Hiç ürün çekilemediği için CSV oluşturulmadı.")
