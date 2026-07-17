from __future__ import annotations

from datetime import date
from difflib import get_close_matches
import re
import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st

from inflation_dashboard.application.chart_specs import (
    BIGGEST_DROPS_COLUMNS,
    BIGGEST_GAINS_COLUMNS,
    SKIPPED_DIAGNOSTICS_COLUMNS,
    category_coverage_bar_chart_spec,
    coverage_area_chart_spec,
    product_price_chart_spec,
    retailer_average_chart_spec,
)
from inflation_dashboard.frontend.api_client import (
    ApiClientError,
    ApiEnvelope,
    DATA_TIMEOUT_SECONDS,
    DEFAULT_API_BASE_URL,
    DashboardFilters,
    FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER,
    FRONTEND_DEFAULT_RETAILERS,
    build_common_params,
    fetch_endpoint,
    fetch_inventory,
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


@st.cache_data(show_spinner=False, ttl=300)
def cached_fetch_inventory(api_base_url: str) -> ApiEnvelope:
    return fetch_inventory(api_base_url)


@st.cache_data(show_spinner="Loading API data...", ttl=120, max_entries=64)
def cached_fetch_api_endpoint(
    api_base_url: str,
    endpoint_path: str,
    params: tuple[tuple[str, object], ...],
) -> ApiEnvelope:
    return fetch_endpoint(api_base_url, endpoint_path, list(params), timeout=DATA_TIMEOUT_SECONDS)


def format_currency(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"₺{value:,.2f}"


def render_chart(data: pd.DataFrame, spec: dict[str, object]):
    chart_type = spec["type"]
    chart_kwargs = {
        "x": spec["x"],
        "y": spec["y"],
        "color": spec.get("color"),
        "title": spec["title"],
    }
    if chart_type == "line":
        chart = px.line(data, markers=True, **chart_kwargs)
    elif chart_type == "area":
        chart = px.area(data, **chart_kwargs)
    elif chart_type == "bar":
        chart = px.bar(data, orientation=spec.get("orientation"), **chart_kwargs)
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    chart.update_layout(height=460, legend_title_text="")
    chart.update_yaxes(title=spec["y_label"])
    chart.update_xaxes(title=spec["x_label"])
    st.plotly_chart(chart, use_container_width=True)


def _parse_inventory_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _extract_inventory_payload(inventory_envelope: ApiEnvelope) -> tuple[list[str], date | None, date | None]:
    data = inventory_envelope.data if isinstance(inventory_envelope.data, dict) else {}
    retailers = [str(retailer) for retailer in data.get("retailers", []) if retailer]
    min_date = _parse_inventory_date(data.get("min_date"))
    max_date = _parse_inventory_date(data.get("max_date"))
    return sorted(retailers), min_date, max_date


def _display_meta(prefix: str, meta: dict[str, object]) -> None:
    warnings = meta.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            st.sidebar.warning(str(warning))

    count = meta.get("selected_inventory_file_count")
    if count is None:
        count = meta.get("inventory_file_count", meta.get("file_count"))
    if count is not None:
        st.sidebar.caption(f"{prefix}: {count:,} files" if isinstance(count, int) else f"{prefix}: {count} files")


def _show_api_error(error: ApiClientError) -> None:
    st.error(f"Falcon API error: {error.message}")
    if error.meta:
        with st.expander("API error metadata"):
            st.json(error.meta)


def render_product_explorer(api_base_url: str, filters: DashboardFilters, retailer_options: list[str]):
    st.subheader("1. Product price explorer")
    selected_retailer = autocorrect_selectbox(
        "Retailer",
        retailer_options,
        key="product_retailer",
        help_text="Search supports close matches, so small typos still guide you to the right retailer.",
    )
    st.info("Product option and price-history API rendering will be connected in Plan 03-02.")
    _render_filter_preview(api_base_url, filters, [("product_retailer", selected_retailer)])


def render_retailer_average(api_base_url: str, filters: DashboardFilters, retailer_options: list[str]):
    st.subheader("2. Retailer average price chart")
    default = list(filters.selected_retailers[: min(4, len(filters.selected_retailers))])
    selected_retailers = autocorrect_multiselect(
        "Retailers",
        retailer_options,
        default,
        key="avg_retailers",
        help_text="Search supports close matches before choosing one or more retailers.",
    )
    aggregation = st.radio("Aggregation", ["Average", "Median"], horizontal=True)
    st.info("Retailer-average API rendering will be connected in Plan 03-02.")
    _render_filter_preview(api_base_url, filters, [("aggregation", aggregation), *[("retailer", r) for r in selected_retailers]])


def render_price_movers(api_base_url: str, filters: DashboardFilters, retailer_options: list[str]):
    st.subheader("3. Biggest price movers")
    scope_options = ["All retailers", *retailer_options]
    selected_retailer = autocorrect_selectbox("Retailer scope", scope_options, key="mover_retailer")
    mover_count = st.slider("Rows to show", min_value=5, max_value=30, value=10)
    st.info("Price-mover API rendering will be connected in Plan 03-02.")
    _render_filter_preview(api_base_url, filters, [("scope_retailer", selected_retailer), ("limit", mover_count)])


def render_overview(api_base_url: str, filters: DashboardFilters):
    st.subheader("4. Dataset coverage overview")
    st.info("Coverage API rendering will be connected in Plan 03-02.")
    _render_filter_preview(api_base_url, filters, [("category_limit", 20)])


def _render_filter_preview(
    api_base_url: str,
    filters: DashboardFilters,
    extra_params: list[tuple[str, object]] | None = None,
) -> None:
    params = [*build_common_params(filters), *(extra_params or [])]
    st.caption(f"API base URL: {api_base_url}")
    with st.expander("Prepared API query parameters"):
        st.json([{"name": name, "value": value} for name, value in params])


def main() -> None:
    st.set_page_config(page_title="Inflation Study Dashboard", layout="wide")

    st.title("Inflation Study Streamlit Dashboard")
    st.caption("Frontend configured to read dashboard setup data from the Falcon API.")

    st.sidebar.header("API settings")
    api_base_url = st.sidebar.text_input("Falcon API base URL", value=DEFAULT_API_BASE_URL)

    try:
        inventory_envelope = cached_fetch_inventory(api_base_url)
    except ApiClientError as error:
        _show_api_error(error)
        st.stop()

    retailer_options, min_date, max_date = _extract_inventory_payload(inventory_envelope)
    if not retailer_options:
        st.info("The Falcon API returned an empty inventory. Check that scraped CSV files are available to the API process.")
        st.stop()
    if min_date is None or max_date is None:
        st.error("The Falcon API inventory response did not include valid min_date and max_date values.")
        st.stop()

    default_retailers = [retailer for retailer in FRONTEND_DEFAULT_RETAILERS if retailer in retailer_options]
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
        value=FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER,
        step=5,
        help="Uses the newest files in the selected date range. Raise this for deeper history; lower it for faster loading.",
    )
    load_all_history = st.sidebar.checkbox("Load all files in date range", value=False)
    effective_limit = 0 if load_all_history else max_files_per_retailer

    filters = DashboardFilters(
        selected_retailers=tuple(selected_retailers),
        start_date=start_date,
        end_date=end_date,
        max_files=effective_limit,
        all_history=load_all_history,
    )
    common_params = tuple(build_common_params(filters))

    st.sidebar.header("API inventory summary")
    _display_meta("Inventory", inventory_envelope.meta)
    st.sidebar.caption(f"Prepared {len(common_params)} common query parameters for data endpoints.")
    if load_all_history:
        st.sidebar.warning("All-history mode sends all_history=true and max_files=0 to the API.")

    product_tab, retailer_tab, movers_tab, overview_tab = st.tabs(
        [
            "Product explorer",
            "Retailer averages",
            "Price movers",
            "Coverage overview",
        ]
    )

    with product_tab:
        render_product_explorer(api_base_url, filters, retailer_options)
    with retailer_tab:
        render_retailer_average(api_base_url, filters, retailer_options)
    with movers_tab:
        render_price_movers(api_base_url, filters, retailer_options)
    with overview_tab:
        render_overview(api_base_url, filters)


if __name__ == "__main__":
    main()
