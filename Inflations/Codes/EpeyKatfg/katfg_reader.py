"""katfg_reader.py — dense per-(product, date) reader for the EpeyKatfg calculators.

The per-date materialized CSVs (InflationItems/Datas/EpeyKatfg/epeykatfg_YYYY-MM-DD.csv)
were retired (archived in /epeykatfg_daily_csvs.zip). Their content is derivable 1:1
from the master harvest file series.csv (url, category, pid, date, price_tl, range_id)
by collapsing overlapping range windows to the minimum price per (pid, date) — the same
collapse materialize.py applied. The master file is loaded once per process (cached) and
per-date snapshots are served from it.

This keeps the calculators byte-equivalent to the old per-date CSVs: a product appears on
a date only on days it was actually observed (the sparse prices_json/EpeyKatfg.json store
cannot express that, since unchanged days carry no entry).
"""
import importlib.util
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root
_SERIES_CSV = os.path.join(_ROOT, "InflationItems", "Datas", "EpeyKatfg", "series.csv")
_TUIK_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tuik_config.py")

_frame = None


def _tuik_map():
    spec = importlib.util.spec_from_file_location("epey_tuik_config", _TUIK_CONFIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.EPEY_CATEGORY_TO_TUIK


def _name_from_url(url: str, pid) -> str:
    if "/" in url:
        return url.split("/")[4].replace(".html", "").replace("-", " ")
    return str(pid)


def load_frame() -> pd.DataFrame:
    """Master long frame: pid, iso (YYYY-MM-DD), price (min per pid/date),
    product_name, tuik_category. One row per observed (product, date)."""
    global _frame
    if _frame is not None:
        return _frame
    cat_map = _tuik_map()
    df = pd.read_csv(_SERIES_CSV, encoding="utf-8", dtype=str, on_bad_lines="skip",
                     names=["url", "category", "pid", "date", "price_tl", "range_id"], header=0)
    df = df.dropna(subset=["date", "price_tl"])
    df["iso"] = df["date"].str[-4:] + "-" + df["date"].str[3:5] + "-" + df["date"].str[:2]
    df["price"] = pd.to_numeric(df["price_tl"], errors="coerce")
    sub = df[["pid", "iso", "url", "category", "price"]]
    sub = sub.groupby(["pid", "iso"], as_index=False).agg(
        price=("price", "min"), url=("url", "first"), category=("category", "first"))
    sub["product_name"] = [_name_from_url(u, p) for u, p in zip(sub["url"], sub["pid"])]
    sub["tuik_category"] = sub["category"].map(cat_map).fillna("")
    sub = sub[sub["price"] > 0]
    sub = sub[sub["product_name"] != ""]
    _frame = sub.reset_index(drop=True)
    return _frame


def snapshot(date_str: str) -> pd.DataFrame | None:
    """All products observed on `date_str` (YYYY-MM-DD) with their price that day.

    Columns: urun_id, product_name, price, tuik_category (mirrors the old
    epeykatfg_%s.csv layout). Returns None when no data exists for the date.
    """
    frame = load_frame()
    sub = frame[frame["iso"] == date_str].copy()
    if sub.empty:
        return None
    out = sub.rename(columns={"pid": "urun_id"})[["urun_id", "product_name", "price", "tuik_category"]]
    return out.reset_index(drop=True)
