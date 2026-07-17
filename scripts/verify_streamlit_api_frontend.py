#!/usr/bin/env python
"""Verify the Phase 03-01 Streamlit/Falcon frontend boundary.

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
    "discover_csv_inventory()",
    "load_price_history_uncached(",
    "chosen_inventory = inventory[",
)
TAB_LABELS = ("Product explorer", "Retailer averages", "Price movers", "Coverage overview")
AUTOCORRECT_HELPERS = (
    "normalize_search_text",
    "rank_search_options",
    "autocorrect_selectbox",
    "autocorrect_multiselect",
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

    assert "Falcon API base URL" in source, "sidebar must expose visible Falcon API base URL control"
    assert "DEFAULT_API_BASE_URL" in source and "http://localhost:8000" not in source, (
        "streamlit_app.py should use the client default API base URL constant"
    )
    assert "fetch_inventory" in source or "/api/inventory" in source, "sidebar inventory must use API inventory"
    assert "cached_fetch_inventory(api_base_url" in source, "inventory cache key must include api_base_url"
    assert "cached_fetch_api_endpoint(" in source and "api_base_url: str" in source and "params:" in source, (
        "cached data endpoint wrapper must include API base URL and filter params"
    )
    assert "DashboardFilters(" in source, "Streamlit must construct shared DashboardFilters"
    assert "build_common_params(filters)" in source, "Streamlit must prepare shared common params"
    assert "Load all files in date range" in source, "all-history checkbox label must be preserved"
    assert "effective_limit = 0 if load_all_history else max_files_per_retailer" in source, (
        "all-history must map to max_files=0 semantics"
    )
    assert "FRONTEND_DEFAULT_RETAILERS" in source and "FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER" in source, (
        "sidebar defaults must come from frontend constants, not CSV adapter constants"
    )
    assert "st.error" in source and "ApiClientError" in source and "st.stop" in source, (
        "ApiClientError must be surfaced with st.error and stop affected rendering"
    )
    assert "st.info" in source, "valid empty inventory/data states should have visible info messaging"

    for label in TAB_LABELS:
        assert label in source, f"missing tab label: {label}"
    for helper in AUTOCORRECT_HELPERS:
        assert re.search(rf"def\s+{helper}\b", source), f"missing helper definition: {helper}"
    assert "autocorrect_multiselect(" in source and "Retailers to load" in source, (
        "sidebar retailer selector must keep autocorrect_multiselect"
    )

    if "from inflation_dashboard.application.use_cases import" in source:
        print("ALLOW until 03-02: remaining tab use-case imports detected")
    else:
        print("PASS source: no application use-case imports remain in streamlit_app.py")

    print("PASS source: Streamlit sidebar/API boundary assertions")


def _assert_client_source() -> None:
    source = CLIENT_MODULE.read_text(encoding="utf-8")
    for token in ("import streamlit", "from streamlit", "plotly", "csv_price_repository", "application.use_cases"):
        assert token not in source, f"api_client.py contains forbidden dependency token: {token}"
    for token in (
        "DEFAULT_API_BASE_URL",
        "FRONTEND_DEFAULT_RETAILERS",
        "FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER",
        "SHORT_TIMEOUT_SECONDS = 10",
        "DATA_TIMEOUT_SECONDS = 60",
        "ApiClientError",
        "DashboardFilters",
        "ApiEnvelope",
        "normalize_api_base_url",
        "build_common_params",
        "fetch_endpoint",
        "fetch_health",
        "fetch_inventory",
        "fetch_history",
        "fetch_retailer_averages",
        "fetch_movers",
        "fetch_coverage",
        "requests.get",
    ):
        assert token in source, f"api_client.py missing expected token: {token}"
    for key in ENVELOPE_KEYS:
        assert key in source, f"api_client.py must validate envelope key: {key}"
    print("PASS source: frontend API client boundary assertions")


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

    seen: dict[str, Any] = {}

    def fake_get(url: str, params: Any = None, timeout: int | None = None) -> FakeResponse:
        seen["url"] = url
        seen["params"] = params
        seen["timeout"] = timeout
        return FakeResponse(200, {"data": {"ok": True}, "meta": {"request_id": "test"}, "errors": []})

    with patch.object(api_client.requests, "get", side_effect=fake_get):
        envelope = api_client.fetch_endpoint("http://localhost:8000/", "/api/history", params, timeout=60)
    assert envelope.data == {"ok": True}
    assert seen["url"] == "http://localhost:8000/api/history"
    assert seen["params"] == params, "request must preserve list-of-pairs params"
    assert seen["timeout"] == 60

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

    with patch.object(api_client.requests, "get", side_effect=fake_get):
        api_client.fetch_inventory("http://localhost:8000")
    assert seen["timeout"] == api_client.SHORT_TIMEOUT_SECONDS

    print("PASS behavior: client params, envelope validation, ApiClientError, timeouts")


def main() -> int:
    _assert_streamlit_source()
    _assert_client_source()
    _assert_client_behavior()
    print("PASS 03-01 Streamlit API frontend verifier")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
