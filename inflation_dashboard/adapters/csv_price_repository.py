from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import time

import pandas as pd

from inflation_dashboard.domain.prices import HISTORY_COLUMNS, PRICE_COLUMNS, build_product_frame, parse_date_from_name

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_ROOT = PROJECT_ROOT / "Datas"

SUPPORTED_RETAILERS = {
    "ClothingStores / Vakko",
    "Markets / Gurmar",
    "HomeGoods",
    "Technology",
    "Cosmetics / Watson",
    "ConstructionSuppliesMarkets / TasciYapiMarket",
    "ConstructionSuppliesMarkets / yapimaks",
    "HousesRent / Kayseri",
    "HousesRent / Sivas",
    "HousesRent / Tokat",
}

DEFAULT_RETAILERS = (
    "Markets / Gurmar",
    "ClothingStores / Vakko",
    "HomeGoods",
)
DEFAULT_MAX_FILES_PER_RETAILER = 45

# --- Per-file parsed-frame cache -------------------------------------------------
# Re-reading and re-building the same CSVs on every API request is the dominant
# cost (one rerun fires ~5 overlapping data requests). Cache the *built product
# frame* per file, keyed on path + mtime + size, so overlapping filter sets
# (options vs product detail vs date-range tweaks) reuse parsed files.

_MAX_CACHED_FILES = 512
_FILE_CACHE_TTL_SECONDS = 600
_MAX_CACHED_FRAME_ROWS = 200_000

_file_frame_cache: "OrderedDict[str, tuple[float, pd.DataFrame]]" = OrderedDict()


def _file_cache_key(csv_path: Path) -> str | None:
    try:
        stat = csv_path.stat()
    except OSError:
        return None
    return f"{csv_path}|{stat.st_mtime_ns}|{stat.st_size}"


def _cache_product_frame(key: str, frame: pd.DataFrame) -> None:
    if frame.empty or len(frame) > _MAX_CACHED_FRAME_ROWS:
        return
    now = time.monotonic()
    _file_frame_cache[key] = (now, frame)
    _file_frame_cache.move_to_end(key)
    while len(_file_frame_cache) > _MAX_CACHED_FILES:
        _file_frame_cache.popitem(last=False)
    for stale_key in [k for k, (ts, _) in _file_frame_cache.items() if now - ts > _FILE_CACHE_TTL_SECONDS]:
        del _file_frame_cache[stale_key]


def _cached_product_frame(key: str) -> pd.DataFrame | None:
    entry = _file_frame_cache.get(key)
    if entry is None:
        return None
    timestamp, frame = entry
    if time.monotonic() - timestamp > _FILE_CACHE_TTL_SECONDS:
        del _file_frame_cache[key]
        return None
    return frame


def clear_price_cache() -> None:
    """Clear the per-file frame cache (new or changed scraped CSVs)."""

    _file_frame_cache.clear()


def detect_retailer(path: Path) -> str:
    parts = path.parts
    if "Datas" not in parts:
        return path.parent.name

    relative_parts = parts[parts.index("Datas") + 1 : -1]
    if not relative_parts:
        return path.parent.name
    if len(relative_parts) == 1:
        return relative_parts[0]
    return " / ".join(relative_parts)


def discover_csv_inventory(raw_data_root: Path = RAW_DATA_ROOT) -> pd.DataFrame:
    rows = []
    for csv_path in raw_data_root.rglob("*.csv"):
        retailer = detect_retailer(csv_path)
        date_value = parse_date_from_name(csv_path.name)
        if retailer not in SUPPORTED_RETAILERS or pd.isna(date_value):
            continue

        rows.append(
            {
                "path": str(csv_path),
                "retailer": retailer,
                "date": date_value,
                "size_mb": csv_path.stat().st_size / 1024 / 1024,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["path", "retailer", "date", "size_mb"])

    return pd.DataFrame(rows).sort_values(["retailer", "date"])


def load_price_history(
    selected_retailers: tuple[str, ...],
    start_date,
    end_date,
    max_files_per_retailer: int,
    inventory: pd.DataFrame | None = None,
    project_root: Path = PROJECT_ROOT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    skipped: list[dict[str, object]] = []

    if inventory is None:
        inventory = discover_csv_inventory()
    if inventory.empty or not selected_retailers:
        return pd.DataFrame(columns=HISTORY_COLUMNS), pd.DataFrame(columns=["file", "reason"])

    selected_files = inventory[
        inventory["retailer"].isin(selected_retailers)
        & (inventory["date"] >= pd.to_datetime(start_date))
        & (inventory["date"] <= pd.to_datetime(end_date))
    ].copy()

    if max_files_per_retailer > 0:
        selected_files = (
            selected_files.sort_values(["retailer", "date"], ascending=[True, False])
            .groupby("retailer", group_keys=False)
            .head(max_files_per_retailer)
            .sort_values(["retailer", "date"])
        )

    for file_info in selected_files.itertuples(index=False):
        csv_path = Path(file_info.path)
        retailer = file_info.retailer
        date_value = file_info.date

        cache_key = _file_cache_key(csv_path)
        cached_product_data = _cached_product_frame(cache_key) if cache_key else None
        if cached_product_data is not None:
            rows.append(cached_product_data)
            continue

        try:
            frame = pd.read_csv(
                csv_path,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
                on_bad_lines="skip",
            )
        except Exception as exc:
            skipped.append({"file": str(csv_path.relative_to(project_root)), "reason": str(exc)})
            continue

        if frame.empty:
            skipped.append({"file": str(csv_path.relative_to(project_root)), "reason": "empty file"})
            continue

        price_column = next((column for column in PRICE_COLUMNS if column in frame.columns), None)
        if not price_column:
            skipped.append({"file": str(csv_path.relative_to(project_root)), "reason": "no recognized price column"})
            continue

        product_data = build_product_frame(
            frame=frame,
            retailer=retailer,
            price_column=price_column,
            date_value=date_value,
            source_file=str(csv_path.relative_to(project_root)),
        )
        if not product_data.empty:
            rows.append(product_data)
            if cache_key is not None:
                _cache_product_frame(cache_key, product_data)

    history = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=HISTORY_COLUMNS)
    skipped_df = pd.DataFrame(skipped, columns=["file", "reason"])

    if history.empty:
        return history, skipped_df

    history = (
        history.drop_duplicates(subset=["date", "retailer", "product_id"], keep="last")
        .sort_values(["retailer", "product_name", "date"])
        .reset_index(drop=True)
    )
    return history[HISTORY_COLUMNS], skipped_df
