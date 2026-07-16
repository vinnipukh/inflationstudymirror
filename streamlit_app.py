from __future__ import annotations

from difflib import get_close_matches
import re
import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st

from inflation_dashboard.adapters.csv_price_repository import (
    DEFAULT_MAX_FILES_PER_RETAILER,
    DEFAULT_RETAILERS,
    discover_csv_inventory as discover_csv_inventory_uncached,
    load_price_history as load_price_history_uncached,
)

MAX_AUTOCORRECT_OPTIONS = 80


def normalize_search_text(value: object) -> str:
    text = str(value or "").casefold().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text)


def rank_search_options(query: str, options: list[str], limit: int = MAX_AUTOCORRECT_OPTIONS) -> list[str]:
    query_key = normalize_search_text(query)
    if not query_key:
        return options[:limit]

    keyed_options = {option: normalize_search_text(option) for option in options}
    startswith_matches = [option for option, key in keyed_options.items() if key.startswith(query_key)]
    contains_matches = [
        option
        for option, key in keyed_options.items()
        if query_key in key and option not in startswith_matches
    ]
    close_keys = get_close_matches(query_key, list(keyed_options.values()), n=limit, cutoff=0.45)
    close_matches = [
        option
        for option, key in keyed_options.items()
        if key in close_keys and option not in startswith_matches and option not in contains_matches
    ]

    return (startswith_matches + contains_matches + close_matches)[:limit]


def autocorrect_selectbox(label: str, options: list[str], key: str, *, help_text: str | None = None) -> str:
    if not options:
        st.warning(f"No options available for {label.lower()}.")
        st.stop()

    query = st.text_input(
        f"Search {label.lower()}",
        key=f"{key}_query",
        placeholder="Type a few letters; misspellings are okay",
        help=help_text,
    )
    ranked_options = rank_search_options(query, options)

    if query and not ranked_options:
        st.info("No close matches found. Showing the full list instead.")
        ranked_options = options[:MAX_AUTOCORRECT_OPTIONS]
    elif query:
        best = ranked_options[0]
        if normalize_search_text(best) != normalize_search_text(query):
            st.caption(f"Closest match: {best}")

    return st.selectbox(label, ranked_options, key=key)


def autocorrect_multiselect(
    label: str,
    options: list[str],
    default: list[str],
    key: str,
    *,
    help_text: str | None = None,
) -> list[str]:
    query = st.text_input(
        f"Search {label.lower()}",
        key=f"{key}_query",
        placeholder="Type a few letters; misspellings are okay",
        help=help_text,
    )
    ranked_options = rank_search_options(query, options)
    current_selection = st.session_state.get(key, default)
    display_options = list(dict.fromkeys([*current_selection, *ranked_options]))

    if query and ranked_options:
        st.caption(f"Closest match: {ranked_options[0]}")
    elif query:
        st.info("No close matches found. Showing the current selection instead.")

    return st.multiselect(label, display_options, default=current_selection, key=key)


@st.cache_data(show_spinner=False)
def discover_csv_inventory() -> pd.DataFrame:
    return discover_csv_inventory_uncached()


