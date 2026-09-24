"""detail_store.py — one consolidated long-format CSV per dataset for inflation calculators.

Each sector calculator used to emit one detail file per run date:
    gurmar_inflation_2026-09-02.csv, vakko_inflation_2026-03-06.csv, ...
Since nothing consumes those per-date files, they are consolidated into a single
long-format CSV per dataset (see scripts/consolidate_inflation_details.py for the
history merge).  Sector calculators call append_detail() here so future runs append
their rows to the consolidated file instead of creating yet another dated file.

Unified column layout (same as the consolidated files, modelled on the leanest
existing format, EpeyKatfg's):

    date, product_id, product_name, category, tuik_category, price,
    relative_1d, relative_7d, relative_15d, relative_30d [, <dataset extras>]

append_detail() is idempotent per date: if a run is repeated for the same date,
the previously appended rows for that date are replaced, and rows are deduplicated
per (date, product_id, price) so writer bugs that emit duplicate/exploded rows do
not accumulate in the store.
"""
import os
import pandas as pd

CORE = ["date", "product_id", "product_name", "category", "tuik_category", "price",
        "relative_1d", "relative_7d", "relative_15d", "relative_30d"]

# Per store: ordered candidate source columns for each core field (schemas
# drifted over time, first existing column wins), plus dataset-specific extras.
STORE_SCHEMAS = {
    "gurmar_inflation.csv": {
        "candidates": {
            "product_id":   ["product_id", "id"],
            "product_name": ["product_id", "id", "name"],
            "category":     ["category"],
            "tuik_category": ["tuik_category"],
            "price":        ["shown_price", "price"],
            "relative_1d":  ["basic_inflation_1d", "relative_1d"],
            "relative_7d":  ["basic_inflation_7d", "relative_7d"],
            "relative_15d": ["basic_inflation_15d", "relative_15d"],
            "relative_30d": ["basic_inflation_30d", "relative_30d"],
        },
        "extras": ["url", "eski_fiyat"],
    },
    "vakko_inflation.csv": {
        "candidates": {
            "product_id":   ["Stok Kodu", "product_id"],
            "product_name": ["product-name", "product_name"],
            "category":     ["Ana Kategori", "category"],
            "tuik_category": ["tuik_category"],
            "price":        ["Fiyat", "price"],
            "relative_1d":  ["basic_inflation_1d", "relative_1d"],
            "relative_7d":  ["basic_inflation_7d", "relative_7d"],
            "relative_15d": ["basic_inflation_15d", "relative_15d"],
            "relative_30d": ["basic_inflation_30d", "relative_30d"],
        },
        "extras": ["Kategori ID"],
    },
    "watsons_inflation.csv": {
        "candidates": {
            "product_id":   ["id", "product_id"],
            "product_name": ["name", "product_name"],
            "category":     ["category"],
            "tuik_category": ["tuik_category"],
            "price":        ["price", "shown_price"],
            "relative_1d":  ["basic_inflation_1d", "relative_1d"],
            "relative_7d":  ["basic_inflation_7d", "relative_7d"],
            "relative_15d": ["basic_inflation_15d", "relative_15d"],
            "relative_30d": ["basic_inflation_30d", "relative_30d"],
        },
        "extras": [],
    },
    "chakra_inflation.csv": {
        "candidates": {
            "product_id":   ["id", "product_id"],
            "product_name": ["name", "product_name"],
            "category":     ["category"],
            "tuik_category": ["tuik_category"],
            "price":        ["price", "shown_price"],
            "relative_1d":  ["basic_inflation_1d", "relative_1d"],
            "relative_7d":  ["basic_inflation_7d", "relative_7d"],
            "relative_15d": ["basic_inflation_15d", "relative_15d"],
            "relative_30d": ["basic_inflation_30d", "relative_30d"],
        },
        "extras": ["url"],
    },
    "yapimaks_detailed_inf.csv": {
        "candidates": {
            "product_id":   ["product_id", "id"],
            "product_name": ["product_name", "product_id"],
            "category":     ["category"],
            "tuik_category": ["tuik_code", "tuik_category"],
            "price":        ["price"],
            "relative_1d":  ["basic_inflation_1d", "relative_1d"],
            "relative_7d":  ["basic_inflation_7d", "relative_7d"],
            "relative_15d": ["basic_inflation_15d", "relative_15d"],
            "relative_30d": ["basic_inflation_30d", "relative_30d"],
        },
        "extras": [],
    },
    "Kayseri_inflation.csv": {
        "candidates": {
            "product_name": ["District", "product_name"],
            "category":     ["category"],
            "tuik_category": ["tuik_category"],
            "price":        ["median_price", "price"],
            "relative_1d":  ["basic_inflation_1d", "relative_1d"],
            "relative_7d":  ["basic_inflation_7d", "relative_7d"],
            "relative_15d": ["basic_inflation_15d", "relative_15d"],
            "relative_30d": ["basic_inflation_30d", "relative_30d"],
        },
        "extras": ["Rooms"],
        "composite": ["product_name", "Rooms"],
    },
    "Sivas_inflation.csv": {
        "candidates": {
            "product_name": ["District", "product_name"],
            "category":     ["category"],
            "tuik_category": ["tuik_category"],
            "price":        ["median_price", "price"],
            "relative_1d":  ["basic_inflation_1d", "relative_1d"],
            "relative_7d":  ["basic_inflation_7d", "relative_7d"],
            "relative_15d": ["basic_inflation_15d", "relative_15d"],
            "relative_30d": ["basic_inflation_30d", "relative_30d"],
        },
        "extras": ["Rooms"],
        "composite": ["product_name", "Rooms"],
    },
    "Tokat_inflation.csv": {
        "candidates": {
            "product_name": ["District", "product_name"],
            "category":     ["category"],
            "tuik_category": ["tuik_category"],
            "price":        ["median_price", "price"],
            "relative_1d":  ["basic_inflation_1d", "relative_1d"],
            "relative_7d":  ["basic_inflation_7d", "relative_7d"],
            "relative_15d": ["basic_inflation_15d", "relative_15d"],
            "relative_30d": ["basic_inflation_30d", "relative_30d"],
        },
        "extras": ["Rooms"],
        "composite": ["product_name", "Rooms"],
    },
    "epeykatfg_inflation.csv": {
        "candidates": {
            "product_id":   ["urun_id", "product_id"],
            "product_name": ["product_name"],
            "category":     ["category"],
            "tuik_category": ["tuik_category"],
            "price":        ["price"],
            "relative_1d":  ["relative_1d"],
            "relative_7d":  ["relative_7d"],
            "relative_15d": ["relative_15d"],
            "relative_30d": ["relative_30d"],
        },
        "extras": [],
    },
    "turkey_inflation.csv": {
        "candidates": {
            "product_id":   ["product_key", "product_id"],
            "product_name": ["canonical_key", "product_name"],
            "category":     ["store", "category"],
            "tuik_category": ["tuik_category"],
            "price":        ["price"],
            "relative_1d":  ["relative_1d"],
            "relative_7d":  ["relative_7d"],
            "relative_15d": ["relative_15d"],
            "relative_30d": ["relative_30d"],
        },
        "extras": ["sector"],
    },
}


