from __future__ import annotations

import pandas as pd


def list_inventory_filters(inventory: pd.DataFrame) -> dict[str, object]:
    if inventory.empty:
        return {"retailers": [], "min_date": None, "max_date": None, "file_count": 0}

    return {
        "retailers": sorted(inventory["retailer"].dropna().unique().tolist()),
        "min_date": inventory["date"].min(),
        "max_date": inventory["date"].max(),
        "file_count": len(inventory),
    }


def get_product_history(history: pd.DataFrame, retailer: str, product_name: str) -> pd.DataFrame:
    product_history = history[
        history["retailer"].eq(retailer) & history["product_name"].eq(product_name)
    ].copy()
    return product_history.sort_values("date")


def summarize_product_history(product_history: pd.DataFrame) -> dict[str, object]:
    if product_history.empty:
        return {
            "latest_price": None,
            "cheapest_price": None,
            "cheapest_date": None,
            "change_since_first_pct": 0.0,
        }

    cheapest_row = product_history.loc[product_history["price"].idxmin()]
    latest_row = product_history.iloc[-1]
    first_row = product_history.iloc[0]
    first_price = first_row["price"]
    change_since_first = ((latest_row["price"] - first_price) / first_price * 100) if first_price else 0.0

    return {
        "latest_price": latest_row["price"],
        "cheapest_price": cheapest_row["price"],
        "cheapest_date": cheapest_row["date"],
        "change_since_first_pct": change_since_first,
    }


def calculate_retailer_average_trends(
    history: pd.DataFrame,
    selected_retailers: list[str],
    aggregation: str,
) -> pd.DataFrame:
    filtered = history[history["retailer"].isin(selected_retailers)].copy()
    if filtered.empty:
        return pd.DataFrame(columns=["date", "retailer", "price"])

    grouped = filtered.groupby(["date", "retailer"], as_index=False)["price"]
    if aggregation == "Median":
        result = grouped.median()
    else:
        result = grouped.mean()
    return result.sort_values(["retailer", "date"])


def calculate_price_movers(
    history: pd.DataFrame,
    selected_retailer: str,
    mover_count: int,
) -> dict[str, pd.DataFrame]:
    movers = history.copy()
    if selected_retailer != "All retailers":
        movers = movers[movers["retailer"] == selected_retailer]

    empty = pd.DataFrame()
    if movers.empty:
        return {"biggest_drops": empty, "biggest_gains": empty, "stats": empty}

    stats = (
        movers.groupby(["retailer", "product_id", "product_name", "category"], as_index=False)
        .agg(
            first_seen=("date", "min"),
            last_seen=("date", "max"),
            first_price=("price", "first"),
            latest_price=("price", "last"),
            min_price=("price", "min"),
            max_price=("price", "max"),
            observations=("price", "size"),
        )
    )
    stats = stats[stats["observations"] >= 2].copy()
    if stats.empty:
        return {"biggest_drops": stats, "biggest_gains": stats, "stats": stats}

    stats["change_since_first_pct"] = ((stats["latest_price"] - stats["first_price"]) / stats["first_price"]) * 100
    stats["drop_from_peak_pct"] = ((stats["latest_price"] - stats["max_price"]) / stats["max_price"]) * 100
    stats["savings_vs_peak"] = stats["max_price"] - stats["latest_price"]

    return {
        "biggest_drops": stats.sort_values("drop_from_peak_pct").head(mover_count),
        "biggest_gains": stats.sort_values("change_since_first_pct", ascending=False).head(mover_count),
        "stats": stats,
    }


def calculate_coverage_summary(history: pd.DataFrame, skipped: pd.DataFrame) -> dict[str, object]:
    if history.empty:
        return {
            "retailer_count": 0,
            "product_count": 0,
            "observation_count": 0,
            "date_range": "-",
            "skipped_file_count": len(skipped),
        }

    return {
        "retailer_count": history["retailer"].nunique(),
        "product_count": history["product_id"].nunique(),
        "observation_count": len(history),
        "date_range": f"{history['date'].min():%Y-%m-%d} → {history['date'].max():%Y-%m-%d}",
        "skipped_file_count": len(skipped),
    }


def calculate_coverage_over_time(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=["date", "retailer", "tracked_products"])

    return (
        history.groupby(["date", "retailer"], as_index=False)["product_id"]
        .nunique()
        .rename(columns={"product_id": "tracked_products"})
    )


def calculate_category_coverage(history: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=["retailer", "category", "products"])

    return (
        history.groupby(["retailer", "category"], as_index=False)["product_id"]
        .nunique()
        .rename(columns={"product_id": "products"})
        .sort_values("products", ascending=False)
        .head(limit)
    )
