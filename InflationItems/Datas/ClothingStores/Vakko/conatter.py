import os
import glob
import re
import pandas as pd

# 1. Klasör ve Dosya Yapısını Ayarla
# CSV dosyalarının olduğu klasör yolu (Script ile aynı yerdeyse '.' kalabilir)
folder_path = "."
file_pattern = os.path.join(folder_path, "vakko_*.csv")
all_files = glob.glob(file_pattern)

all_dfs = []

# 2. Dosyaları Tek Tek Oku ve Tarih Bilgisini Ekle
for file_path in all_files:
    file_name = os.path.basename(file_path)

    # Dosya adından YYYY-MM-DD formatındaki tarihi regex ile çek
    date_match = re.search(r'\d{4}-\d{2}-\d{2}', file_name)
    if date_match:
        date_str = date_match.group(0)
    else:
        continue  # Eğer isimde tarih yoksa bu dosyayı atla

    try:
        # CSV'yi oku (Türkçe karakter problemi olmaması için utf-8 veya ihtiyaca göre utf-8-sig)
        df = pd.read_csv(file_path, encoding='utf-8')
    except UnicodeDecodeError:
        # Alternatif encoding dene
        df = pd.read_csv(file_path, encoding='utf-8-sig')

    # Geçici olarak Tarih sütununu ekle
    df['Tarih'] = date_str
    all_dfs.append(df)

# 3. Birleştirme ve Sütun Sıralama İşlemleri
if all_dfs:
    # Tüm dataframe'leri birleştir (Farklı sütunlar varsa birleştirilir ve korunur)
    combined_df = pd.concat(all_dfs, ignore_index=True, sort=False)

    # 'Tarih' sütununu listenin en sonuna atarak sütunları yeniden sırala
    cols = [col for col in combined_df.columns if col != 'Tarih'] + ['Tarih']
    combined_df = combined_df[cols]

    # 4. Çıktıyı Kaydet
    output_name = "vakko_master_birlesik.csv"
    combined_df.to_csv(output_name, index=False, encoding='utf-8-sig')
    print(f"İşlem tamamlandı! {len(all_files)} adet dosya '{output_name}' adıyla birleştirildi.")
else:
    print("Belirtilen formatta birleştirilecek CSV dosyası bulunamadı.")