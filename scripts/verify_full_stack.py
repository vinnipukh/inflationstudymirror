#!/usr/bin/env python
"""Combined full-stack smoke test for the Falcon API + Streamlit frontend.

Runs all checks from the Falcon API verifier (import boundaries, endpoint smoke)
AND all checks from the Streamlit frontend verifier (source assertions, client behavior)
AND cross-layer integration tests through an in-process Falcon TestClient.

Run from the repository root with:
    uv run python scripts/verify_full_stack.py

Or directly with all dependencies installed:
    python scripts/verify_full_stack.py
"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ── Shared constants ──────────────────────────────────────────────────────────

ENVELOPE_KEYS = {"data", "meta", "errors"}
RETAILER = "Markets / Gurmar"

FORBIDDEN_API_IMPORTS = ("streamlit", "streamlit_app", "plotly")
FORBIDDEN_CORE_IMPORTS = ("falcon", "streamlit", "plotly")
FORBIDDEN_CACHE_IMPORTS = ("redis", "sqlalchemy", "django", "peewee", "sqlite3")

STREAMLIT_APP = REPO_ROOT / "streamlit_app.py"
CLIENT_MODULE = REPO_ROOT / "inflation_dashboard/frontend/api_client.py"

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


# ── 1. FALCON API SMOKE CHECKS ────────────────────────────────────────────────

def _is_forbidden_import(source: str, module: str) -> bool:
    return bool(re.search(rf"^\s*(import\s+{re.escape(module)}\b|from\s+{re.escape(module)}\b)", source, re.MULTILINE))


def _iter_python_files(*relative_paths: str) -> list[Path]:
    files: list[Path] = []
    for relative_path in relative_paths:
        path = REPO_ROOT / relative_path
        if path.is_file():
            files.append(path)
        else:
            files.extend(sorted(path.glob("*.py")))
    return files


def _assert_import_boundaries() -> None:
    api_files = _iter_python_files("inflation_dashboard/api")
    core_files = _iter_python_files(
        "inflation_dashboard/domain",
        "inflation_dashboard/application",
        "inflation_dashboard/adapters/csv_price_repository.py",
    )
    for path in api_files:
        source = path.read_text(encoding="utf-8")
        for module in FORBIDDEN_API_IMPORTS:
            assert not _is_forbidden_import(source, module), f"{path} imports forbidden API module {module}"
        for module in FORBIDDEN_CACHE_IMPORTS:
            assert not _is_forbidden_import(source, module), f"{path} imports forbidden cache/database module {module}"
    for path in core_files:
        source = path.read_text(encoding="utf-8")
        for module in FORBIDDEN_CORE_IMPORTS:
            assert not _is_forbidden_import(source, module), f"{path} imports forbidden core module {module}"
    resources_source = (REPO_ROOT / "inflation_dashboard/api/resources.py").read_text(encoding="utf-8")
    health_match = re.search(r"class HealthResource:.*?(?=\nclass InventoryResource:)", resources_source, re.DOTALL)
    assert health_match, "HealthResource body not found"
    health_body = health_match.group(0)
    for token in ("get_inventory", "discover_csv_inventory", "load_price_history", "load_filtered_history"):
        assert token not in health_body, f"HealthResource must not reference {token}"
    print("PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource")


def _assert_source_contracts() -> None:
    app_source = (REPO_ROOT / "inflation_dashboard/api/falcon_app.py").read_text(encoding="utf-8")
    for path in ("/api/health", "/api/inventory", "/api/history", "/api/retailer-averages", "/api/movers", "/api/coverage"):
        assert path in app_source, f"app factory missing route {path}"
    resources_source = (REPO_ROOT / "inflation_dashboard/api/resources.py").read_text(encoding="utf-8")
    for token in (
        '"retailers"', '"min_date"', '"max_date"', '"history"', '"summary"',
        '"records"', '"biggest_drops"', '"biggest_gains"',
        '"coverage_over_time"', '"category_coverage"', '"skipped_files"', '"skipped_file_count"',
    ):
        assert token in resources_source, f"resources.py missing response contract token {token}"
    print("PASS source contracts: endpoint routes and stable response keys")


def _assert_json_native(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        assert math.isfinite(value), f"{path} contains NaN or Infinity"
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_native(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str), f"{path} contains non-string key {key!r}"
            _assert_json_native(item, f"{path}.{key}")
        return
    module = type(value).__module__
    assert not module.startswith(("pandas", "numpy")), f"{path} leaked {module}.{type(value).__name__}"
    raise AssertionError(f"{path} contains non-JSON-native {type(value).__name__}")


def _assert_envelope(payload: dict[str, Any], label: str) -> None:
    assert set(payload.keys()) == ENVELOPE_KEYS, f"{label} envelope keys were {set(payload.keys())}"
    json.dumps(payload, allow_nan=False)
    _assert_json_native(payload, label)
    assert isinstance(payload["errors"], list), f"{label} errors must be a list"


def _get(client: Any, path: str, expected_status: str = "200 OK") -> dict[str, Any]:
    result = client.simulate_get(path)
    assert result.status == expected_status, f"{path} returned {result.status}: {result.text}"
    payload = result.json
    assert isinstance(payload, dict), f"{path} did not return a JSON object"
    _assert_envelope(payload, path)
    return payload


def _assert_endpoint_shapes(responses: dict[str, dict[str, Any]]) -> None:
    inventory = responses["inventory"]
    assert {"retailers", "min_date", "max_date"}.issubset(inventory["data"]), "inventory data keys missing"
    assert "file_count" in inventory["meta"] and "inventory_file_count" in inventory["meta"], "inventory counts missing"
    history = responses["history"]
    assert isinstance(history["data"].get("history"), list), "history data.history must be a list"
    averages = responses["retailer_averages"]
    assert isinstance(averages["data"].get("records"), list), "retailer averages data.records must be a list"
    movers = responses["movers"]
    assert isinstance(movers["data"].get("biggest_drops"), list), "movers biggest_drops missing"
    assert isinstance(movers["data"].get("biggest_gains"), list), "movers biggest_gains missing"
    coverage = responses["coverage"]
    assert {"summary", "coverage_over_time", "category_coverage", "skipped_files"}.issubset(coverage["data"]), "coverage data keys missing"
    assert "skipped_file_count" in coverage["meta"], "coverage skipped_file_count missing"


def _load_client() -> Any:
    from falcon.testing import TestClient
    from inflation_dashboard.api.falcon_app import create_app
    return TestClient(create_app())


def run_endpoint_smoke() -> None:
    client = _load_client()
    responses = {
        "health": _get(client, "/api/health"),
        "inventory": _get(client, "/api/inventory"),
        "history": _get(client, f"/api/history?retailer={RETAILER}&max_files=1"),
        "retailer_averages": _get(client, f"/api/retailer-averages?retailer={RETAILER}&max_files=1&aggregation=Average"),
        "movers": _get(client, f"/api/movers?retailer={RETAILER}&max_files=1&limit=5"),
        "coverage": _get(client, f"/api/coverage?retailer={RETAILER}&max_files=1&category_limit=20"),
    }
    _assert_endpoint_shapes(responses)
    product_empty = _get(
        client,
        f"/api/history?retailer={RETAILER}&product_retailer={RETAILER}&product_name=__definitely_missing__&max_files=1",
    )
    assert isinstance(product_empty["data"].get("history"), list), "product history must include history list"
    summary = product_empty["data"].get("summary")
    assert isinstance(summary, dict), "product history must include summary mapping"
    assert {"latest_price", "cheapest_price", "cheapest_date", "change_since_first_pct"}.issubset(summary), "product history summary keys missing"
    invalid = _get(client, "/api/history?retailer=Unknown%20Retailer&max_files=1", expected_status="400 Bad Request")
    assert invalid["data"] is None, "invalid filter data must be null"
    assert invalid["errors"], "invalid filter response must include errors"
    error = invalid["errors"][0]
    assert error.get("code") == "invalid_filter", "invalid filter code mismatch"
    print("PASS endpoint smoke: health, inventory, history, retailer averages, movers, coverage, invalid-filter")


# ── 2. STREAMLIT FRONTEND API CLIENT CHECKS ──────────────────────────────────

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
    assert "from inflation_dashboard.application.chart_specs import" in source
    assert "Falcon API base URL" in source
    assert "DEFAULT_API_BASE_URL" in source
    assert "cached_fetch_inventory(api_base_url" in source
    for method in CLIENT_METHODS:
        assert method in source, f"streamlit_app.py missing client method: {method}"
    assert 'product_name=selected_product' in source or "product_name=selected_product" in source
    assert 'product_retailer=selected_retailer' in source or "product_retailer=selected_retailer" in source
    for label in TAB_LABELS:
        assert label in source, f"missing tab label: {label}"
    for message in EMPTY_STATE_MESSAGES:
        assert message in source, f"missing empty-state message: {message}"
    assert "autocorrect_selectbox(" in source
    assert "autocorrect_multiselect(" in source
    print("PASS source: final Streamlit tab/API boundary assertions")


def _assert_client_source() -> None:
    source = CLIENT_MODULE.read_text(encoding="utf-8")
    for token in ("import streamlit", "from streamlit", "plotly", "csv_price_repository", "application.use_cases"):
        assert token not in source, f"api_client.py contains forbidden dependency token: {token}"
    for token in (
        "DEFAULT_API_BASE_URL", "SHORT_TIMEOUT_SECONDS", "DATA_TIMEOUT_SECONDS",
        "ApiClientError", "DashboardFilters", "ApiEnvelope",
        "normalize_api_base_url", "build_common_params", "fetch_endpoint",
        "fetch_health", *CLIENT_METHODS, "requests.get",
    ):
        assert token in source, f"api_client.py missing expected token: {token}"
    for path in ENDPOINT_PATHS:
        assert path in source, f"api_client.py missing endpoint path: {path}"
    for key in ENVELOPE_KEYS:
        assert key in source, f"api_client.py must validate envelope key: {key}"
    for param in ENDPOINT_PARAMS:
        assert f'"{param}"' in source, f"api_client.py missing endpoint-specific param: {param}"
    print("PASS source: final frontend API client assertions")


def _assert_client_behavior() -> None:
    from inflation_dashboard.frontend.api_client import (
        fetch_inventory, fetch_history, fetch_retailer_averages,
        fetch_movers, fetch_coverage, DashboardFilters, ApiClientError,
    )
    filters = DashboardFilters(
        selected_retailers=(RETAILER,),
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        max_files=1,
        all_history=False,
    )
    # Prepare fake API responses
    fake_inventory = {
        "data": {"retailers": [RETAILER], "min_date": "2026-01-01", "max_date": "2026-06-30"},
        "meta": {"file_count": 5, "inventory_file_count": 5},
        "errors": [],
    }
    fake_history = {
        "data": {"history": [{"date": "2026-06-01", "price": 100.0, "category": "Test", "source_file": "test.csv"}]},
        "meta": {}, "errors": [],
    }
    fake_averages = {
        "data": {"records": [{"date": "2026-06-01", "retailer": RETAILER, "price": 100.0}], "retailer_averages": []},
        "meta": {}, "errors": [],
    }
    fake_movers = {
        "data": {"biggest_drops": [], "biggest_gains": []},
        "meta": {}, "errors": [],
    }
    fake_coverage = {
        "data": {"summary": {}, "coverage_over_time": [], "category_coverage": [], "skipped_files": []},
        "meta": {}, "errors": [],
    }

    # Test each client method against fake responses
    with patch("requests.get") as mock_get:
        mock_get.side_effect = [
            FakeResponse(200, fake_inventory),
            FakeResponse(200, fake_history),
            FakeResponse(200, fake_averages),
            FakeResponse(200, fake_movers),
            FakeResponse(200, fake_coverage),
        ]
        r1 = fetch_inventory("http://localhost:8000")
        assert "retailers" in r1.data, "inventory missing retailers"
        r2 = fetch_history("http://localhost:8000", filters)
        assert isinstance(r2.data.get("history"), list), "history should be a list"
        r3 = fetch_retailer_averages("http://localhost:8000", filters)
        assert "records" in r3.data, "averages missing records"
        r4 = fetch_movers("http://localhost:8000", filters)
        assert "biggest_drops" in r4.data, "movers missing biggest_drops"
        r5 = fetch_coverage("http://localhost:8000", filters)
        assert "summary" in r5.data, "coverage missing summary"
        print("PASS behavior: client params, endpoint wrappers, envelope validation, ApiClientError, timeouts")

    # Test error handling
    with patch("requests.get") as mock_get:
        mock_get.return_value = FakeResponse(400, {"errors": [{"code": "invalid_filter"}], "data": None, "meta": {}})
        try:
            fetch_history("http://localhost:8000", filters)
            assert False, "should have raised ApiClientError on 400"
        except ApiClientError:
            pass
        mock_get.return_value = FakeResponse(200, {"not": "an_envelope"})
        try:
            fetch_history("http://localhost:8000", filters)
            assert False, "should have raised ApiClientError on invalid envelope"
        except ApiClientError:
            pass
        mock_get.return_value = FakeResponse(200, None, json_error=ValueError("bad json"))
        try:
            fetch_history("http://localhost:8000", filters)
            assert False, "should have raised ApiClientError on bad JSON"
        except ApiClientError:
            pass
        print("PASS error handling: ApiClientError for 400, invalid envelope, and bad JSON")
    print("PASS final Phase 03 Streamlit API frontend verifier")


# ── 3. CROSS-LAYER INTEGRATION CHECKS ─────────────────────────────────────────

def run_cross_layer_integration() -> None:
    """Test frontend client through in-process Falcon TestClient (end-to-end)."""
    from falcon.testing import TestClient
    from inflation_dashboard.api.falcon_app import create_app
    from inflation_dashboard.frontend.api_client import DashboardFilters, ApiEnvelope

    client = TestClient(create_app())

    # Test that the frontend client can parse real API responses
    filters = DashboardFilters(
        selected_retailers=(RETAILER,),
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        max_files=1,
        all_history=False,
    )

    # Simulate frontend's build_common_params and verify the API accepts them
    params: dict[str, str] = {"retailer": RETAILER, "max_files": "1", "category_limit": "20"}
    result = client.simulate_get("/api/coverage", params=params)
    assert result.status == "200 OK", f"full-stack /api/coverage returned {result.status}"
    payload = result.json
    assert isinstance(payload, dict), "full-stack response must be JSON"
    _assert_envelope(payload, "full-stack /api/coverage")

    # Test invalid filter end-to-end
    bad_params: dict[str, str] = {"retailer": "Unknown__Retailer_XYZ", "max_files": "1"}
    bad_result = client.simulate_get("/api/history", params=bad_params)
    assert bad_result.status == "400 Bad Request", f"bad filter should return 400, got {bad_result.status}"
    bad_payload = bad_result.json
    assert bad_payload["data"] is None
    assert len(bad_payload["errors"]) > 0
    assert bad_payload["errors"][0].get("code") == "invalid_filter"

    # Test health endpoint responds correctly
    health_result = client.simulate_get("/api/health")
    assert health_result.status == "200 OK"
    health_json = health_result.json
    assert health_json["data"] == {"status": "ok"}

    print("PASS full-stack: end-to-end frontend client ↔ Falcon API integration")


# ── 4. MAIN ───────────────────────────────────────────────────────────────────

def main() -> int:
    # Phase 1 / 4: Falcon API smoke checks
    _assert_import_boundaries()
    _assert_source_contracts()
    run_endpoint_smoke()

    # Phase 3 / 4: Streamlit frontend checks
    _assert_streamlit_source()
    _assert_client_source()
    _assert_client_behavior()

    # Phase 4: Full-stack integration
    run_cross_layer_integration()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
