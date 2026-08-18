import requests
import csv
import time
import os
import sys
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -------------------------------------------------------------------
# KATEGORİLER — yedek liste (initialize-v2 çekilemezse kullanılır)
# -------------------------------------------------------------------
FALLBACK_KATEGORILER = [
    ("Meyve ve Sebze", "meyve-ve-sebze-c"),
    ("Et ve Tavuk", "et-ve-tavuk-urunleri-c"),
    ("Süt, Kahvaltılık, Sark.", "sut-kahvaltiliklar-sarkuteri-c"),
    ("Temel Gıda", "temel-gida-c"),
    ("İçecekler", "icecekler-c"),
    ("Atıştırmalıklar", "atistirmaliklar-c"),
    ("Bebek Ürünleri", "bebek-urunleri-c"),
    ("Deterjan ve Temizlik", "deterjan-temizlik-c"),
    ("Kişisel Bakım", "kisisel-bakim-ve-hijyen-c"),
    ("Ev ve Yaşam", "ev-yasam-c"),
    ("Petshop", "petshop-c"),
    # NOT: "Kitap, Kırtasiye" (kitap-kirtasiye-oyuncak-c) kaldırıldı —
    # kategori 2026-08-18 itibarıyla katalogdan tamamen silinmiş
    # (initialize-v2 ağacında yok, API 0 ürün döndürüyor).
]

BASE_URL = "https://api.gurmar.com.tr/api/home/slug/{slug}?page={page}"
INIT_URL = "https://api.gurmar.com.tr/api/home/initialize-v2"
PAGE_SIZE = 25          # API'nin döndürdüğü sayfa boyutu
MAX_PAGES = 200         # sonsuz döngü koruması
SLEEP_CATEGORY = 0.3    # kategoriler arası bekleme
SLEEP_PAGE = 0.5        # sayfalar arası bekleme

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def extract_products(data):
    """
    API yanıtındaki iç içe geçmiş yapıda gezinerek
    component == "product-card" olan düğümlerdeki
    product objelerini toplar.
    """
    products = []

    if isinstance(data, dict):
        if data.get("component") == "product-card" and "product" in data:
            products.append(data["product"])
        for value in data.values():
            products.extend(extract_products(value))

    elif isinstance(data, list):
        for item in data:
            products.extend(extract_products(item))

    return products


def discover_categories(session):
    """
    initialize-v2 yanıtından tüm '-c' kategori slug'larını toplar.
    Alt kategoriler dahildir — bu sayede API sayfalaması bozuk olsa bile
    katalog kapsamı maksimize edilir (her alt kategori kendi ilk sayfasını
    döndürür). Sırayı koruyarak yinelenen slug'ları temizler.
    """
    try:
        response = session.get(INIT_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"  ⚠️ initialize-v2 alınamadı ({e}), yedek kategori listesi kullanılıyor.")
        return FALLBACK_KATEGORILER

    slugs = []

    def walk(node):
        if isinstance(node, dict):
            slug = node.get("slug")
            if isinstance(slug, str) and slug.endswith("-c"):
                baslik = node.get("title") or node.get("name") or slug
                slugs.append((str(baslik), slug))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)

    seen = set()
    kategoriler = []
    for baslik, slug in slugs:
        if slug not in seen:
            seen.add(slug)
            kategoriler.append((baslik, slug))

    print(f"  🗂️  initialize-v2'den {len(kategoriler)} kategori bulundu")
    return kategoriler


