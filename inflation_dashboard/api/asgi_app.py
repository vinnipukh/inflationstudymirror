"""
ASGI application factory (falcon.asgi.App) -- the high-scale entry point.

Serves the same route table as the WSGI factory (falcon_app.create_app) but
with the full ASGI middleware stack and async resources:

    TraceID -> Session -> RateLimit -> Idempotency -> CacheControl -> CORS

Run with uvicorn or Granian (ASGI interface), e.g.::

    python scripts/run_falcon_server.py --interface asgi          # uvicorn
    python scripts/run_falcon_server.py --interface asgi --engine granian

or directly::

    uvicorn inflation_dashboard.api.asgi_app:create_asgi_app --factory --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os

import falcon
import falcon.asgi  # noqa: F401  (explicit: parent pkg does not re-export the submodule)

import orjson

from inflation_dashboard.api import resources_asgi
from inflation_dashboard.api.middleware import (
    CacheControlMiddleware,
    IdempotencyMiddleware,
    RateLimitMiddleware,
    SessionMiddleware,
)
from inflation_dashboard.api.observability import TraceIDMiddleware, configure_logging

_JSON_HANDLER = falcon.media.JSONHandler(dumps=orjson.dumps, loads=orjson.loads)


def _cors_middleware():
    raw_origins = os.getenv("FALCON_CORS_ORIGINS", "*")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    allow_origins: str | list[str] = "*" if origins == ["*"] else origins
    return falcon.CORSMiddleware(allow_origins=allow_origins, expose_headers=[])


def build_middleware() -> list:
    """Build the ordering-sensitive middleware stack (exported for tests)."""
    return [
        TraceIDMiddleware(),
        SessionMiddleware(),
        RateLimitMiddleware(),
        IdempotencyMiddleware(),
        CacheControlMiddleware(),
        _cors_middleware(),
    ]


async def _json_error_handler(req, resp, ex, params):
    from inflation_dashboard.api.serialization import error_envelope

    exc_class = type(ex).__name__
    resp.status = falcon.HTTP_500
    resp.media = error_envelope(
        "server_error",
        f"Internal server error ({exc_class})",
        meta={"trace_id": getattr(req.context, "trace_id", None)},
    )


def create_asgi_app() -> falcon.asgi.App:
    """Create the Falcon ASGI application with the production middleware stack."""

    configure_logging()
    app = falcon.asgi.App(middleware=build_middleware())
    app.req_options.media_handlers[falcon.MEDIA_JSON] = _JSON_HANDLER
    app.resp_options.media_handlers[falcon.MEDIA_JSON] = _JSON_HANDLER

    app.add_route("/api/health", resources_asgi.HealthResource())
    app.add_route("/api/inventory", resources_asgi.InventoryResource())
    app.add_route("/api/history", resources_asgi.HistoryResource())
    app.add_route("/api/retailer-averages", resources_asgi.RetailerAveragesResource())
    app.add_route("/api/movers", resources_asgi.MoversResource())
    app.add_route("/api/coverage", resources_asgi.CoverageResource())
    app.add_route("/api/products/search", resources_asgi.ProductSearchResource())
    # compile=True on the final route pre-builds the router decision tree.
    app.add_route("/api/product", resources_asgi.ProductDetailResource(), compile=True)

    app.add_error_handler(Exception, _json_error_handler)
    return app
