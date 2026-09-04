"""
Structured JSON logging and trace/correlation-ID middleware (principle 9).

Every request receives a trace ID (client-supplied ``X-Request-ID`` /
``X-Correlation-ID`` when present, otherwise a generated UUID). The ID is
stored in ``req.context.trace_id`` (principle 1: request-scoped state only),
echoed on the response, and bound to structlog contextvars so every log line
emitted while the request is in flight carries it.

Log output is JSON via structlog + orjson:
    {"event": "request_processed", "trace_id": "...", "method": "GET",
     "path": "/api/history", "status": "200 OK", "duration_ms": 12.3,
     "cache_hit": false, "req_succeeded": true, "client_ip": "..."}
"""

from __future__ import annotations

import os
import time
import uuid

import structlog

import orjson

logger = structlog.get_logger(__name__)


def configure_logging() -> None:
    """Configure structlog for JSON line output (idempotent per process)."""

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(serializer=orjson.dumps),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging_level(), "levelno", 20)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def logging_level() -> int | None:
    """Resolve FALCON_LOG_LEVEL (or LOG_LEVEL) to a logging level."""
    import logging

    name = os.environ.get("FALCON_LOG_LEVEL") or os.environ.get("LOG_LEVEL") or "info"
    return logging.getLevelName(name.upper())


def new_trace_id() -> str:
    return uuid.uuid4().hex


_TRACE_HEADERS = ("X-Request-ID", "X-Correlation-ID")


class TraceIDMiddleware:
    """Correlation-ID middleware: bind, echo, and log one structured line."""

    async def process_request(self, req, resp) -> None:
        trace_id = None
        for header in _TRACE_HEADERS:
            value = req.get_header(header)
            if value:
                trace_id = str(value).strip()[:128]
                break
        if not trace_id:
            trace_id = new_trace_id()
        req.context.trace_id = trace_id
        req.context.started_at = time.perf_counter()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            method=req.method,
            path=req.path,
        )

    async def process_response(self, req, resp, resource, req_succeeded: bool | None = None) -> None:
        trace_id = getattr(req.context, "trace_id", None)
        if trace_id:
            resp.set_header("X-Request-ID", trace_id)
        started_at = getattr(req.context, "started_at", None)
        duration_ms = (time.perf_counter() - started_at) * 1000.0 if started_at else None
        await logger.ainfo(
            "request_processed",
            status=str(resp.status),
            duration_ms=round(duration_ms, 2) if duration_ms is not None else None,
            cache_hit=getattr(req.context, "_cache_hit", False),
            req_succeeded=req_succeeded,
            client_ip=(req.access_route[0] if req.access_route else req.remote_addr),
            store_backend=getattr(req.context, "store_backend", None),
        )
        structlog.contextvars.clear_contextvars()
