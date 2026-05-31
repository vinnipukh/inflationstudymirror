"""
gurmar_inflation.py — Gurmar Daily Inflation Calculator CLI
"""

import argparse
import logging
import re
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

try:
    from gurmar_tuik_config import gurmar_category_to_tuik as migros_category_to_tuik, normalised_weights
except ImportError:
    print("HATA: gurmar_tuik_config.py dosyası bulunamadı! Lütfen aynı dizinde olduğundan emin ol.")
    sys.exit(1)

logger = logging.getLogger(__name__)

# ── STRICT RELATIVE PATH SETUP ──────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "Datas", "Markets", "Gurmar")
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "Inflations", "Datas", "Markets", "Gurmar")


def _build_category_mapping(out_dir_path):
    mapping = {}
    if not out_dir_path.exists():
        return mapping

    for f in out_dir_path.glob("gurmar_inflation_*.csv"):
        try:
            temp_df = pd.read_csv(f, usecols=['id', 'category'], on_bad_lines='skip', engine='python')
            temp_dict = temp_df.dropna(subset=['id', 'category']).set_index('id')['category'].to_dict()
            mapping.update(temp_dict)
        except Exception:
            continue
    return mapping


def load_and_clean_csv(file_path, category_mapping=None):
    """Verilen dosya yolundan CSV'yi okur ve esnek sütun yapısıyla temizler."""
    if not file_path.exists():
        logger.info(f"Veri dosyası bulunamadı: {file_path}")
        return None
    try:
        # C-error (tokenizing) hatalarını önlemek için bozuk satırları atla (on_bad_lines='skip')
        try:
            df = pd.read_csv(file_path, sep=';', on_bad_lines='skip', encoding='utf-8')
            if len(df.columns) < 2:
                df = pd.read_csv(file_path, sep=',', on_bad_lines='skip', encoding='utf-8')
        except Exception:
            df = pd.read_csv(file_path, sep=None, engine='python', on_bad_lines='skip', encoding='utf-8')

        if df is None or df.empty:
            return None

        # Sütun isimlerini normalize edip eşleştir
        rename_dict = {}
        for col in df.columns:
            c_lower = str(col).lower().strip()
            if c_lower in ['product-name', 'product_name', 'id', 'name']:
                rename_dict[col] = 'id'
            elif c_lower in ['product-price', 'product_price', 'price', 'shown_price', 'fiyat']:
                rename_dict[col] = 'shown_price'
            elif c_lower in ['kategori', 'category', 'tuik_category']:
                rename_dict[col] = 'category'

        df = df.rename(columns=rename_dict)

        # EĞER KRİTİK SÜTUNLAR YOKSA DOSYAYI İPTAL ET (KeyError engellemesi)
        if 'id' not in df.columns or 'shown_price' not in df.columns:
            logger.warning(f"Gerekli sütunlar bulunamadı, dosya atlanıyor: {file_path.name}")
            return None

        if 'category' not in df.columns:
            df['category'] = pd.NA

        # ID si olmayanları sil ve tekilleştir
        df = df.dropna(subset=['id'])
        df = df.drop_duplicates(subset=['id'], keep='first')

        if category_mapping:
            df['category'] = df['category'].fillna(df['id'].map(category_mapping))

        df['category'] = df['category'].fillna("Bilinmiyor")

        # Fiyatları float formatına temizle
        s = df['shown_price'].astype(str).str.replace('"', '', regex=False).str.replace('₺', '', regex=False).str.strip()
        s = s.str.replace(r'\.0$', '', regex=True)
        df['shown_price'] = s.apply(lambda x: x.replace('.', '').replace(',', '.') if ',' in x else x)
        df['shown_price'] = pd.to_numeric(df['shown_price'], errors='coerce')

        return df
    except Exception as e:
        logger.error(f"Dosya okunamadı {file_path}: {e}")
        return None


def _safe_tuik_map(cat_name):
    if pd.isna(cat_name) or cat_name == "Bilinmiyor":
        return None
    try:
        return migros_category_to_tuik(cat_name)
    except Exception:
        return None


