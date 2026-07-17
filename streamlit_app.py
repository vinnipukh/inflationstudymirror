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
    DEFAULT_API_BASE_URL,
    DashboardFilters,
    FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER,
    FRONTEND_DEFAULT_RETAILERS,
    build_common_params,
    fetch_coverage,
    fetch_history,
    fetch_inventory,
    fetch_movers,
    fetch_retailer_averages,
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


@st.cache_data(show_spinner="Loading product options from /api/history...", ttl=120, max_entries=64)
def cached_fetch_history(
    api_base_url: str,
    filters: DashboardFilters,
    product_name: str | None = None,
    product_retailer: str | None = None,
) -> ApiEnvelope:
    return fetch_history(
        api_base_url,
        filters,
        product_name=product_name,
        product_retailer=product_retailer,
    )


@st.cache_data(show_spinner="Loading retailer averages from /api/retailer-averages...", ttl=120, max_entries=64)
def cached_fetch_retailer_averages(api_base_url: str, filters: DashboardFilters, aggregation: str) -> ApiEnvelope:
    return fetch_retailer_averages(api_base_url, filters, aggregation=aggregation)


@st.cache_data(show_spinner="Loading price movers from /api/movers...", ttl=120, max_entries=64)
def cached_fetch_movers(api_base_url: str, filters: DashboardFilters, scope_retailer: str, limit: int) -> ApiEnvelope:
    return fetch_movers(api_base_url, filters, scope_retailer=scope_retailer, limit=limit)


@st.cache_data(show_spinner="Loading coverage from /api/coverage...", ttl=120, max_entries=64)
def cached_fetch_coverage(api_base_url: str, filters: DashboardFilters, category_limit: int = 20) -> ApiEnvelope:
    return fetch_coverage(api_base_url, filters, category_limit=category_limit)


