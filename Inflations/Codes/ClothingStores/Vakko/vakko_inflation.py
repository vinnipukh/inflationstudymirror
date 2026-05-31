"""
vakko_inflation.py — Vakko Enflasyon Hesaplayıcı
"""

import logging
import os
import sys
from datetime import datetime, timedelta
import pandas as pd

# ── RELATIVE PATH SETUP ─────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

DATA_DIR = os.path.join(PROJECT_ROOT, "Datas", "ClothingStores", "Vakko")
INFLATION_OUT_DIR = os.path.join(PROJECT_ROOT, "Inflations", "Datas", "ClothingStores", "Vakko")

os.makedirs(INFLATION_OUT_DIR, exist_ok=True)

# Config dosyasını bulabilmesi için dizin ekliyoruz
sys.path.insert(0, SCRIPT_DIR)

logger = logging.getLogger(__name__)

try:
    from tuik_config import vakko_category_to_tuik, normalised_weights
except ImportError:
    try:
        from vakko_tuik_config import vakko_category_to_tuik, normalised_weights
    except ImportError:
        logger.error("HATA: tuik_config.py veya vakko_tuik_config.py bulunamadı!")
        sys.exit(1)


def _load_csv(date_str):
    """Vakko CSV'sini yükler, görünmez karakterleri siler ve fiyatları sayısallaştırır."""
    fpath = os.path.join(DATA_DIR, f"vakko_{date_str}.csv")
    if not os.path.exists(fpath):
        return None
    try:
        # utf-8-sig kullanımı BOM (\ufeff) karakterlerini otomatik temizler!
        df = pd.read_csv(fpath, sep=None, engine='python', encoding='utf-8-sig')

        # Sütun isimlerindeki boşlukları ve görünmez karakterleri zorla temizle
        rename_dict = {}
        for col in df.columns:
            c_lower = str(col).strip().lower().replace('\ufeff', '')
            if c_lower in ['product-name', 'product_name', 'isim', 'ürün adı']:
                rename_dict[col] = 'product-name'
            elif c_lower in ['product-price', 'product_price', 'price', 'fiyat']:
                rename_dict[col] = 'product-price'
            elif c_lower in ['stok kodu', 'stok_kodu', 'sku']:
                rename_dict[col] = 'Stok Kodu'

        df = df.rename(columns=rename_dict)

        # Fiyatları Sayısala Çevir
        if 'product-price' in df.columns:
            cleaned_price = (
                df['product-price']
                .astype(str)
                .str.replace('₺', '', regex=False)
                .str.replace('TL', '', regex=False)
                .str.strip()
            )
            cleaned_price = cleaned_price.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
            df['Fiyat'] = pd.to_numeric(cleaned_price, errors='coerce')

        # Stok Kodu temizliği (Merge eşleşmeme sorununu önler)
        if 'Stok Kodu' in df.columns:
            df['Stok Kodu'] = df['Stok Kodu'].astype(str).str.strip()
            df = df.drop_duplicates(subset=['Stok Kodu'], keep='first')

        return df
    except Exception as e:
        logger.error(f"Dosya okunurken hata oluştu {fpath}: {e}")
        return None


def _compute_metrics(df_current, df_past):
    df_current = df_current.copy()

    # Kategori Tespiti
    if 'product-name' in df_current.columns:
        df_current['tuik_category'] = df_current['product-name'].apply(vakko_category_to_tuik)
    else:
        df_current['tuik_category'] = None

    if 'Stok Kodu' not in df_current.columns or 'Stok Kodu' not in df_past.columns:
        return df_current, None, None

    past_subset = df_past[['Stok Kodu', 'Fiyat']].rename(columns={'Fiyat': 'past_price'})
    merged = df_current.merge(past_subset, on='Stok Kodu', how='left')

    # Fiyatların kesin sayısal olduğundan emin ol
    merged['Fiyat'] = pd.to_numeric(merged['Fiyat'], errors='coerce')
    merged['past_price'] = pd.to_numeric(merged['past_price'], errors='coerce')

    # Kaç ürünün geçmiş fiyatı bulunduğunu sayalım (0 ise zaten hesaplayamaz)
    valid_matches = merged.dropna(subset=['Fiyat', 'past_price'])

    if valid_matches.empty:
        return merged, None, None

    # Temel Enflasyon (Eğer fiyatlar aynıysa 0.0 çıkar, boş çıkmaz)
    merged['basic_inflation'] = ((merged['Fiyat'] - merged['past_price']) / merged['past_price']) * 100
    merged['basic_inflation'] = merged['basic_inflation'].replace([float('inf'), float('-inf')], pd.NA)

    avg_inflation = merged['basic_inflation'].mean()

    # TUIK Ağırlıklı
    if 'tuik_category' in merged.columns:
        cat_avg = merged.dropna(subset=['tuik_category', 'basic_inflation']).groupby('tuik_category')['basic_inflation'].mean()
        present_codes = list(cat_avg.index)

        if present_codes:
            norm_w = normalised_weights(present_codes)
            tuik_weighted = sum(
                cat_avg[c] * norm_w[c] / 100.0
                for c in norm_w
                if c in cat_avg.index and pd.notna(cat_avg[c])
            )
        else:
            tuik_weighted = None
    else:
        tuik_weighted = None

    return merged, avg_inflation, tuik_weighted