def _compute_metrics(df_current, df_past):
    df_current = df_current.copy()
    df_current['tuik_category'] = df_current['category'].apply(_safe_tuik_map)

    past_subset = df_past[['id', 'shown_price']].rename(columns={'shown_price': 'past_price'})
    merged = df_current.merge(past_subset, on='id', how='left')

    merged['basic_inflation'] = ((merged['shown_price'] - merged['past_price']) / merged['past_price']) * 100
    merged['basic_inflation'] = merged['basic_inflation'].replace([float('inf'), float('-inf')], pd.NA)

    avg_inflation = merged['basic_inflation'].mean()

    valid = merged.dropna(subset=['shown_price', 'past_price'])
    sum_current = valid['shown_price'].sum()
    sum_past = valid['past_price'].sum()
    basic_inflation_index = ((sum_current - sum_past) / sum_past) * 100 if sum_past else None

    cat_avg = merged.dropna(subset=['tuik_category']).groupby('tuik_category')['basic_inflation'].mean()
    present_codes = list(cat_avg.dropna().index)

    if present_codes:
        norm_w = normalised_weights(present_codes)
        tuik_weighted = sum(cat_avg[c] * norm_w[c] / 100.0 for c in norm_w if c in cat_avg.index and pd.notna(cat_avg[c]))
    else:
        tuik_weighted = None

    merged = merged.drop(columns=['past_price'], errors='ignore')
    return merged, basic_inflation_index, avg_inflation, tuik_weighted


def calculate_inflation(input_file, output_dir=None, compare_file=None):
    input_path = Path(input_file).resolve()

    if not input_path.exists():
        logger.error(f"Girdi dosyası bulunamadı: {input_path}")
        return

    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', input_path.name)
    if date_match:
        today_str = date_match.group(1)
        base_date = datetime.strptime(today_str, "%Y-%m-%d")
    else:
        logger.error("Girdi dosyasının isminde 'YYYY-MM-DD' formatında bir tarih bulunamadı!")
        return

    out_dir_path = Path(output_dir).resolve() if output_dir else Path(DEFAULT_OUT_DIR)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    category_mapping = _build_category_mapping(out_dir_path)

    df_today = load_and_clean_csv(input_path, category_mapping)
    if df_today is None:
        logger.warning(f"Enflasyon hesaplanamıyor – {today_str} için veri yok, bozuk veya eksik sütunlu.")
        return

    data_dir = input_path.parent

    if compare_file:
        comp_path = Path(compare_file).resolve()
        comp_date_match = re.search(r'(\d{4}-\d{2}-\d{2})', comp_path.name)
        comp_label = comp_date_match.group(1) if comp_date_match else "custom"
        intervals = {comp_label: comp_path}
    else:
        intervals = {}
        prefix = input_path.name.split(today_str)[0]
        suffix = input_path.name.split(today_str)[1]

        for days in [1, 7, 15, 30]:
            past_date_str = (base_date - timedelta(days=days)).strftime("%Y-%m-%d")
            past_file_name = f"{prefix}{past_date_str}{suffix}"
            intervals[f"{days}d"] = data_dir / past_file_name

    summary_row = {'date': today_str}
    detail_base = df_today.copy()
    detail_base['tuik_category'] = detail_base['category'].apply(_safe_tuik_map)

    for label, past_path in intervals.items():
        df_past = load_and_clean_csv(past_path, category_mapping)

        if df_past is None:
            detail_base[f'basic_inflation_{label}'] = None
            summary_row[f'basket_inflation_{label}'] = None
            summary_row[f'avg_inflation_{label}'] = None
            summary_row[f'tuik_weighted_{label}'] = None
            continue

        merged, basic_idx, avg_inf, tuik_w = _compute_metrics(df_today, df_past)

        detail_base = detail_base.merge(
            merged[['id', 'basic_inflation']].rename(columns={'basic_inflation': f'basic_inflation_{label}'}),
            on='id', how='left'
        )

        summary_row[f'basket_inflation_{label}'] = basic_idx
        summary_row[f'avg_inflation_{label}'] = avg_inf
        summary_row[f'tuik_weighted_{label}'] = tuik_w

    detail_file = out_dir_path / f"gurmar_inflation_{today_str}.csv"
    detail_base.to_csv(detail_file, index=False, encoding='utf-8-sig')
    logger.info(f"Detaylı enflasyon verisi kaydedildi: {detail_file}")

    summary_file = out_dir_path / "inflation_summary.csv"
    df_summary = pd.DataFrame([summary_row])

    try:
        if summary_file.exists():
            df_existing = pd.read_csv(summary_file, encoding='utf-8-sig')
            df_existing = df_existing[df_existing['date'] != today_str]
            df_final = pd.concat([df_existing, df_summary], ignore_index=True)
            df_final.to_csv(summary_file, index=False, encoding='utf-8-sig')
        else:
            df_summary.to_csv(summary_file, index=False, encoding='utf-8-sig')
    except Exception as e:
        logger.error(f"Summary dosyası yazılamadı: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gürmar Enflasyon Hesaplayıcı CLI Aracı")
    parser.add_argument("-i", "--input", help="Bugünün fiyatlarını içeren CSV dosyasının yolu")
    parser.add_argument("-o", "--out-dir", help="Çıktıların kaydedileceği klasör", default=None)
    parser.add_argument("-c", "--compare", help="Özel bir karşılaştırma için geçmiş tarihli CSV dosyasının yolu.", default=None)

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    calculate_inflation(args.input, args.out_dir, args.compare)