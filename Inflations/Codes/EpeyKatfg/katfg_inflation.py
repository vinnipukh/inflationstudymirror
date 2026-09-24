"""
katfg_inflation.py — EpeyKatfg sector inflation calculator
(Layer 2, docs/site-analysis/katfg-harness-plan.md)

Reads per-(product, date) snapshots reconstructed from the master harvest file
(InflationItems/Datas/EpeyKatfg/series.csv, via katfg_reader.py — same min-price
collapse that materialize.py applied to the retired per-date CSVs) and computes
per-interval inflation metrics for the sector:

  avg_inflation    – Carli: arithmetic mean of per-product price relatives
  basic_index      – Dutot: (Σp_t / Σp_0 − 1) × 100
  median_inflation – median of per-product relatives (0% dominates)
  median_inflation_nonzero / pct_increased / pct_decreased / pct_unchanged
  tuik_weighted    – two-stage Carli: unweighted per-group means, weighted by
                     TÜİK 2026 weights normalised over the groups present
                     (EpeyKatfg spans 03/05/06/07/08/09/13)

Products are matched on UrunID (the stable epey product ID); prices are epey's
daily lowest offer in nominal TL. Price relatives with |change| > 80% are
treated as scraping artefacts (same threshold as turkey_inflation.py).

Outputs (Inflations/Datas/EpeyKatfg/):
  epeykatfg_inflation.csv     – one consolidated per-product detail file (date,
                                product_id, product_name, price, tuik_category,
                                relative_1d/7d/15d/30d), appended per run
  inflation_summary.csv       – one row per (date, compare_date)

Usage:
    python katfg_inflation.py                       # today, 1d/7d/15d/30d
    python katfg_inflation.py --date 2026-09-06
    python katfg_inflation.py --date 2026-09-06 --compare 2026-08-07
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
_THIS_DIR     = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent.parent.parent       # inflationstudymirror

sys.path.insert(0, str(_THIS_DIR))
from tuik_config import TUIK_WEIGHTS, normalised_weights  # noqa: E402
sys.path.insert(0, str(_PROJECT_ROOT / "Inflations" / "Codes"))
from detail_store import append_detail  # noqa: E402

DATA_DIR = _PROJECT_ROOT / "InflationItems" / "Datas" / "EpeyKatfg"
INFLATION_OUT_DIR = _PROJECT_ROOT / "Inflations" / "Datas" / "EpeyKatfg"

logger = logging.getLogger(__name__)

_OUTLIER_THRESHOLD = 80.0   # |relative| > 80% → scraping artefact
_ZERO_CHANGE_TOL = 1e-9


def _to_float(x) -> float | None:
    """Parse a price from the materialized CSVs (bare float strings, or
    Turkish formats as a fallback)."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace("₺", "").replace("TL", "").replace("TRY", "").strip()
    if not s:
        return None
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        pass
    if "," in s and "." in s:
        if s.index(".") < s.index(","):      # "1.234,56"
            s = s.replace(".", "").replace(",", ".")
        else:                                 # "1,234.56"
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        return None


_READER_DIR = _PROJECT_ROOT / "Inflations" / "Codes" / "EpeyKatfg"


def _load_csv(date_str: str) -> pd.DataFrame | None:
    """Load the per-(product, date) snapshot from the master series.csv.

    The old per-date CSVs (epeykatfg_YYYY-MM-DD.csv) were retired; their content
    is reproduced exactly from series.csv via katfg_reader (min price per pid/date
    across range windows). Columns mirror the old files:
    urun_id, product_name, price, tuik_category.
    """
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(
            "epeykatfg_reader", str(_READER_DIR / "katfg_reader.py"))
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        out = reader.snapshot(date_str)
        if out is None or out.empty:
            logger.info("No EpeyKatfg data for %s", date_str)
            return None
        return out
    except Exception as e:
        logger.error("Failed to load EpeyKatfg snapshot for %s: %s", date_str, e)
        return None


