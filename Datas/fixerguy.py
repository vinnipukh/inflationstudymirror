import os
import glob
import pandas as pd


def csv_sutun_ustune_yaz(hedef_klasor):
    # Klasördeki tüm .csv uzantılı dosyaları bul
    csv_dosyalari = glob.glob(os.path.join(hedef_klasor, "*.csv"))

    if not csv_dosyalari:
        print(f"'{hedef_klasor}' klasöründe CSV dosyası bulunamadı.")
        return

    for dosya_yolu in csv_dosyalari:
        dosya_adi = os.path.basename(dosya_yolu)

        try:
            # CSV dosyasını oku
            df = pd.read_csv(dosya_yolu)

            # Sütun isimlerini kontrol et ve değiştir
            yeni_isimler = {}
            if 'product_name' in df.columns:
                yeni_isimler['product_name'] = 'product-name'
            if 'FiyatFloat' in df.columns:
                yeni_isimler['product_price'] = 'product-price'

            if yeni_isimler:
                df = df.rename(columns=yeni_isimler)

            # Hedeflenen sütunların varlığını kontrol et
            mevcut_hedef_sutunlar = [col for col in ['product-name', 'product-price'] if col in df.columns]

            # Belirtilen sütunları başa al, diğerlerini arkasına ekle
            yeni_sira = mevcut_hedef_sutunlar + [col for col in df.columns if col not in mevcut_hedef_sutunlar]
            df = df[yeni_sira]

            # Aynı dosya yoluna geri yaz (dosya adı ve klasör değişmez)
            df.to_csv(dosya_yolu, index=False)
            print(f"Güncellendi: {dosya_adi}")

        except Exception as e:
            print(f"{dosya_adi} işlenirken hata oluştu: {e}")


# CSV dosyalarının olduğu klasörün yolunu buraya yazın
KLASOR_YOLU = f"C:\\Users\\arhan\\PycharmProjects\\inflationstudymirror\\Datas\\Markets\\Gurmar"

csv_sutun_ustune_yaz(KLASOR_YOLU)