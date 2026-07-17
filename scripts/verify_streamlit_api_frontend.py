#!/usr/bin/env python
"""Verify the final Phase 03 Streamlit/Falcon frontend boundary.

Run from the repository root with:
    python scripts/verify_streamlit_api_frontend.py

This verifier source-scans Streamlit and exercises the API client without a
live Falcon server.
"""
from __future__ import annotations

from datetime import date
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STREAMLIT_APP = REPO_ROOT / "streamlit_app.py"
CLIENT_MODULE = REPO_ROOT / "inflation_dashboard/frontend/api_client.py"
ENVELOPE_KEYS = {"data", "meta", "errors"}

FORBIDDEN_STREAMLIT_TOKENS = (
    "inflation_dashboard.adapters.csv_price_repository",
    "discover_csv_inventory_uncached",
    "load_price_history_uncached",
    "from inflation_dashboard.application.use_cases import",
    "calculate_retailer_average_trends(",
    "calculate_price_movers(",
    "calculate_coverage_summary(",
    "calculate_coverage_over_time(",
    "calculate_category_coverage(",
    "get_product_history(",
    "summarize_product_history(",
    "discover_csv_inventory(",
    "load_price_history(",
    "history, skipped =",
    "chosen_inventory = inventory[",
    "history['product_id'].nunique()",
    'history["product_id"].nunique()',
    '"/api/products"',
    "'/api/products'",
)
TAB_LABELS = ("Product explorer", "Retailer averages", "Price movers", "Coverage overview")
EMPTY_STATE_MESSAGES = (
    "No product options were returned by /api/history",
    "No price history was returned for this product",
    "No retailer average records were returned",
    "Not enough repeated product observations for this selection.",
    "No coverage data was returned",
)
ENDPOINT_PATHS = (
    "/api/inventory",
    "/api/history",
    "/api/retailer-averages",
    "/api/movers",
    "/api/coverage",
)
CLIENT_METHODS = (
    "fetch_inventory",
    "fetch_history",
    "fetch_retailer_averages",
    "fetch_movers",
    "fetch_coverage",
)
ENDPOINT_PARAMS = (
    "product_name",
    "product_retailer",
    "aggregation",
    "scope_retailer",
    "limit",
    "category_limit",
)


