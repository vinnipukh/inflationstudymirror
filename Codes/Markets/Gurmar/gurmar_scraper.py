import requests
import csv
import time
import os
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -------------------------------------------------------------------
# KATEGORİLER  (sadece slug'lar)
# -------------------------------------------------------------------
KATEGORILER = [
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
    ("Kitap, Kırtasiye", "kitap-kirtasiye-oyuncak-c"),
    ("Petshop", "petshop-c"),
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


def main():
    tum_urunler = []
    session = requests.Session()
    session.headers.update(HEADERS)

    # Surgical Add: Robust retry strategy for unattended GitHub Actions workflows
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))

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

            if page == 1:
                paging = data.get("paging", {})
                beklenen_sayi = paging.get("totalRecords", 0)
                total_pages = paging.get("totalPages", 1)
                print(f"  📦 Beklenen ürün sayısı: {beklenen_sayi}  "
                      f"(sayfa boyutu: {paging.get('pageSize', '?')}, "
                      f"toplam sayfa: {total_pages})")

            products = extract_products(data.get("page", []))

            for product in products:
                isim = product.get("name", "")
                if not isim:
                    continue

                # Ensures price is safely cast to float as requested
                try:
                    fiyat = float(product.get("price", 0.0))
                except (ValueError, TypeError):
                    fiyat = 0.0

                urun_id = product.get("id", "")

                # Surgical Fix: Mapping exact requested column headers
                tum_urunler.append({
                    "product-name": str(isim),
                    "product-price": fiyat,
                    "product-id": str(urun_id)
                })
                cekilen_urun_sayisi += 1

            print(f"  📄 Sayfa {page}/{total_pages} — "
                  f"bu sayfadan {len(products)} ürün çekildi")

            page += 1
            time.sleep(0.5)

        if beklenen_sayi and cekilen_urun_sayisi == beklenen_sayi:
            print(f"  ✅ Başarılı! Beklenen: {beklenen_sayi} | "
                  f"Çekilen: {cekilen_urun_sayisi}")
        else:
            print(f"  ⚠️  Uyuşmazlık! Beklenen: {beklenen_sayi} | "
                  f"Çekilen: {cekilen_urun_sayisi}")

    # ── CSV'ye kaydet ────────────────────────────────────────────────
    bugunun_tarihi = datetime.now().strftime("%Y-%m-%d")
    csv_dosyasi = f"Datas/Markets/Gurmar/gurmar_prices_{bugunun_tarihi}.csv"

    os.makedirs(os.path.dirname(csv_dosyasi), exist_ok=True)

    # Surgical Fix: delimiter=";" and strict column ordering
    with open(csv_dosyasi, "w", newline="", encoding="utf-8-sig") as file:
        fieldnames = ["product-name", "product-price", "product-id"]
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(tum_urunler)

    print(f"\n🎉 İşlem tamam! Toplam {len(tum_urunler)} ürün "
          f"'{csv_dosyasi}' dosyasına kaydedildi.")


if __name__ == "__main__":
    main()