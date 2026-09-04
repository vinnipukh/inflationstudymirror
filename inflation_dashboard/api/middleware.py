"""
Core Falcon ASGI middleware stack (principles 1, 2, 3, 5, 6, 7).

* SessionMiddleware      -- binds request-scoped state (store, DB session,
                            queue) to ``req.context``; never mutates ``self``
                            per request (principle 1 + 2).
* RateLimitMiddleware    -- Redis token bucket per (route, client IP) with a
                            per-process fallback; 429 + Retry-After (7).
* IdempotencyMiddleware  -- Idempotency-Key handling for unsafe methods with
                            a distributed lock and response replay (5).
* CacheControlMiddleware -- centralized edge-cache headers: Cache-Control,
                            CDN-Cache-Control, stale-while-revalidate and
                            stale-if-error (6).

Middleware order (as registered in asgi_app.create_asgi_app):
    [TraceID, Session, RateLimit, Idempotency, CacheControl, CORS]
process_request runs in registration order; process_response in reverse, so
CORS/Cache headers are applied before the idempotency store snapshot, and the
trace log line is emitted last with full context.
"""

from __future__ import annotations

import base64
import hashlib
import math
import os
import re

import falcon

import structlog

from inflation_dashboard.adapters.redis_store import get_store
from inflation_dashboard.adapters.async_price_repository import get_db_session

logger = structlog.get_logger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class SessionMiddleware:
    """Create the per-request session: store, DB read/write split, queue."""

    def __init__(self) -> None:
        self._store = None
        self._store_ready = False

    async def _ensure_store(self):
        if not self._store_ready:
            self._store = await get_store()
            self._store_ready = True
        return self._store

    async def process_request(self, req, resp) -> None:
        store = await self._ensure_store()
        req.context.store = store
        req.context.store_backend = store.backend_name
        req.context.db = get_db_session()
        req.context.queue = store  # same adapter: XADD-based offload
        req.context.circuit = store  # circuit breaker lives on the store


class RateLimitMiddleware:
    """Token-bucket rate limiting keyed by (route, client IP)."""

    def __init__(
        self,
        capacity: float | None = None,
        refill_per_sec: float | None = None,
        exempt_paths: tuple[str, ...] = ("/api/health",),
    ) -> None:
        self.enabled = _env_bool("FALCON_RATE_LIMIT_ENABLED", True)
        self.capacity = capacity if capacity is not None else _env_float("FALCON_RATE_CAPACITY", 300.0)
        self.refill_per_sec = refill_per_sec if refill_per_sec is not None else _env_float("FALCON_RATE_REFILL_PER_SEC", 5.0)
        self.exempt_paths = exempt_paths

    async def process_request(self, req, resp) -> None:
        if not self.enabled:
            return
        if req.method in {"OPTIONS"} or req.path in self.exempt_paths:
            return
        client_ip = (req.access_route[0] if req.access_route else req.remote_addr) or "unknown"
        bucket = f"{req.path}:{client_ip}"
        store = getattr(req.context, "store", None)
        if store is None:
            return
        allowed, wait = await store.rate_limit(bucket, self.capacity, self.refill_per_sec)
        if not allowed:
            retry_after = str(max(1, math.ceil(wait)))
            raise falcon.HTTPTooManyRequests(
                title="Rate limit exceeded",
                description=f"Retry after {retry_after} seconds.",
                headers={"Retry-After": retry_after},
            )


