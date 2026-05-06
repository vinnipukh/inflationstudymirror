import requests
import csv
import time
from datetime import datetime

# -------------------------------------------------------------------
# KATEGORİLER  (sadece slug'lar)
# -------------------------------------------------------------------
KATEGORILER = [
    ("Meyve ve Sebze",          "meyve-ve-sebze-c"),
    ("Et ve Tavuk",             "et-ve-tavuk-urunleri-c"),
    ("Süt, Kahvaltılık, Sark.", "sut-kahvaltiliklar-sarkuteri-c"),
    ("Temel Gıda",              "temel-gida-c"),
    ("İçecekler",               "icecekler-c"),
    ("Atıştırmalıklar",         "atistirmaliklar-c"),
    ("Bebek Ürünleri",          "bebek-urunleri-c"),
    ("Deterjan ve Temizlik",    "deterjan-temizlik-c"),
    ("Kişisel Bakım",           "kisisel-bakim-ve-hijyen-c"),
    ("Ev ve Yaşam",             "ev-yasam-c"),
    ("Kitap, Kırtasiye",        "kitap-kirtasiye-oyuncak-c"),
    ("Petshop",                 "petshop-c"),
]

BASE_URL = "https://api.gurmar.com.tr/api/home/slug/{slug}?page={page}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


# -------------------------------------------------------------------
# Yardımcı fonksiyon: JSON ağacından tüm ürünleri recursive olarak çek
# -------------------------------------------------------------------
def extract_products(data):
    """
    API yanıtındaki iç içe geçmiş yapıda gezinerek
    component == "product-card" olan düğümlerdeki
    product objelerini toplar.
    """
    products = []

    if isinstance(data, dict):
        # Bulunduğumuz düğüm bir product-card ise ürünü ekle
        if data.get("component") == "product-card" and "product" in data:
            products.append(data["product"])
        # Alt dallarda da ara
        for value in data.values():
            products.extend(extract_products(value))

    elif isinstance(data, list):
        for item in data:
            products.extend(extract_products(item))

    return products


# -------------------------------------------------------------------
# Ana fonksiyon
# -------------------------------------------------------------------
def main():
    tum_urunler = []
    session = requests.Session()
    session.headers.update(HEADERS)

    for kategori_adi, slug in KATEGORILER:
        print(f"\n🔍 İşleniyor: {kategori_adi}")

        page = 1
        total_pages = 1
        beklenen_sayi = 0
        cekilen_urun_sayisi = 0

        while page <= total_pages:
            url = BASE_URL.format(slug=slug, page=page)

            try:
                response = session.get(url, timeout=15)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                print(f"  ❌ Sayfa {page} alınamadı: {e}")
                break

            # İlk sayfadan sayfalama bilgilerini al
            if page == 1:
                paging = data.get("paging", {})
                beklenen_sayi = paging.get("totalRecords", 0)
                total_pages = paging.get("totalPages", 1)
                print(f"  📦 Beklenen ürün sayısı: {beklenen_sayi}  "
                      f"(sayfa boyutu: {paging.get('pageSize', '?')}, "
                      f"toplam sayfa: {total_pages})")

            # Ürünleri çıkar
            products = extract_products(data.get("page", []))

            for product in products:
                isim = product.get("name", "")
                if not isim:
                    continue

                fiyat = product.get("price", "")

                # Ekstra bilgileri de istersen açabilirsin:
                # eski_fiyat = product.get("oldPrice")
                # indirim    = product.get("discountRate")
                # birim      = product.get("unitCode")
                # stok_disi  = product.get("outOfStock")

                tum_urunler.append({
                    "kategori":      kategori_adi,
                    "product_name":  isim,
                    "product_price": fiyat,
                })
                cekilen_urun_sayisi += 1

            print(f"  📄 Sayfa {page}/{total_pages} — "
                  f"bu sayfadan {len(products)} ürün çekildi")

            page += 1
            time.sleep(0.5)  # sunucuyu yormamak için kısa bekleme

        # Sonuç kontrolü
        if beklenen_sayi and cekilen_urun_sayisi == beklenen_sayi:
            print(f"  ✅ Başarılı! Beklenen: {beklenen_sayi} | "
                  f"Çekilen: {cekilen_urun_sayisi}")
        else:
            print(f"  ⚠️  Uyuşmazlık! Beklenen: {beklenen_sayi} | "
                  f"Çekilen: {cekilen_urun_sayisi}")

    # ── CSV'ye kaydet ────────────────────────────────────────────────
    bugunun_tarihi = datetime.now().strftime("%Y-%m-%d")
    csv_dosyasi = f"Datas/Markets/Gurmar/gurmar_prices_{bugunun_tarihi}.csv"

    with open(csv_dosyasi, "w", newline="", encoding="utf-8-sig") as file:
        fieldnames = ["kategori", "product_name", "product_price"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(tum_urunler)

    print(f"\n🎉 İşlem tamam! Toplam {len(tum_urunler)} ürün "
          f"'{csv_dosyasi}' dosyasına kaydedildi.")


if __name__ == "__main__":
    main()