def _dist_stats(rel: pd.Series) -> dict:
    if rel.empty:
        return {"median_nonzero": None, "pct_increased": None, "pct_decreased": None, "pct_unchanged": None}
    nonzero = rel[rel.abs() > _ZERO_CHANGE_TOL]
    return {
        "median_nonzero": float(nonzero.median()) if not nonzero.empty else None,
        "pct_increased": float((rel > _ZERO_CHANGE_TOL).mean() * 100),
        "pct_decreased": float((rel < -_ZERO_CHANGE_TOL).mean() * 100),
        "pct_unchanged": float((rel.abs() <= _ZERO_CHANGE_TOL).mean() * 100),
    }


def _compute_metrics(df_current: pd.DataFrame, df_past: pd.DataFrame):
    """Match current vs past on UrunID and compute sector + per-group metrics."""
    if df_past.empty:
        return None
    merged = df_current.merge(
        df_past[["urun_id", "price"]].rename(columns={"price": "past_price"}),
        on="urun_id", how="inner",
    )
    if merged.empty:
        return None

    merged["relative"] = (merged["price"] / merged["past_price"] - 1) * 100
    merged["relative"] = merged["relative"].replace([float("inf"), float("-inf")], pd.NA)

    # Outlier filter (scraping artefacts)
    n_before = merged["relative"].notna().sum()
    merged.loc[merged["relative"].abs() > _OUTLIER_THRESHOLD, "relative"] = pd.NA
    merged.loc[merged["relative"].isna(), ["price", "past_price"]] = pd.NA
    n_dropped = n_before - merged["relative"].notna().sum()
    if n_dropped:
        logger.info("  Outlier filter: dropped %d product pairs (|change| > %.0f%%)", n_dropped, _OUTLIER_THRESHOLD)

    valid = merged[merged["relative"].notna()]
    basic_index = float((valid["price"].sum() / valid["past_price"].sum() - 1) * 100) if valid["past_price"].sum() else None
    avg = float(valid["relative"].mean()) if not valid.empty else None
    median = float(valid["relative"].median()) if not valid.empty else None
    dist = _dist_stats(valid["relative"])

    # Per-group metrics (matched products)
    group_metrics: dict[str, dict] = {}
    for code, grp in valid.groupby("tuik_category"):
        s_basic = float((grp["price"].sum() / grp["past_price"].sum() - 1) * 100)
        group_metrics[str(code)] = {
            "avg_inflation": float(grp["relative"].mean()),
            "basic_index": s_basic,
            "median_inflation": float(grp["relative"].median()),
            "median_inflation_nonzero": _dist_stats(grp["relative"])["median_nonzero"],
            "n_matched": int(len(grp)),
        }

    # TÜİK-weighted two-stage Carli over present groups
    cat_rel = valid.groupby("tuik_category")["relative"].mean()
    present_codes = [c for c in cat_rel.index if c in TUIK_WEIGHTS]
    norm_w = normalised_weights(present_codes)
    tuik_weighted = (
        float(sum(cat_rel[c] * norm_w[c] / 100.0 for c in norm_w if pd.notna(cat_rel.get(c))))
        if norm_w else None
    )

    return {
        "detail": merged,
        "basic_index": basic_index,
        "avg_inflation": avg,
        "median_inflation": median,
        "median_inflation_nonzero": dist["median_nonzero"],
        "pct_increased": dist["pct_increased"],
        "pct_decreased": dist["pct_decreased"],
        "pct_unchanged": dist["pct_unchanged"],
        "tuik_weighted": tuik_weighted,
        "group_metrics": group_metrics,
        "n_matched": len(valid),
    }