_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Statuses that must not be replayed (a 5xx means the operation may not have
# applied; the client should retry with a fresh key).
_NON_REPLAYABLE_STATUS_PREFIX = ("5",)


class IdempotencyMiddleware:
    """Idempotency-Key enforcement for unsafe methods (principle 5).

    Flow: parse+validate the key -> replay a stored response if present ->
    acquire a distributed lock (key scope) so concurrent duplicates conflict ->
    snapshot the completed response into the store for future replays.
    """

    def __init__(self, replay_ttl_s: float | None = None) -> None:
        self.required = _env_bool("FALCON_IDEMPOTENCY_REQUIRED", True)
        self.replay_ttl_s = replay_ttl_s if replay_ttl_s is not None else _env_float("FALCON_IDEMPOTENCY_TTL_S", 86400.0)

    def _idem_hash(self, req) -> str:
        raw = f"{req.method}:{req.path}:{req.context.idem_key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def process_request(self, req, resp) -> None:
        if req.method not in _UNSAFE_METHODS:
            return
        store = getattr(req.context, "store", None)
        key = req.get_header("Idempotency-Key")
        if not key:
            if self.required:
                raise falcon.HTTPBadRequest(
                    title="Missing Idempotency-Key",
                    description="Send an Idempotency-Key header for this request method.",
                )
            return
        if not _IDEMPOTENCY_KEY_PATTERN.match(key):
            raise falcon.HTTPBadRequest(
                title="Invalid Idempotency-Key",
                description="Idempotency-Key must be 1-128 chars of [A-Za-z0-9._:-].",
            )
        req.context.idem_key = key
        idem_hash = self._idem_hash(req)
        req.context.idem_hash = idem_hash

        # 1) Replay a completed response if we have one.
        stored = await store.idem_get(idem_hash)
        if stored is not None:
            await self._replay(resp, stored)
            return

        # 2) Distributed lock: one in-flight execution per key.
        locked = await store.lock(f"idem:lock:{idem_hash}", ttl_s=float(os.environ.get("FALCON_IDEMPOTENCY_LOCK_TTL_S", "60")))
        if not locked:
            raise falcon.HTTPConflict(
                title="Idempotent request in progress",
                description="A request with the same Idempotency-Key is already being processed.",
            )

    async def _replay(self, resp, stored: dict) -> None:
        resp.status = stored.get("status", falcon.HTTP_200)
        body = stored.get("body_b64")
        if body:
            resp.data = base64.b64decode(body)
        content_type = stored.get("content_type")
        if content_type:
            resp.content_type = content_type
        resp.complete = True
        if stored.get("etag"):
            resp.etag = stored["etag"]

    async def process_response(self, req, resp, resource, req_succeeded: bool | None = None) -> None:
        if req.method not in _UNSAFE_METHODS:
            return
        idem_hash = getattr(req.context, "idem_hash", None)
        store = getattr(req.context, "store", None)
        if not idem_hash or store is None:
            return
        status_str = str(resp.status)
        if req_succeeded is False or status_str.startswith(_NON_REPLAYABLE_STATUS_PREFIX):
            return  # do not cache failed/5xx outcomes
        # Serialize the body ourselves: ASGI render_body() is a coroutine and
        # media may only be serialized lazily; data is already bytes.
        body = resp.data
        if body is None and resp.media is not None:
            try:
                import orjson

                body = orjson.dumps(resp.media)
            except Exception:
                body = None
        if body is None:
            return
        await store.idem_put(
            idem_hash,
            {
                "status": status_str,
                "body_b64": base64.b64encode(body).decode("ascii"),
                "content_type": resp.content_type if resp.content_type else falcon.MEDIA_JSON,
                "etag": getattr(resp, "etag", None) or "",
            },
            ttl_s=self.replay_ttl_s,
        )


# Per-endpoint shared-cache profiles: (max_age, stale_while_revalidate, stale_if_error).
CACHE_PROFILES: dict[str, tuple[int, int, int]] = {
    "/api/health": (0, 0, 0),
    "/api/inventory": (300, 60, 86400),
    "/api/history": (300, 60, 86400),
    "/api/retailer-averages": (300, 60, 86400),
    "/api/movers": (300, 60, 86400),
    "/api/coverage": (300, 60, 86400),
    "/api/products/search": (300, 60, 86400),
    "/api/product": (300, 60, 86400),
}
DEFAULT_CACHE_PROFILE = (300, 60, 86400)


class CacheControlMiddleware:
    """Centralized edge-cache headers (principle 6).

    Sets Cache-Control with stale-while-revalidate/stale-if-error so CDNs and
    shared caches absorb repeat traffic, plus an explicit CDN-Cache-Control
    header for intermediaries that should cache longer than browsers.
    """

    def __init__(self, profiles: dict[str, tuple[int, int, int]] | None = None) -> None:
        self.profiles = profiles or dict(CACHE_PROFILES)

    async def process_response(self, req, resp, resource, req_succeeded: bool | None = None) -> None:
        if resp.get_header("Cache-Control"):
            return
        if str(resp.status) not in {"200 OK", "304 Not Modified"}:
            return
        max_age, swr, sfe = self.profiles.get(req.path, DEFAULT_CACHE_PROFILE)
        if max_age <= 0:
            resp.cache_control = ["no-store"]
            return
        directives = [
            "public",
            f"max-age={max_age}",
        ]
        if swr > 0:
            directives.append(f"stale-while-revalidate={swr}")
        if sfe > 0:
            directives.append(f"stale-if-error={sfe}")
        resp.cache_control = directives
        resp.set_header("CDN-Cache-Control", f"public, max-age={max_age}")
        vary = resp.vary
        if vary is None:
            resp.vary = ["Accept-Encoding"]
        elif isinstance(vary, list) and "Accept-Encoding" not in vary:
            vary.append("Accept-Encoding")