def calculate_inflation(target_date=None, compare_date=None):
    if target_date:
        base_date = datetime.strptime(target_date, "%Y-%m-%d")
    else:
        base_date = datetime.today()

    today_str = base_date.strftime("%Y-%m-%d")
    df_today = _load_csv(today_str)

    if df_today is None:
        logger.warning(f"Atlanıyor: {today_str} verisi bulunamadı.")
        return

    if compare_date:
        intervals = {f"custom": compare_date}
    else:
        intervals = {"1d": 1, "7d": 7, "15d": 15, "30d": 30}

    summary_row = {'date': today_str}
    detail_base = df_today.copy()

    if 'product-name' in detail_base.columns:
        detail_base['tuik_category'] = detail_base['product-name'].apply(vakko_category_to_tuik)
    else:
        detail_base['tuik_category'] = None

    for label, val in intervals.items():
        if isinstance(val, int):
            past_str = (base_date - timedelta(days=val)).strftime("%Y-%m-%d")
        else:
            past_str = val

        df_past = _load_csv(past_str)

        if df_past is None:
            summary_row[f'avg_inflation_{label}'] = None
            summary_row[f'tuik_weighted_{label}'] = None
            continue

        merged, avg_inf, tuik_w = _compute_metrics(df_today, df_past)

        if 'Stok Kodu' in merged.columns:
            # Sadece basic_inflation kolonunu alıp ismini değiştirerek ana tabloya ekliyoruz
            detail_base = detail_base.merge(
                merged[['Stok Kodu', 'basic_inflation']].rename(columns={'basic_inflation': f'basic_inflation_{label}'}),
                on='Stok Kodu', how='left'
            )

        summary_row[f'avg_inflation_{label}'] = avg_inf
        summary_row[f'tuik_weighted_{label}'] = tuik_w

        # Sadece bilgi amaçlı log atıyoruz
        matched_count = merged.dropna(subset=[f'basic_inflation']).shape[0] if 'basic_inflation' in merged.columns else 0
        logger.info(f"{today_str} vs {past_str} ({label}): Eşleşen ürün: {matched_count} | Ort. Enf: {avg_inf}")

    detail_file = os.path.join(INFLATION_OUT_DIR, f"vakko_inflation_{today_str}.csv")
    detail_base.to_csv(detail_file, index=False, encoding='utf-8-sig')

    summary_file = os.path.join(INFLATION_OUT_DIR, "inflation_summary.csv")
    df_summary = pd.DataFrame([summary_row])

    try:
        if os.path.exists(summary_file):
            df_existing = pd.read_csv(summary_file, encoding='utf-8-sig')
            df_existing = df_existing[df_existing['date'] != today_str]
            df_final = pd.concat([df_existing, df_summary], ignore_index=True)
            df_final.to_csv(summary_file, index=False, encoding='utf-8-sig')
        else:
            df_summary.to_csv(summary_file, index=False, encoding='utf-8-sig')
    except Exception as e:
        logger.error(f"Özet dosyası yazılırken hata oluştu: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Vakko enflasyon hesaplayıcı")
    parser.add_argument("--date", help="Hedef (güncel) tarih YYYY-MM-DD formatında", default=None)
    parser.add_argument("--compare", help="Karşılaştırılacak (geçmiş) tarih YYYY-MM-DD formatında", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    calculate_inflation(args.date, args.compare)