def format_currency(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"₺{value:,.2f}"


def _format_percent(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    try:
        return f"{float(value):,.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _format_int(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


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
    st.plotly_chart(chart, width="stretch")


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


def _records_to_frame(records: object, *, date_columns: tuple[str, ...] = ("date",)) -> pd.DataFrame:
    frame = pd.DataFrame(records if isinstance(records, list) else [])
    for column in date_columns:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def _safe_table_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column in frame.columns]


def _unique_strings(values: object) -> list[str]:
    if values is None:
        return []
    return sorted({str(value) for value in values if pd.notna(value) and str(value)})


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


def _display_api_warnings(meta: dict[str, object]) -> None:
    warnings = meta.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            st.warning(str(warning))


def _show_api_error(error: ApiClientError) -> None:
    st.error(f"Falcon API error: {error.message}")
    if error.meta:
        with st.expander("API error metadata"):
            st.json(error.meta)


def _filters_for_selected_retailers(filters: DashboardFilters, selected_retailers: list[str]) -> DashboardFilters:
    return DashboardFilters(
        selected_retailers=tuple(selected_retailers),
        start_date=filters.start_date,
        end_date=filters.end_date,
        max_files=filters.max_files,
        all_history=filters.all_history,
    )


def render_product_explorer(api_base_url: str, filters: DashboardFilters, retailer_options: list[str]):
    st.subheader("1. Product price explorer")
    try:
        options_envelope = cached_fetch_history(api_base_url, filters)
    except ApiClientError as error:
        _show_api_error(error)
        return

    _display_api_warnings(options_envelope.meta)
    options_data = options_envelope.data if isinstance(options_envelope.data, dict) else {}
    options_history = _records_to_frame(options_data.get("history", []))
    if options_history.empty:
        st.info("No product options were returned by /api/history for the selected filters.")
        return

    returned_retailers = _unique_strings(options_history.get("retailer"))
    selected_filter_retailers = [retailer for retailer in filters.selected_retailers if retailer in returned_retailers]
    product_retailer_options = selected_filter_retailers or returned_retailers or retailer_options
    selected_retailer = autocorrect_selectbox(
        "Retailer",
        product_retailer_options,
        key="product_retailer",
        help_text="Search supports close matches, so small typos still guide you to the right retailer.",
    )

    retailer_history = options_history[options_history["retailer"] == selected_retailer] if "retailer" in options_history else options_history
    product_options = _unique_strings(retailer_history.get("product_name"))
    if not product_options:
        st.info("No product options were returned for the selected retailer and filters.")
        return

    selected_product = autocorrect_selectbox(
        "Product",
        product_options,
        key="product_name",
        help_text="Product options come from bounded /api/history results for the current filters.",
    )

    try:
        product_envelope = cached_fetch_history(
            api_base_url,
            filters,
            product_name=selected_product,
            product_retailer=selected_retailer,
        )
    except ApiClientError as error:
        _show_api_error(error)
        return

    _display_api_warnings(product_envelope.meta)
    data = product_envelope.data if isinstance(product_envelope.data, dict) else {}
    product_history = _records_to_frame(data.get("history", []))
    if product_history.empty:
        st.info("No price history was returned for this product and filter selection.")
        return

    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    latest_price, cheapest_price, cheapest_date, change_pct = st.columns(4)
    latest_price.metric("Latest price", format_currency(summary.get("latest_price")))
    cheapest_price.metric("Cheapest price", format_currency(summary.get("cheapest_price")))
    cheapest_date.metric("Cheapest date", str(summary.get("cheapest_date") or "-"))
    change_pct.metric("Change since first", _format_percent(summary.get("change_since_first_pct")))

    spec = product_price_chart_spec(f"{selected_product} at {selected_retailer}")
    render_chart(product_history, spec)
    columns = _safe_table_columns(product_history, spec["table_columns"])
    st.dataframe(product_history[columns] if columns else product_history, hide_index=True)


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
    if not selected_retailers:
        st.info("Select at least one retailer to load retailer averages.")
        return

    average_filters = _filters_for_selected_retailers(filters, selected_retailers)
    try:
        averages_envelope = cached_fetch_retailer_averages(api_base_url, average_filters, aggregation)
    except ApiClientError as error:
        _show_api_error(error)
        return

    _display_api_warnings(averages_envelope.meta)
    data = averages_envelope.data if isinstance(averages_envelope.data, dict) else {}
    records = data.get("records") or data.get("retailer_averages", [])
    averages = _records_to_frame(records)
    if averages.empty:
        st.info("No retailer average records were returned for this filter selection.")
        return

    spec = retailer_average_chart_spec(aggregation)
    render_chart(averages, spec)
    columns = _safe_table_columns(averages, spec["table_columns"])
    st.dataframe(averages[columns] if columns else averages, hide_index=True)


def render_price_movers(api_base_url: str, filters: DashboardFilters, retailer_options: list[str]):
    st.subheader("3. Biggest price movers")
    selected_filter_retailers = [retailer for retailer in filters.selected_retailers if retailer in retailer_options]
    scope_options = ["All retailers", *(selected_filter_retailers or list(filters.selected_retailers) or retailer_options)]
    selected_retailer = autocorrect_selectbox("Retailer scope", scope_options, key="mover_retailer")
    mover_count = st.slider("Rows to show", min_value=5, max_value=30, value=10)

    try:
        movers_envelope = cached_fetch_movers(
            api_base_url,
            filters,
            scope_retailer=selected_retailer,
            limit=mover_count,
        )
    except ApiClientError as error:
        _show_api_error(error)
        return

    _display_api_warnings(movers_envelope.meta)
    data = movers_envelope.data if isinstance(movers_envelope.data, dict) else {}
    biggest_drops = _records_to_frame(data.get("biggest_drops", []), date_columns=("last_seen",))
    biggest_gains = _records_to_frame(data.get("biggest_gains", []), date_columns=("first_seen", "last_seen"))
    if biggest_drops.empty and biggest_gains.empty:
        st.info("Not enough repeated product observations for this selection.")
        return

    drop_col, gain_col = st.columns(2)
    with drop_col:
        st.markdown("**Biggest drops vs. peak**")
        columns = _safe_table_columns(biggest_drops, BIGGEST_DROPS_COLUMNS)
        if biggest_drops.empty:
            st.info("No price drops were returned for this selection.")
        else:
            st.dataframe(biggest_drops[columns] if columns else biggest_drops, hide_index=True)
    with gain_col:
        st.markdown("**Biggest gains since first observation**")
        columns = _safe_table_columns(biggest_gains, BIGGEST_GAINS_COLUMNS)
        if biggest_gains.empty:
            st.info("No price gains were returned for this selection.")
        else:
            st.dataframe(biggest_gains[columns] if columns else biggest_gains, hide_index=True)


def render_overview(api_base_url: str, filters: DashboardFilters):
    st.subheader("4. Dataset coverage overview")
    try:
        coverage_envelope = cached_fetch_coverage(api_base_url, filters, category_limit=20)
    except ApiClientError as error:
        _show_api_error(error)
        return

    _display_api_warnings(coverage_envelope.meta)
    data = coverage_envelope.data if isinstance(coverage_envelope.data, dict) else {}
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    coverage_over_time = _records_to_frame(data.get("coverage_over_time", []))
    category_coverage = _records_to_frame(data.get("category_coverage", []))
    skipped_files = _records_to_frame(data.get("skipped_files", []), date_columns=())

    if not summary and coverage_over_time.empty and category_coverage.empty and skipped_files.empty:
        st.info("No coverage data was returned for this filter selection.")
        return

    date_range = summary.get("date_range")
    if isinstance(date_range, (list, tuple)):
        date_range_value = " → ".join(str(value) for value in date_range if value)
    elif isinstance(date_range, dict):
        date_range_value = " → ".join(str(date_range.get(key) or "") for key in ("start", "end")).strip(" →")
    else:
        date_range_value = str(date_range or "-")

    retailer_count, product_count, observation_count, date_range_metric = st.columns(4)
    retailer_count.metric("Retailers", _format_int(summary.get("retailer_count")))
    product_count.metric("Products", _format_int(summary.get("product_count")))
    observation_count.metric("Observations", _format_int(summary.get("observation_count")))
    date_range_metric.metric("Date range", date_range_value or "-")

    if coverage_over_time.empty:
        st.info("No coverage-over-time records were returned for this filter selection.")
    else:
        coverage_spec = coverage_area_chart_spec()
        render_chart(coverage_over_time, coverage_spec)
        columns = _safe_table_columns(coverage_over_time, coverage_spec["table_columns"])
        st.dataframe(coverage_over_time[columns] if columns else coverage_over_time, hide_index=True)

    if category_coverage.empty:
        st.info("No category coverage records were returned for this filter selection.")
    else:
        category_spec = category_coverage_bar_chart_spec()
        render_chart(category_coverage, category_spec)
        columns = _safe_table_columns(category_coverage, category_spec["table_columns"])
        st.dataframe(category_coverage[columns] if columns else category_coverage, hide_index=True)

    skipped_count = summary.get("skipped_file_count", coverage_envelope.meta.get("skipped_file_count", len(skipped_files)))
    if skipped_count:
        st.warning(f"{_format_int(skipped_count)} files were skipped while loading this selection.")
    with st.expander("Skipped file diagnostics"):
        if skipped_files.empty:
            st.info("No skipped file diagnostics were returned by the API.")
        else:
            columns = _safe_table_columns(skipped_files, SKIPPED_DIAGNOSTICS_COLUMNS)
            st.dataframe(skipped_files[columns] if columns else skipped_files, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Inflation Study Dashboard", layout="wide")

    st.title("Inflation Study Streamlit Dashboard")
    st.caption("Frontend configured to read dashboard setup and tab data from the Falcon API.")

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