def _pick(df, candidates):
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series(pd.NA, index=df.index, dtype="object")


def normalise_frame(df, store_name, date_str):
    """Map a calculator's detail DataFrame to the unified store layout."""
    schema = STORE_SCHEMAS.get(store_name)
    if schema is None:
        raise ValueError(f"no schema registered for store {store_name!r}")
    out = pd.DataFrame(index=df.index)
    out["date"] = date_str
    for c in CORE[1:]:
        out[c] = _pick(df, schema["candidates"].get(c, [c]))
    for e in schema["extras"]:
        out[e] = df[e] if e in df.columns else pd.NA
    if schema.get("composite"):
        left, right = schema["composite"]
        out["product_id"] = (out[left].fillna("").astype(str) + " | "
                             + out[right].fillna("").astype(str))
    return out


def append_detail(out_dir, store_name, date_str, df):
    """Append (or replace, per date) the calculator's rows in the store file.

    Idempotent: rows for the same date are replaced, not duplicated.
    """
    store_path = os.path.join(out_dir, store_name)
    new = normalise_frame(df.reset_index(drop=True), store_name, date_str)

    if os.path.exists(store_path) and os.path.getsize(store_path) > 0:
        old = pd.read_csv(store_path, encoding="utf-8", dtype=str, on_bad_lines="skip")
        old = old[old["date"] != date_str]  # drop same-date rows -> replace
        merged = pd.concat([old, new], ignore_index=True)
    else:
        merged = new

    # writer-bug guard: one row per (date, product_id, price); previous appends
    # were already replaced for this date, so merely drop any duplicate rows
    merged = merged.drop_duplicates(subset=["date", "product_id", "price"], keep="first")
    merged = merged.sort_values(["date", "product_id"], kind="stable")
    merged.to_csv(store_path, index=False, encoding="utf-8")
