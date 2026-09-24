"""
monthly_inflation.py — EpeyKatfg month-over-month inflation for every month on record.

Method (standard CPI approach):
  - For each calendar month, each product's monthly price = mean of its daily
    lowest prices in that month (only products observed on >= min_days days).
  - Consecutive months are matched on UrunID (+ same tuik_category).
  - Metrics per month pair (m vs m-1):
      avg_inflation       Carli: mean of per-product relatives
      basic_index         Dutot: (Σp_m / Σp_{m-1} − 1) × 100
      median_inflation_nonzero, pct_increased/decreased/unchanged
      tuik_weighted       two-stage Carli over groups present in the pair,
                          with TÜİK 2026 weights normalised to 100% on the
                          covered set (weights are renormalised because we do
                          not cover all TÜİK groups).
      covered_weight      sum of the TÜİK weights of the groups present
  - Per-group avg / basic / n also reported.
  - Products with |monthly relative| > 80% are treated as scraping artefacts
    and excluded (same threshold as turkey_inflation.py).
  - tuik_weighted only weights a group if it has >= min_group_n matched products;
    under-represented groups are excluded and the covered set renormalised
    (prevents a 1-product high-weight group from swinging the index).

Usage:
    python monthly_inflation.py [--min-days 5]

Output:
    Inflations/Datas/EpeyKatfg/monthly_inflation.csv
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent.parent.parent
sys.path.insert(0, str(_THIS_DIR))
from tuik_config import TUIK_WEIGHTS, normalised_weights  # noqa: E402

DATA_DIR = _PROJECT_ROOT / "InflationItems" / "Datas" / "EpeyKatfg"
OUT = _PROJECT_ROOT / "Inflations" / "Datas" / "EpeyKatfg" / "monthly_inflation.csv"

logger = logging.getLogger(__name__)
_OUTLIER_THRESHOLD = 80.0
_ZERO_CHANGE_TOL = 1e-9


def build_longframe(min_days: int) -> pd.DataFrame:
    """Long frame from the master series.csv via katfg_reader.

    The old per-date CSVs (epeykatfg_YYYY-MM-DD.csv) were retired; katfg_reader
    reproduces their rows exactly (min price per pid/date across range windows).
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "epeykatfg_reader", str(_THIS_DIR / "katfg_reader.py"))
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)

    long = reader.load_frame().rename(columns={"pid": "UrunID", "iso": "date"})
    long = long[["UrunID", "date", "price", "tuik_category"]].copy()
    long["month"] = long["date"].str[:7]
    long["tuik_category"] = long["tuik_category"].fillna("").astype(str).str.strip()
    long = long.dropna(subset=["price"])
    long = long[long["price"] > 0]
    # per-product daily count within month, keep products with enough days
    long["days_in_month"] = long.groupby(["UrunID", "month"])["date"].transform("nunique")
    long = long[long["days_in_month"] >= min_days]
    # monthly mean price per product
    monthly = (
        long.groupby(["UrunID", "tuik_category", "month"], as_index=False)["price"]
        .mean()
        .rename(columns={"price": "month_price"})
    )
    return monthly


def dist_stats(rel: pd.Series) -> dict:
    if rel.empty:
        return {"median_nonzero": None, "pct_increased": None, "pct_decreased": None, "pct_unchanged": None}
    nz = rel[rel.abs() > _ZERO_CHANGE_TOL]
    return {
        "median_nonzero": float(nz.median()) if not nz.empty else None,
        "pct_increased": float((rel > _ZERO_CHANGE_TOL).mean() * 100),
        "pct_decreased": float((rel < -_ZERO_CHANGE_TOL).mean() * 100),
        "pct_unchanged": float((rel.abs() <= _ZERO_CHANGE_TOL).mean() * 100),
    }


def month_pair(m: str, prev: str, monthly: pd.DataFrame, min_group_n: int = 20) -> dict | None:
    cur = monthly[monthly["month"] == m][["UrunID", "tuik_category", "month_price"]]
    past = monthly[monthly["month"] == prev][["UrunID", "tuik_category", "month_price"]].rename(
        columns={"month_price": "past_price"})
    merged = cur.merge(past, on=["UrunID", "tuik_category"], how="inner")
    if merged.empty:
        return None
    merged["relative"] = (merged["month_price"] / merged["past_price"] - 1) * 100
    merged["relative"] = merged["relative"].replace([float("inf"), float("-inf")], pd.NA)
    merged.loc[merged["relative"].abs() > _OUTLIER_THRESHOLD, "relative"] = pd.NA
    valid = merged[merged["relative"].notna()]
    if valid.empty:
        return None

    basic = float((valid["month_price"].sum() / valid["past_price"].sum() - 1) * 100)
    avg = float(valid["relative"].mean())
    median = float(valid["relative"].median())
    ds = dist_stats(valid["relative"])

    # Only weight groups with enough matched products (small-sample guard)
    n_per_group = valid.groupby("tuik_category")["relative"].count()
    present = [c for c in n_per_group.index
               if c in TUIK_WEIGHTS and int(n_per_group[c]) >= min_group_n]
    cat_rel = valid[valid["tuik_category"].isin(present)].groupby("tuik_category")["relative"].mean()
    norm_w = normalised_weights(present)
    tuik_w = float(sum(cat_rel[c] * norm_w[c] / 100.0 for c in norm_w if pd.notna(cat_rel.get(c)))) if norm_w else None
    covered = sum(TUIK_WEIGHTS[c]["weight"] for c in present)

    row = {
        "month": m, "prev_month": prev, "n_matched": len(valid),
        "avg_inflation": avg, "basic_index": basic,
        "median_inflation_nonzero": ds["median_nonzero"],
        "pct_increased": ds["pct_increased"], "pct_decreased": ds["pct_decreased"],
        "pct_unchanged": ds["pct_unchanged"],
        "tuik_weighted": tuik_w, "covered_weight": round(covered, 3),
        "groups": ",".join(sorted(present)),
    }
    for code, grp in valid.groupby("tuik_category"):
        if code not in TUIK_WEIGHTS:
            continue
        s_basic = float((grp["month_price"].sum() / grp["past_price"].sum() - 1) * 100)
        row[f"n_{code}"] = int(len(grp))
        row[f"avg_{code}"] = float(grp["relative"].mean())
        row[f"basic_{code}"] = s_basic
    return row


def main(min_days: int, min_group_n: int = 20) -> None:
    logger.info("Building monthly averages (min_days=%d) …", min_days)
    monthly = build_longframe(min_days)
    months = sorted(monthly["month"].unique())
    logger.info("Months: %s .. %s", months[0], months[-1])

    rows = []
    for i in range(1, len(months)):
        row = month_pair(months[i], months[i - 1], monthly, min_group_n)
        if row is not None:
            rows.append(row)

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8")
    logger.info("Wrote %d month pairs -> %s", len(df), OUT)

    pd.set_option("display.width", 200)
    show = df[["month", "prev_month", "n_matched", "avg_inflation", "basic_index",
               "tuik_weighted", "covered_weight", "groups"]].copy()
    for c in ["avg_inflation", "basic_index", "tuik_weighted"]:
        show[c] = show[c].round(3)
    print(show.to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-days", type=int, default=5)
    ap.add_argument("--min-group-n", type=int, default=20)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main(args.min_days, args.min_group_n)