def calculate_inflation(target_date: str | None = None, compare_date: str | None = None) -> None:
    base_date = datetime.strptime(target_date, "%Y-%m-%d") if target_date else datetime.today()
    today_str = base_date.strftime("%Y-%m-%d")

    df_today = _load_csv(today_str)
    if df_today is None:
        logger.warning("Cannot calculate EpeyKatfg inflation — no data for %s.", today_str)
        return

    INFLATION_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if compare_date:
        intervals = {compare_date: compare_date}
    else:
        intervals = {}
        for days in [1, 7, 15, 30]:
            past_str = (base_date - timedelta(days=days)).strftime("%Y-%m-%d")
            intervals[f"{days}d"] = past_str

    summary_row = {"date": today_str, "compare_date": compare_date or min(intervals.values()),
                   "n_products_current": int(len(df_today))}
    detail_base = df_today[["urun_id", "product_name", "price", "tuik_category"]].copy()

    for label, past_str in intervals.items():
        df_past = _load_csv(past_str)
        res = _compute_metrics(df_today, df_past) if df_past is not None else None

        if res is None:
            summary_row[f"n_matched_{label}"] = None
            for key in ["avg_inflation", "basic_index", "median_inflation",
                        "median_inflation_nonzero", "pct_increased", "pct_decreased",
                        "pct_unchanged", "tuik_weighted"]:
                summary_row[f"{key}_{label}"] = None
            continue

        rel = res["detail"][["urun_id", "relative"]].rename(columns={"relative": f"relative_{label}"})
        detail_base = detail_base.merge(rel, on="urun_id", how="left")

        summary_row[f"n_matched_{label}"] = res["n_matched"]
        for key in ["avg_inflation", "basic_index", "median_inflation",
                    "median_inflation_nonzero", "pct_increased", "pct_decreased",
                    "pct_unchanged", "tuik_weighted"]:
            summary_row[f"{key}_{label}"] = res[key]

        for code, gm in res["group_metrics"].items():
            summary_row[f"n_matched_{code}_{label}"] = gm["n_matched"]
            summary_row[f"avg_inflation_{code}_{label}"] = gm["avg_inflation"]
            summary_row[f"basic_index_{code}_{label}"] = gm["basic_index"]
            summary_row[f"median_inflation_{code}_{label}"] = gm["median_inflation"]
            summary_row[f"median_inflation_nonzero_{code}_{label}"] = gm["median_inflation_nonzero"]

        logger.info(
            "  [%s vs %s] n_matched=%s avg=%.3f%% basic=%.3f%% tuik_weighted=%s",
            today_str, past_str, res["n_matched"],
            res["avg_inflation"] if res["avg_inflation"] is not None else float("nan"),
            res["basic_index"] if res["basic_index"] is not None else float("nan"),
            f"{res['tuik_weighted']:.3f}%" if res["tuik_weighted"] is not None else "N/A",
        )

    # ── Save detail ──────────────────────────────────────────────────────────
    append_detail(INFLATION_OUT_DIR, "epeykatfg_inflation.csv", today_str, detail_base)
    logger.info("Saved detailed inflation data: epeykatfg_inflation.csv (%s)", today_str)

    # ── Save / update summary ────────────────────────────────────────────────
    summary_file = INFLATION_OUT_DIR / "inflation_summary.csv"
    df_new = pd.DataFrame([summary_row])
    try:
        if summary_file.exists():
            df_existing = pd.read_csv(summary_file)
            same = (df_existing["date"] == today_str) & (
                df_existing["compare_date"].astype(str) == str(summary_row["compare_date"])
            )
            df_existing = df_existing[~same]
            df_final = pd.concat([df_existing, df_new], ignore_index=True).sort_values("date").reset_index(drop=True)
            df_final.to_csv(summary_file, index=False, encoding="utf-8")
        else:
            df_new.to_csv(summary_file, index=False, encoding="utf-8")
        logger.info("Updated summary: %s", summary_file)
    except Exception as e:
        logger.error("Failed to write summary: %s", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EpeyKatfg sector inflation calculator")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD")
    parser.add_argument("--compare", default=None, help="Comparison date YYYY-MM-DD")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    calculate_inflation(args.date, args.compare)
