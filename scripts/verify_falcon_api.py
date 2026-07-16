#!/usr/bin/env python
"""Bounded Falcon API smoke verification for Phase 02.

Run from the repository root with:
    python scripts/verify_falcon_api.py

The script uses Falcon's in-process TestClient only; it does not bind ports or
start a long-running server.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ENVELOPE_KEYS = {"data", "meta", "errors"}
RETAILER = "Markets / Gurmar"


def _load_client() -> Any:
    try:
        from falcon.testing import TestClient
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Falcon is missing. Install project dependency metadata with the user's uv workflow "
            "(for example: uv sync or uv pip install -r requirements.txt), then rerun "
            "python scripts/verify_falcon_api.py."
        ) from exc

    from inflation_dashboard.api.falcon_app import create_app

    return TestClient(create_app())


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
    assert {"summary", "coverage_over_time", "category_coverage", "skipped_files"}.issubset(coverage["data"]), (
        "coverage data keys missing"
    )
    assert "skipped_file_count" in coverage["meta"], "coverage skipped_file_count missing"


def run_endpoint_smoke() -> None:
    client = _load_client()
    responses = {
        "health": _get(client, "/api/health"),
        "inventory": _get(client, "/api/inventory"),
        "history": _get(client, f"/api/history?retailer={RETAILER}&max_files=1"),
        "retailer_averages": _get(
            client,
            f"/api/retailer-averages?retailer={RETAILER}&max_files=1&aggregation=Average",
        ),
        "movers": _get(client, f"/api/movers?retailer={RETAILER}&max_files=1&limit=5"),
        "coverage": _get(client, f"/api/coverage?retailer={RETAILER}&max_files=1&category_limit=20"),
    }
    _assert_endpoint_shapes(responses)

    invalid = _get(client, "/api/history?retailer=Unknown%20Retailer&max_files=1", expected_status="400 Bad Request")
    assert invalid["data"] is None, "invalid filter data must be null"
    assert invalid["errors"], "invalid filter response must include errors"
    error = invalid["errors"][0]
    assert error.get("code") == "invalid_filter", "invalid filter code mismatch"
    assert isinstance(error.get("message"), str) and 0 < len(error["message"]) <= 160, "invalid error message"

    print("PASS endpoint smoke: health, inventory, history, retailer averages, movers, coverage, invalid-filter")


def main() -> int:
    run_endpoint_smoke()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