def main():
    tum_urunler = {}   # product-id -> kayıt (ilk görülen korunur)
    session = requests.Session()
    session.headers.update(HEADERS)

    # Robust retry strategy for unattended GitHub Actions workflows
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))

    kategoriler = discover_categories(session)

    toplam_beklenen = 0     # katalogdaki toplam ürün sayısı (totalRecords toplamı)
    hatali_kategori = 0     # hiç ürün alınamayan kategoriler
    uyari_sayisi = 0        # veri bütünlüğü uyarıları

    for kategori_adi, slug in kategoriler:
        print(f"\n🔍 İşleniyor: {kategori_adi} ({slug})")

        page = 1
        total_pages = 1
        beklenen_sayi = 0
        kategori_idleri = set()   # bu kategoriden dönen ürün id'leri (küresel dedup'tan bağımsız)

        while page <= total_pages:
            url = BASE_URL.format(slug=slug, page=page)

            try:
                response = session.get(url, timeout=15)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as e:
                print(f"  ❌ Sayfa {page} alınamadı: {e}")
                break

            if page == 1:
                if "page" not in data or "paging" not in data:
                    print("  ❌ Geçersiz yanıt (hata zarfı), kategori atlanıyor.")
                    hatali_kategori += 1
                    break
                paging = data.get("paging", {})
                beklenen_sayi = paging.get("totalRecords", 0) or 0
                total_pages = min(paging.get("totalPages", 1) or 1, MAX_PAGES)
                print(f"  📦 Beklenen ürün sayısı: {beklenen_sayi}  "
                      f"(sayfa boyutu: {paging.get('pageSize', '?')}, "
                      f"toplam sayfa: {total_pages})")

            products = extract_products(data.get("page", []))
            yeni = 0

            for product in products:
                isim = product.get("name", "")
                if not isim:
                    continue

                try:
                    fiyat = float(product.get("price", 0.0))
                except (ValueError, TypeError):
                    fiyat = 0.0

                urun_id = str(product.get("id", ""))

                if not urun_id:
                    continue

                kategori_idleri.add(urun_id)

                if urun_id not in tum_urunler:
                    tum_urunler[urun_id] = {
                        "product-name": str(isim),
                        "product-price": fiyat,
                        "product-id": urun_id,
                    }
                    yeni += 1

            print(f"  📄 Sayfa {page}/{total_pages} — "
                  f"bu sayfadan {len(products)} ürün, {yeni} yeni")

            # Sayfalar arasında yeni ürün gelmiyorsa dur.
            # (API 'page' parametresini yok sayıp her sayfada aynı ürünleri
            # döndürüyorsa 2. sayfada bu koşul tetiklenir ve gereksiz
            # istekler engellenir. API düzeldiğinde döngü normal çalışır.)
            if page > 1 and yeni == 0:
                print("  ⏹️  Yeni ürün gelmedi, sayfalama durduruldu.")
                break

            if page >= MAX_PAGES:
                break

            page += 1
            time.sleep(SLEEP_PAGE)

        # ── kategori bazında bütünlük kontrolü ─────────────────────────
        # (cekilen = bu kategorinin kendi sayfalarından dönen benzersiz ürün
        # sayısı; diğer kategorilerle çakışan ürünler de sayılır)
        cekilen = len(kategori_idleri)
        if beklenen_sayi > 0:
            toplam_beklenen += beklenen_sayi
            sayfa_basina = min(beklenen_sayi, PAGE_SIZE)

            if cekilen == 0:
                hatali_kategori += 1
                print(f"  ❌ Kategori alınamadı! Beklenen: {beklenen_sayi} | "
                      f"Çekilen: 0")
            elif cekilen < sayfa_basina:
                uyari_sayisi += 1
                print(f"  ⚠️  EKSİK VERİ! Beklenen: {beklenen_sayi} | "
                      f"Çekilen: {cekilen} "
                      f"(ilk sayfada bile eksik ürün var)")
            elif beklenen_sayi > PAGE_SIZE and cekilen < beklenen_sayi:
                # API sayfalaması bozuk: her sayfa aynı ilk sayfayı döndürüyor
                uyari_sayisi += 1
                print(f"  ⚠️  API SAYFALAMA BOZUK! Beklenen: {beklenen_sayi} | "
                      f"Çekilen: {cekilen} "
                      f"(tüm sayfalar aynı ürünleri döndürüyor, katalog "
                      f"kapsamı kısıtlı)")
            else:
                print(f"  ✅ Başarılı! Beklenen: {beklenen_sayi} | "
                      f"Çekilen: {cekilen}")

        time.sleep(SLEEP_CATEGORY)

    # ── CSV'ye kaydet ────────────────────────────────────────────────
    bugunun_tarihi = datetime.now().strftime("%Y-%m-%d")

    # Dynamically find the project root directory (3 levels up from this script)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))

    # Target the root-level Datas/Markets/Gurmar folder
    target_dir = os.path.join(project_root, "Datas", "Markets", "Gurmar")
    csv_dosyasi = os.path.join(target_dir, f"gurmar_prices_{bugunun_tarihi}.csv")

    os.makedirs(target_dir, exist_ok=True)

    with open(csv_dosyasi, "w", newline="", encoding="utf-8-sig") as file:
        fieldnames = ["product-name", "product-price", "product-id"]
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(tum_urunler.values())

    print(f"\n🎉 İşlem tamam! Toplam {len(tum_urunler)} benzersiz ürün "
          f"'{csv_dosyasi}' dosyasına kaydedildi.")
    print(f"📊 Özet: {len(kategoriler)} kategori | "
          f"katalogdaki toplam ürün (totalRecords): {toplam_beklenen} | "
          f"hatalı kategori: {hatali_kategori} | "
          f"bütünlük uyarısı: {uyari_sayisi}")

    # Veri bütünlüğü sorunu varsa non-zero exit →
    # GitHub Actions çalışması kırmızıya döner ve sorun görünür olur.
    if hatali_kategori > 0 or uyari_sayisi > 0:
        print("\n🚨 DİKKAT: Veri bütünlüğü sorunları tespit edildi! "
              "Detaylar yukarıda. CSV yine de yazıldı.")
        sys.exit(1)


if __name__ == "__main__":
    main()
