from __future__ import annotations

import logging
import os
import time

import falcon

import orjson

from inflation_dashboard.api import resources

_LOGGER = logging.getLogger("inflation_dashboard.api.timing")


class TimingMiddleware:
    """Per-request duration + cache-hit logging, opt-in via FALCON_TIMING_LOG=1.

    Does no measurable work when disabled (one attribute read per request).
    When enabled, records a perf_counter in ``process_request`` and emits one
    INFO line per request with method, path, status, duration and whether the
    response came from the pre-serialized byte cache.
    """

    enabled: bool

    def __init__(self) -> None:
        self.enabled = os.getenv("FALCON_TIMING_LOG", "").strip().lower() in {"1", "true", "yes", "on"}

    def process_request(self, req: object, resp: object) -> None:
        if self.enabled:
            req.context["_started_at"] = time.perf_counter()

    def process_response(self, req: object, resp: object, resource: object, req_succeeded: bool | None = None) -> None:
        if not self.enabled:
            return
        started_at = req.context.get("_started_at")
        if started_at is None:
            return
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        _LOGGER.info(
            "falcon_request method=%s path=%s status=%s duration_ms=%.2f cache_hit=%s",
            req.method,
            req.path,
            resp.status,
            duration_ms,
            req.context.get("_cache_hit", False),
        )

# orjson serializes large record payloads several times faster than stdlib
# json.dumps; every value leaving the API is already JSON-native (NaN/NaT are
# mapped to None by serialization.to_json_value), so orjson's strict mode is
# safe.
_JSON_HANDLER = falcon.media.JSONHandler(dumps=orjson.dumps, loads=orjson.loads)

# Cross-origin access for the Svelte frontend (documented in
# docs/FALCON_API_CONTRACT.md and docs/ARCHITECTURE.md). The launcher
# (scripts/run_falcon_server.py) exposes this as --cors-origins /
# FALCON_CORS_ORIGINS; default is open access ("*").
def _cors_middleware():
    raw_origins = os.getenv("FALCON_CORS_ORIGINS", "*")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    # Falcon requires the "*" wildcard as a plain string, not inside a list.
    allow_origins: str | list[str] = "*" if origins == ["*"] else origins
    # Falcon's CORSMiddleware handles GET/OPTIONS preflights automatically.
    return falcon.CORSMiddleware(allow_origins=allow_origins, expose_headers=[])


def create_app() -> falcon.App:
    """Create the Falcon WSGI application and register API resources."""

    app = falcon.App(middleware=[TimingMiddleware(), _cors_middleware()])
    app.req_options.media_handlers[falcon.MEDIA_JSON] = _JSON_HANDLER
    app.resp_options.media_handlers[falcon.MEDIA_JSON] = _JSON_HANDLER
    app.add_route("/api/health", resources.HealthResource())
    app.add_route("/api/inventory", resources.InventoryResource())
    app.add_route("/api/history", resources.HistoryResource())
    app.add_route("/api/retailer-averages", resources.RetailerAveragesResource())
    app.add_route("/api/movers", resources.MoversResource())
    app.add_route("/api/coverage", resources.CoverageResource())
    app.add_route("/api/products/search", resources.ProductSearchResource())
    # compile=True on the final route forces the router decision tree to be
    # built at startup instead of lazily on the first request of each worker
    # (per Falcon docs: only set it on the LAST add_route call).
    app.add_route("/api/product", resources.ProductDetailResource(), compile=True)
    return app