class FakeResponse:
    def __init__(self, status_code: int, payload: Any = None, *, json_error: Exception | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def _assert_streamlit_source() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")

    for token in FORBIDDEN_STREAMLIT_TOKENS:
        assert token not in source, f"streamlit_app.py still contains forbidden local data-boundary token: {token}"

    assert "from inflation_dashboard.application.chart_specs import" in source, "chart-spec imports should remain available"
    assert "Falcon API base URL" in source, "sidebar must expose visible Falcon API base URL control"
    assert "DEFAULT_API_BASE_URL" in source, "streamlit_app.py should use the client default API base URL constant"
    assert "cached_fetch_inventory(api_base_url" in source, "inventory cache key must include api_base_url"
    for method in CLIENT_METHODS:
        assert method in source, f"streamlit_app.py missing client method usage/import: {method}"
    assert "cached_fetch_history(api_base_url, filters)" in source, (
        "product options must use bounded cached /api/history without product selectors"
    )
    assert "cached_fetch_history(" in source and "product_name=selected_product" in source, (
        "product-specific history must pass product_name"
    )
    assert "product_retailer=selected_retailer" in source, "product-specific history must pass product_retailer"
    assert "cached_fetch_retailer_averages(" in source and "aggregation" in source, (
        "retailer averages must call API with aggregation"
    )
    assert "cached_fetch_movers(" in source and "scope_retailer=selected_retailer" in source and "limit=mover_count" in source, (
        "movers must call API with scope_retailer and limit"
    )
    assert "cached_fetch_coverage(api_base_url, filters, category_limit=20)" in source, (
        "coverage must call API with category_limit=20"
    )
    assert "Load all files in date range" in source, "all-history checkbox label must be preserved"
    assert "effective_limit = 0 if load_all_history else max_files_per_retailer" in source, (
        "all-history must map to max_files=0 semantics"
    )
    assert "st.error" in source and "ApiClientError" in source, "ApiClientError must be surfaced with st.error"
    assert "_display_api_warnings" in source and "meta.get(\"warnings\")" in source, "API warnings must be visible"

    for label in TAB_LABELS:
        assert label in source, f"missing tab label: {label}"
    assert "autocorrect_multiselect(" in source and "Retailers to load" in source, (
        "sidebar retailer selector must keep autocorrect_multiselect"
    )
    assert "autocorrect_multiselect(" in source and '"Retailers"' in source and "avg_retailers" in source, (
        "retailer averages must keep autocorrect_multiselect"
    )
    assert source.count("autocorrect_selectbox(") >= 3, "product and movers flows must keep autocorrect_selectbox"
    assert '"Retailer scope"' in source and '"Rows to show"' in source, "movers controls must be preserved"
    assert "min_value=5" in source and "max_value=30" in source and "value=10" in source, (
        "movers rows slider must remain 5..30 default 10"
    )
    assert "st.columns(2)" in source and "biggest_drops" in source and "biggest_gains" in source, (
        "movers must preserve two-column drops/gains rendering"
    )
    for token in (
        "latest_price",
        "cheapest_price",
        "cheapest_date",
        "change_since_first_pct",
        "records",
        "retailer_averages",
        "summary",
        "coverage_over_time",
        "category_coverage",
        "skipped_files",
        "SKIPPED_DIAGNOSTICS_COLUMNS",
        "coverage_area_chart_spec",
        "category_coverage_bar_chart_spec",
        "product_price_chart_spec",
        "retailer_average_chart_spec",
        "BIGGEST_DROPS_COLUMNS",
        "BIGGEST_GAINS_COLUMNS",
    ):
        assert token in source, f"streamlit_app.py missing expected rendering token: {token}"
    for message in EMPTY_STATE_MESSAGES:
        assert message in source, f"missing tab-specific empty-state message: {message}"

    print("PASS source: final Streamlit tab/API boundary assertions")


def _assert_client_source() -> None:
    source = CLIENT_MODULE.read_text(encoding="utf-8")
    for token in ("import streamlit", "from streamlit", "plotly", "csv_price_repository", "application.use_cases"):
        assert token not in source, f"api_client.py contains forbidden dependency token: {token}"
    for token in (
        "DEFAULT_API_BASE_URL = \"http://localhost:8000\"",
        "SHORT_TIMEOUT_SECONDS = 10",
        "DATA_TIMEOUT_SECONDS = 60",
        "ApiClientError",
        "DashboardFilters",
        "ApiEnvelope",
        "normalize_api_base_url",
        "build_common_params",
        "fetch_endpoint",
        "fetch_health",
        *CLIENT_METHODS,
        "requests.get",
    ):
        assert token in source, f"api_client.py missing expected token: {token}"
    for path in ENDPOINT_PATHS:
        assert path in source, f"api_client.py missing endpoint path: {path}"
    for key in ENVELOPE_KEYS:
        assert key in source, f"api_client.py must validate envelope key: {key}"
    for param in ENDPOINT_PARAMS:
        assert f'"{param}"' in source, f"api_client.py missing endpoint-specific param: {param}"
    assert "for retailer in filters.selected_retailers" in source and "params.append((\"retailer\", retailer))" in source, (
        "client must serialize repeated retailer params as list-of-pairs"
    )
    print("PASS source: final frontend API client assertions")


def _assert_client_behavior() -> None:
    from inflation_dashboard.frontend import api_client

    assert api_client.DEFAULT_API_BASE_URL == "http://localhost:8000"
    assert api_client.FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER == 45
    assert api_client.SHORT_TIMEOUT_SECONDS == 10
    assert api_client.DATA_TIMEOUT_SECONDS == 60

    filters = api_client.DashboardFilters(
        selected_retailers=("Markets / Gurmar", "HomeGoods"),
        start_date=date(2026, 1, 1),
        end_date="2026-03-01",
        max_files=45,
        all_history=False,
    )
    params = api_client.build_common_params(filters)
    assert params.count(("retailer", "Markets / Gurmar")) == 1
    assert params.count(("retailer", "HomeGoods")) == 1
    assert [name for name, _ in params].count("retailer") == 2, "retailer params must be repeated pairs"
    assert ("start_date", "2026-01-01") in params
    assert ("end_date", "2026-03-01") in params
    assert ("max_files", 45) in params
    assert ("all_history", "false") in params

    all_history = api_client.DashboardFilters(
        selected_retailers=("Markets / Gurmar",),
        start_date="2026-01-01",
        end_date="2026-03-01",
        max_files=45,
        all_history=True,
    )
    all_params = api_client.build_common_params(all_history)
    assert ("max_files", 0) in all_params and ("all_history", "true") in all_params

    seen_calls: list[dict[str, Any]] = []

    def fake_get(url: str, params: Any = None, timeout: int | None = None) -> FakeResponse:
        seen_calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(200, {"data": {"ok": True}, "meta": {"request_id": "test"}, "errors": []})

    with patch.object(api_client.requests, "get", side_effect=fake_get):
        envelope = api_client.fetch_endpoint("http://localhost:8000/", "/api/history", params, timeout=60)
    assert envelope.data == {"ok": True}
    assert seen_calls[-1]["url"] == "http://localhost:8000/api/history"
    assert seen_calls[-1]["params"] == params, "request must preserve list-of-pairs params"
    assert seen_calls[-1]["timeout"] == 60

    with patch.object(api_client.requests, "get", side_effect=fake_get):
        api_client.fetch_inventory("http://localhost:8000")
        api_client.fetch_history("http://localhost:8000", filters)
        api_client.fetch_history("http://localhost:8000", filters, "Milk", "Markets / Gurmar")
        api_client.fetch_retailer_averages("http://localhost:8000", filters, "Median")
        api_client.fetch_movers("http://localhost:8000", filters, "All retailers", 10)
        api_client.fetch_coverage("http://localhost:8000", filters, 20)

    inventory_call, options_call, product_call, averages_call, movers_call, coverage_call = seen_calls[-6:]
    assert inventory_call["url"].endswith("/api/inventory") and inventory_call["timeout"] == api_client.SHORT_TIMEOUT_SECONDS
    assert options_call["url"].endswith("/api/history")
    assert product_call["url"].endswith("/api/history")
    assert ("product_name", "Milk") in product_call["params"]
    assert ("product_retailer", "Markets / Gurmar") in product_call["params"]
    assert averages_call["url"].endswith("/api/retailer-averages")
    assert ("aggregation", "Median") in averages_call["params"]
    assert movers_call["url"].endswith("/api/movers")
    assert ("scope_retailer", "All retailers") in movers_call["params"] and ("limit", 10) in movers_call["params"]
    assert coverage_call["url"].endswith("/api/coverage")
    assert ("category_limit", 20) in coverage_call["params"]
    for call in (options_call, product_call, averages_call, movers_call, coverage_call):
        assert call["timeout"] == api_client.DATA_TIMEOUT_SECONDS
        assert [name for name, _ in call["params"]].count("retailer") == 2

    with patch.object(
        api_client.requests,
        "get",
        return_value=FakeResponse(200, {"data": {}, "meta": {}}),
    ):
        try:
            api_client.fetch_inventory("http://localhost:8000")
        except api_client.ApiClientError as exc:
            assert "valid envelope" in str(exc)
        else:
            raise AssertionError("missing envelope keys should raise ApiClientError")

    with patch.object(
        api_client.requests,
        "get",
        return_value=FakeResponse(200, {"data": None, "meta": {}, "errors": [{"code": "invalid_filter", "message": "Bad"}]}),
    ):
        try:
            api_client.fetch_inventory("http://localhost:8000")
        except api_client.ApiClientError as exc:
            assert "Bad" in str(exc)
        else:
            raise AssertionError("non-empty errors should raise ApiClientError")

    with patch.object(
        api_client.requests,
        "get",
        return_value=FakeResponse(503, {"data": {"ignored": True}, "meta": {}, "errors": []}),
    ):
        try:
            api_client.fetch_inventory("http://localhost:8000")
        except api_client.ApiClientError as exc:
            assert "HTTP 503" in str(exc)
        else:
            raise AssertionError("non-2xx response should raise ApiClientError")

    with patch.object(
        api_client.requests,
        "get",
        return_value=FakeResponse(200, json_error=ValueError("no json")),
    ):
        try:
            api_client.fetch_inventory("http://localhost:8000")
        except api_client.ApiClientError as exc:
            assert "valid JSON" in str(exc)
        else:
            raise AssertionError("invalid JSON should raise ApiClientError")

    print("PASS behavior: client params, endpoint wrappers, envelope validation, ApiClientError, timeouts")


def main() -> int:
    _assert_streamlit_source()
    _assert_client_source()
    _assert_client_behavior()
    print("PASS final Phase 03 Streamlit API frontend verifier")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