@st.cache_data(show_spinner="Loading selected scraped CSV files...")
def load_price_history(
    selected_retailers: tuple[str, ...],
    start_date,
    end_date,
    max_files_per_retailer: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    inventory = discover_csv_inventory()
    return load_price_history_uncached(
        selected_retailers,
        start_date,
        end_date,
        max_files_per_retailer,
        inventory=inventory,
    )


def format_currency(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"₺{value:,.2f}"


def line_chart(data: pd.DataFrame, x: str, y: str, color: str | None = None, title: str = ""):
    chart = px.line(data, x=x, y=y, color=color, markers=True, title=title)
    chart.update_layout(height=460, legend_title_text="")
    chart.update_yaxes(title="Price (TRY)")
    chart.update_xaxes(title="Date")
    st.plotly_chart(chart, use_container_width=True)


def render_product_explorer(history: pd.DataFrame):
    st.subheader("1. Product price explorer")
    retailer_options = sorted(history["retailer"].unique())
    selected_retailer = autocorrect_selectbox(
        "Retailer",
        retailer_options,
        key="product_retailer",
        help_text="Search supports close matches, so small typos still guide you to the right retailer.",
    )

    retailer_slice = history[history["retailer"] == selected_retailer].copy()
    product_labels = retailer_slice["product_name"].drop_duplicates().sort_values().tolist()
    selected_product = autocorrect_selectbox(
        "Product",
        product_labels,
        key="product_name",
        help_text="Type part of the product name; the closest spelling is surfaced first.",
    )

    product_history = retailer_slice[retailer_slice["product_name"] == selected_product].copy()
    product_history = product_history.sort_values("date")

    cheapest_row = product_history.loc[product_history["price"].idxmin()]
    latest_row = product_history.iloc[-1]
    first_row = product_history.iloc[0]
    change_since_first = ((latest_row["price"] - first_row["price"]) / first_row["price"] * 100) if first_row["price"] else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest price", format_currency(latest_row["price"]))
    c2.metric("Cheapest price", format_currency(cheapest_row["price"]))
    c3.metric("Cheapest date", cheapest_row["date"].strftime("%Y-%m-%d"))
    c4.metric("Change vs first seen", f"{change_since_first:.2f}%")

    line_chart(product_history, x="date", y="price", title=f"{selected_product} price history")
    st.dataframe(product_history[["date", "price", "category", "source_file"]], use_container_width=True, hide_index=True)


def render_retailer_average(history: pd.DataFrame):
    st.subheader("2. Retailer average price chart")
    retailer_options = sorted(history["retailer"].unique())
    selected_retailers = autocorrect_multiselect(
        "Retailers",
        retailer_options,
        retailer_options[: min(4, len(retailer_options))],
        key="avg_retailers",
        help_text="Search supports close matches before choosing one or more retailers.",
    )
    aggregation = st.radio("Aggregation", ["Average", "Median"], horizontal=True)

    filtered = history[history["retailer"].isin(selected_retailers)].copy()
    if filtered.empty:
        st.info("Select at least one retailer.")
        return

    if aggregation == "Average":
        grouped = filtered.groupby(["date", "retailer"], as_index=False)["price"].mean()
    else:
        grouped = filtered.groupby(["date", "retailer"], as_index=False)["price"].median()

    line_chart(grouped, x="date", y="price", color="retailer", title=f"{aggregation} scraped price by retailer")
    st.dataframe(grouped.sort_values(["retailer", "date"]), use_container_width=True, hide_index=True)


def render_price_movers(history: pd.DataFrame):
    st.subheader("3. Biggest price movers")
    retailer_options = ["All retailers"] + sorted(history["retailer"].unique())
    selected_retailer = autocorrect_selectbox("Retailer scope", retailer_options, key="mover_retailer")
    mover_count = st.slider("Rows to show", min_value=5, max_value=30, value=10)

    movers = history.copy()
    if selected_retailer != "All retailers":
        movers = movers[movers["retailer"] == selected_retailer]

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
        st.info("Not enough repeated product observations for this selection.")
        return

    stats["change_since_first_pct"] = ((stats["latest_price"] - stats["first_price"]) / stats["first_price"]) * 100
    stats["drop_from_peak_pct"] = ((stats["latest_price"] - stats["max_price"]) / stats["max_price"]) * 100
    stats["savings_vs_peak"] = stats["max_price"] - stats["latest_price"]

    biggest_drops = stats.sort_values("drop_from_peak_pct").head(mover_count)
    biggest_gains = stats.sort_values("change_since_first_pct", ascending=False).head(mover_count)

    left, right = st.columns(2)
    with left:
        st.markdown("**Best current deals vs peak price**")
        st.dataframe(
            biggest_drops[
                [
                    "retailer",
                    "product_name",
                    "latest_price",
                    "max_price",
                    "savings_vs_peak",
                    "drop_from_peak_pct",
                    "last_seen",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.markdown("**Strongest increases since first seen**")
        st.dataframe(
            biggest_gains[
                [
                    "retailer",
                    "product_name",
                    "first_price",
                    "latest_price",
                    "change_since_first_pct",
                    "first_seen",
                    "last_seen",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


def render_overview(history: pd.DataFrame, skipped: pd.DataFrame):
    st.subheader("4. Dataset coverage overview")
    history = history.copy()
    history["month"] = history["date"].dt.to_period("M").astype(str)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Retailers", history["retailer"].nunique())
    c2.metric("Tracked products", history["product_id"].nunique())
    c3.metric("Price observations", len(history))
    c4.metric("Date range", f"{history['date'].min():%Y-%m-%d} → {history['date'].max():%Y-%m-%d}")

    left, right = st.columns(2)
    with left:
        coverage = history.groupby(["date", "retailer"], as_index=False)["product_id"].nunique()
        coverage = coverage.rename(columns={"product_id": "tracked_products"})
        chart = px.area(coverage, x="date", y="tracked_products", color="retailer", title="Tracked products over time")
        chart.update_layout(height=420, legend_title_text="")
        st.plotly_chart(chart, use_container_width=True)

    with right:
        categories = (
            history.groupby(["retailer", "category"], as_index=False)["product_id"]
            .nunique()
            .rename(columns={"product_id": "products"})
            .sort_values("products", ascending=False)
            .head(20)
        )
        chart = px.bar(categories, x="products", y="category", color="retailer", orientation="h", title="Top categories by tracked products")
        chart.update_layout(height=420, legend_title_text="")
        st.plotly_chart(chart, use_container_width=True)

    if not skipped.empty:
        with st.expander(f"Skipped files ({len(skipped)})"):
            st.dataframe(skipped, use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Inflation Study Dashboard", layout="wide")

    st.title("Inflation Study Streamlit Dashboard")
    st.caption("Built directly on the scraped CSV files in the repository.")

    inventory = discover_csv_inventory()
    if inventory.empty:
        st.error("No supported scraped CSV files were found in the Datas/ directory.")
        st.stop()

    retailer_options = sorted(inventory["retailer"].unique())
    default_retailers = [retailer for retailer in DEFAULT_RETAILERS if retailer in retailer_options]
    if not default_retailers:
        default_retailers = retailer_options[: min(3, len(retailer_options))]

    st.sidebar.header("Load settings")
    with st.sidebar:
        selected_retailers = autocorrect_multiselect(
            "Retailers to load",
            retailer_options,
            default_retailers,
            key="load_retailers",
            help_text="Loading fewer retailers is much faster. Add the large datasets only when needed.",
        )

    min_date = inventory["date"].min().date()
    max_date = inventory["date"].max().date()
    default_start = max(min_date, (pd.Timestamp(max_date) - pd.Timedelta(days=60)).date())
    start_date, end_date = st.sidebar.date_input(
        "Date range",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    max_files_per_retailer = st.sidebar.slider(
        "Max CSV files per retailer",
        min_value=10,
        max_value=160,
        value=DEFAULT_MAX_FILES_PER_RETAILER,
        step=5,
        help="Uses the newest files in the selected date range. Raise this for deeper history; lower it for faster loading.",
    )
    load_all_history = st.sidebar.checkbox("Load all files in date range", value=False)
    effective_limit = 0 if load_all_history else max_files_per_retailer

    chosen_inventory = inventory[
        inventory["retailer"].isin(selected_retailers)
        & (inventory["date"] >= pd.to_datetime(start_date))
        & (inventory["date"] <= pd.to_datetime(end_date))
    ]
    estimated_files = len(chosen_inventory)
    if not load_all_history:
        estimated_files = min(estimated_files, len(selected_retailers) * max_files_per_retailer)
    st.sidebar.caption(f"About {estimated_files} CSV files will be loaded.")

    history, skipped = load_price_history(
        tuple(selected_retailers),
        start_date,
        end_date,
        effective_limit,
    )

    if history.empty:
        st.error("No price rows could be loaded with the current filters.")
        if not skipped.empty:
            st.dataframe(skipped, use_container_width=True, hide_index=True)
        st.stop()

    st.sidebar.header("Loaded dataset summary")
    st.sidebar.write(f"Retailers: {history['retailer'].nunique()}")
    st.sidebar.write(f"Products: {history['product_id'].nunique()}")
    st.sidebar.write(f"Observations: {len(history):,}")
    st.sidebar.write(f"Window: {history['date'].min():%Y-%m-%d} → {history['date'].max():%Y-%m-%d}")

    with st.sidebar.expander("Loaded retailers"):
        for retailer_name in sorted(history["retailer"].unique()):
            st.write(f"- {retailer_name}")

    product_tab, retailer_tab, movers_tab, overview_tab = st.tabs(
        [
            "Product explorer",
            "Retailer averages",
            "Price movers",
            "Coverage overview",
        ]
    )

    with product_tab:
        render_product_explorer(history)
    with retailer_tab:
        render_retailer_average(history)
    with movers_tab:
        render_price_movers(history)
    with overview_tab:
        render_overview(history, skipped)


if __name__ == "__main__":
    main()
