from __future__ import annotations

PRODUCT_HISTORY_COLUMNS = ["date", "price", "category", "source_file"]
RETAILER_AVERAGE_COLUMNS = ["date", "retailer", "price"]
BIGGEST_DROPS_COLUMNS = [
    "retailer",
    "product_name",
    "latest_price",
    "max_price",
    "savings_vs_peak",
    "drop_from_peak_pct",
    "last_seen",
]
BIGGEST_GAINS_COLUMNS = [
    "retailer",
    "product_name",
    "first_price",
    "latest_price",
    "change_since_first_pct",
    "first_seen",
    "last_seen",
]
SKIPPED_DIAGNOSTICS_COLUMNS = ["file", "reason"]
COVERAGE_OVER_TIME_COLUMNS = ["date", "retailer", "tracked_products"]
CATEGORY_COVERAGE_COLUMNS = ["retailer", "category", "products"]


def product_price_chart_spec(title: str) -> dict[str, object]:
    return {
        "type": "line",
        "x": "date",
        "y": "price",
        "color": None,
        "title": title,
        "x_label": "Date",
        "y_label": "Price (TRY)",
        "table_columns": PRODUCT_HISTORY_COLUMNS,
    }


def retailer_average_chart_spec(aggregation: str) -> dict[str, object]:
    return {
        "type": "line",
        "x": "date",
        "y": "price",
        "color": "retailer",
        "title": f"{aggregation} scraped price by retailer",
        "x_label": "Date",
        "y_label": "Price (TRY)",
        "table_columns": RETAILER_AVERAGE_COLUMNS,
    }


def coverage_area_chart_spec() -> dict[str, object]:
    return {
        "type": "area",
        "x": "date",
        "y": "tracked_products",
        "color": "retailer",
        "title": "Tracked products over time",
        "x_label": "Date",
        "y_label": "Tracked products",
        "table_columns": COVERAGE_OVER_TIME_COLUMNS,
    }


def category_coverage_bar_chart_spec() -> dict[str, object]:
    return {
        "type": "bar",
        "x": "products",
        "y": "category",
        "color": "retailer",
        "orientation": "h",
        "title": "Top categories by tracked products",
        "x_label": "Products",
        "y_label": "Category",
        "table_columns": CATEGORY_COVERAGE_COLUMNS,
    }
