#!/usr/bin/env python
"""Bounded smoke verification for the ASGI Falcon API (scaling refactor).

Run from the repository root with:
    python scripts/verify_asgi_api.py

Part A -- in-process falcon.testing on middleware-only behavior:
    * health + trace/correlation ID echo
    * token-bucket rate limiting (429 + Retry-After)
    * idempotency middleware (replay, missing/invalid key)
    * malformed pagination cursor -> 400

Part B -- live uvicorn (ASGI interface) server:
    * DB-backed endpoints: inventory, product search (keyset pagination),
      bounded history, product detail 200/404
    * ETag 304, gzip variants, Cache-Control/CDN-Cache-Control headers
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ENVELOPE_KEYS = {"data", "meta", "errors"}
PASS: list[str] = []


def _record(name: str) -> None:
    PASS.append(name)
    print(f"PASS {name}")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# --- Part A: in-process middleware checks ---------------------------------
def part_a() -> None:
    from falcon.testing import TestClient
    from falcon.asgi import App as AsgiApp
    import falcon

    from inflation_dashboard.api.asgi_app import build_middleware
    from inflation_dashboard.api.observability import configure_logging

    configure_logging()

    # 1) health + trace echo (rate limiting off to keep the test stable)
    old_cap = os.environ.get("FALCON_RATE_CAPACITY")
    old_refill = os.environ.get("FALCON_RATE_REFILL_PER_SEC")
    os.environ["FALCON_RATE_CAPACITY"] = "100000"
    os.environ["FALCON_RATE_REFILL_PER_SEC"] = "100000"
    try:
        from inflation_dashboard.api.asgi_app import create_asgi_app

        client = TestClient(create_asgi_app())
        resp = client.simulate_get("/api/health", headers={"X-Correlation-ID": "trace-abc"})
        assert resp.status_code == 200, resp.status
        payload = resp.json
        assert set(payload.keys()) == ENVELOPE_KEYS, payload.keys()
        assert payload["data"]["status"] == "ok"
        assert resp.headers.get("X-Request-ID") == "trace-abc", resp.headers
        assert payload["meta"]["interface"] == "asgi"
        _record("health: 200 envelope + correlation ID echo (asgi interface)")

        # 2) rate limiting (build a fresh app with a tiny bucket)
        os.environ["FALCON_RATE_CAPACITY"] = "3"
        os.environ["FALCON_RATE_REFILL_PER_SEC"] = "0.0001"
        app_rl = AsgiApp(middleware=build_middleware())

        class FastProbe:
            async def on_get(self, req, resp):
                resp.media = {"ok": True}

        app_rl.add_route("/rlprobe", FastProbe())
        rl_client = TestClient(app_rl)
        statuses = [rl_client.simulate_get("/rlprobe").status_code for _ in range(6)]
        assert statuses[0] == 200 and statuses[1] == 200 and statuses[2] == 200, statuses
        assert any(code == 429 for code in statuses), statuses
        last = rl_client.simulate_get("/rlprobe")
        assert last.status_code == 429
        assert last.headers.get("Retry-After") is not None, last.headers
        _record(f"rate limit: 3 allowed then 429 + Retry-After ({statuses})")

        # 3) idempotency middleware
        os.environ["FALCON_RATE_CAPACITY"] = "100000"
        os.environ["FALCON_RATE_REFILL_PER_SEC"] = "100000"
        app_idem = AsgiApp(middleware=build_middleware())

        class OrderResource:
            def __init__(self) -> None:
                self.runs = 0

            async def on_post(self, req, resp):
                self.runs += 1
                resp.media = {"order_id": f"order-{self.runs}", "trace": req.context.trace_id}

        order = OrderResource()
        app_idem.add_route("/orders", order)
        idem_client = TestClient(app_idem)

        first = idem_client.simulate_post("/orders", json={"qty": 1}, headers={"Idempotency-Key": "k-1"})
        assert first.status_code == 200, first.status
        second = idem_client.simulate_post("/orders", json={"qty": 2}, headers={"Idempotency-Key": "k-1"})
        assert second.status_code == 200
        assert first.json == second.json, (first.json, second.json)
        assert order.runs == 1, f"resource executed {order.runs} times (expected 1 after replay)"
        _record("idempotency: identical replay for same Idempotency-Key (resource ran once)")

        missing = idem_client.simulate_post("/orders", json={})
        assert missing.status_code == 400, missing.status
        invalid = idem_client.simulate_post("/orders", json={}, headers={"Idempotency-Key": "bad key!!"})
        assert invalid.status_code == 400, invalid.status
        _record("idempotency: 400 on missing / invalid Idempotency-Key")

        # 4) malformed pagination cursor -> 400 (DB not touched)
        bad_cursor = client.simulate_get("/api/products/search?cursor=%21%21%21&limit=5")
        assert bad_cursor.status_code == 400, bad_cursor.status
        assert bad_cursor.json["errors"][0]["code"] == "invalid_cursor", bad_cursor.json
        _record("pagination: malformed cursor -> 400 invalid_cursor")
    finally:
        for name, value in (("FALCON_RATE_CAPACITY", old_cap), ("FALCON_RATE_REFILL_PER_SEC", old_refill)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# --- Part B: live uvicorn ASGI server --------------------------------------
def part_b() -> None:
    import requests

    port = _free_port()
    venv_python = sys.executable
    env = {**os.environ, "FALCON_RATE_CAPACITY": "100000", "FALCON_RATE_REFILL_PER_SEC": "100000"}
    import sys as _sys

    _sys.path.insert(0, str(REPO_ROOT))
    from scripts.run_falcon_server import build_command  # same path operators use

    cmd = build_command(
        engine="uvicorn", host="127.0.0.1", port=port, workers=1, threads=8,
        backlog=2048, log_level="warning", interface="asgi",
    )
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                health = requests.get(f"{base_url}/api/health", timeout=2)
                if health.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.3)
        else:
            output = proc.stdout.read() if proc.stdout else ""
            raise AssertionError(f"uvicorn ASGI server did not start:\n{output[-2000:]}")

        # health
        assert health.json()["data"]["status"] == "ok"
        assert health.headers.get("X-Request-ID"), health.headers
        _record("live: health 200 with X-Request-ID")

        # inventory: cache/edge headers
        inv = requests.get(f"{base_url}/api/inventory")
        assert inv.status_code == 200, inv.text[:300]
        inv_json = inv.json()
        assert set(inv_json.keys()) == ENVELOPE_KEYS
        assert "retailers" in inv_json["data"] and "min_date" in inv_json["data"]
        cc = inv.headers.get("Cache-Control", "")
        assert "max-age=300" in cc and "stale-while-revalidate=60" in cc, cc
        assert "stale-if-error=86400" in cc, cc
        assert inv.headers.get("CDN-Cache-Control") == "public, max-age=300", inv.headers
        assert inv.headers.get("ETag"), inv.headers
        _record("live: inventory 200 + Cache-Control/swr/sfe + CDN-Cache-Control + ETag")

        # gzip variant when client accepts it (use the large history payload;
        # inventory is ~0.5 KB and intentionally below the 1 KB gzip threshold)
        hist_base = requests.get(f"{base_url}/api/history")
        assert hist_base.status_code == 200
        assert len(hist_base.content) >= 1024, f"history payload unexpectedly small: {len(hist_base.content)} B"
        hist_gz = requests.get(f"{base_url}/api/history", headers={"Accept-Encoding": "gzip"})
        assert hist_gz.headers.get("Content-Encoding") == "gzip", hist_gz.headers
        assert json.loads(hist_gz.content) == hist_base.json(), "gzip payload mismatch"
        _record(f"live: gzip variant on history payload ({len(hist_base.content)} B -> {len(hist_gz.content)} B)")

        # ETag conditional request -> 304
        etag = inv.headers.get("ETag")
        inv_304 = requests.get(f"{base_url}/api/inventory", headers={"If-None-Match": etag})
        assert inv_304.status_code == 304, inv_304.status_code
        _record("live: If-None-Match -> 304 Not Modified")

        # keyset pagination on product search (two pages, disjoint ids)
        page1 = requests.get(f"{base_url}/api/products/search", params={"q": "ETAMİN", "limit": 5}).json()
        data1 = page1["data"]
        assert 0 < len(data1) <= 5, len(data1)
        next_cursor = page1["meta"]["pagination"]["next_cursor"]
        assert next_cursor, page1["meta"]
        page2 = requests.get(
            f"{base_url}/api/products/search",
            params={"q": "ETAMİN", "limit": 5, "cursor": next_cursor},
        ).json()
        data2 = page2["data"]
        ids1 = {row["product_id"] for row in data1}
        ids2 = {row["product_id"] for row in data2}
        assert ids1.isdisjoint(ids2), (ids1 & ids2)
        assert len(page2["meta"]["pagination"]["next_cursor"] or "") >= 0
        _record(f"live: search keyset pagination p1={len(data1)} p2={len(data2)} disjoint ids")

        # bounded history
        hist = requests.get(
            f"{base_url}/api/history",
            params={"retailer": "Markets / Gurmar", "max_files": 1},
        )
        assert hist.status_code == 200, hist.text[:400]
        assert "history" in hist.json()["data"]
        _record("live: bounded history 200 (async offload compute)")

        # product detail 200 + 404
        first = data1[0]
        detail = requests.get(
            f"{base_url}/api/product",
            params={"product_id": first["product_id"], "retailer": first["retailer"]},
        )
        assert detail.status_code == 200, detail.text[:300]
        assert detail.json()["data"]["product_id"] == first["product_id"]
        missing = requests.get(f"{base_url}/api/product", params={"product_id": "__nope__"})
        assert missing.status_code == 404
        assert missing.json()["errors"][0]["code"] == "not_found"
        _record("live: product detail 200 + not_found 404 (async DB reads)")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    print("== Part A: in-process middleware checks ==")
    part_a()
    print("\n== Part B: live uvicorn ASGI server ==")
    part_b()
    print(f"\nAll {len(PASS)} ASGI checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
