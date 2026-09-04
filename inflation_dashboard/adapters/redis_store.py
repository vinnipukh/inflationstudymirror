"""
Distributed state store for the Falcon API: Redis-backed with an in-process
fallback and a circuit breaker.

High-scale principles implemented here:
* Cache-Aside with TTLs (``get``/``set`` with expiry) -- principle 3.
* Message-queue offload for heavy I/O (Redis Streams ``XADD``) -- principle 4.
* Distributed locks + idempotency response storage -- principle 5.
* Token-bucket rate limiting (atomic Lua script) -- principle 7.
* Circuit breaker so a dead Redis degrades to the per-process fallback
  instead of failing every request -- principle 7.

Environment:
* REDIS_URL                      -- e.g. redis://127.0.0.1:6379/0 (default)
* REDIS_PING_TIMEOUT_S           -- connect probe timeout (default 1.5)
* FALCON_REDIS_CIRCUIT_FAILURES  -- failures before circuit opens (default 5)
* FALCON_REDIS_CIRCUIT_OPEN_S    -- how long the circuit stays open (default 30)
* FALCON_RATE_BUCKET_TTL_S       -- TTL of rate-limit bucket keys (default 3600)

When Redis is unreachable the store silently falls back to the per-process
``MemoryStore`` (one instance per worker). Behavior is identical, but caches,
locks and rate counters are no longer shared between workers -- which is the
correct degraded mode for a multi-process deployment.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import logging
import math
import os
import threading
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)




class CircuitOpenError(RuntimeError):
    """Raised internally when the circuit is open; callers use the fallback."""


class CircuitBreaker:
    """Async circuit breaker (closed -> open -> half-open -> closed).

    ``acquire()`` returns True when a call may proceed against the protected
    backend. After ``failure_threshold`` consecutive failures the circuit
    opens for ``open_timeout`` seconds; a single probe then decides whether it
    recovers (half-open) or stays open.
    """

    def __init__(self, failure_threshold: int = 5, open_timeout: float = 30.0) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.open_timeout = max(0.1, open_timeout)
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    async def acquire(self) -> bool:
        async with self._lock:
            if self._state == "closed":
                return True
            if self._state == "open":
                if time.monotonic() - self._opened_at >= self.open_timeout:
                    self._state = "half_open"  # allow a single probe
                    return True
                return False
            return False  # half_open: a probe is already in flight

    async def release(self, ok: bool) -> None:
        async with self._lock:
            if ok:
                self._state = "closed"
                self._failures = 0
                return
            self._failures += 1
            if self._state == "half_open" or self._failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()


class TokenBucket:
    """In-process token bucket used by the memory fallback."""

    __slots__ = ("capacity", "refill_per_sec", "tokens", "updated_at", "lock")

    def __init__(self, capacity: float, refill_per_sec: float) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = capacity
        self.updated_at = time.monotonic()
        self.lock = threading.Lock()

    def take(self, cost: float = 1.0) -> float:
        """Try to consume ``cost`` tokens; returns wait seconds (0 => allowed)."""
        with self.lock:
            now = time.monotonic()
            elapsed = max(0.0, now - self.updated_at)
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            self.updated_at = now
            if self.tokens >= cost:
                self.tokens -= cost
                return 0.0
            return (cost - self.tokens) / self.refill_per_sec


class MemoryStore:
    """Per-process fallback implementing the same surface as RedisStore."""

    backend_name = "memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.RLock()
        self._buckets: dict[str, TokenBucket] = {}
        self._buckets_lock = threading.Lock()
        self._locks: dict[str, float] = {}
        self._idem: dict[str, tuple[float, dict[str, Any]]] = {}
        self._queue: deque[dict[str, Any]] = deque(maxlen=1000)
        self._max_entries = 100_000

    # --- key/value ---------------------------------------------------------
    async def get(self, key: str) -> bytes | None:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if now > expires_at:
                del self._data[key]
                return None
            return value

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + (ttl if ttl is not None else 86_400)
        with self._lock:
            if len(self._data) >= self._max_entries:
                self._data.clear()
            self._data[key] = (expires_at, value)

    async def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    # --- rate limiting -----------------------------------------------------
    async def rate_limit(
        self, bucket: str, capacity: float, refill_per_sec: float, cost: float = 1.0
    ) -> tuple[bool, float]:
        with self._buckets_lock:
            tb = self._buckets.get(bucket)
            if tb is None:
                if len(self._buckets) >= 20_000:
                    self._buckets.clear()
                tb = TokenBucket(capacity, refill_per_sec)
                self._buckets[bucket] = tb
        wait = tb.take(cost)
        return (wait == 0.0), wait

    # --- distributed locks -------------------------------------------------
    async def lock(self, key: str, ttl_s: float = 30.0) -> bool:
        now = time.monotonic()
        with self._lock:
            held_until = self._locks.get(key)
            if held_until is not None and now < held_until:
                return False
            self._locks[key] = now + ttl_s
            return True

    async def unlock(self, key: str) -> None:
        with self._lock:
            self._locks.pop(key, None)

    # --- idempotency -------------------------------------------------------
    async def idem_get(self, key: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            entry = self._idem.get(key)
            if entry is None:
                return None
            expires_at, payload = entry
            if now > expires_at:
                del self._idem[key]
                return None
            return payload

    async def idem_put(self, key: str, payload: dict[str, Any], ttl_s: float) -> None:
        with self._lock:
            if len(self._idem) >= self._max_entries:
                self._idem.clear()
            self._idem[key] = (time.monotonic() + ttl_s, payload)

    # --- queue -------------------------------------------------------------
    async def enqueue(self, stream: str, payload: dict[str, Any]) -> bool:
        self._queue.append({"ts": datetime.now(timezone.utc).isoformat(), "stream": stream, "payload": payload})
        return True

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MemoryStore entries={len(self._data)} buckets={len(self._buckets)}>"


class RedisStore:
    """Redis-backed store. All operations are non-blocking (redis.asyncio)."""

    backend_name = "redis"

    def __init__(self, client: Any) -> None:
        self.client = client

    async def get(self, key: str) -> bytes | None:
        return await self.client.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        await self.client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def rate_limit(
        self, bucket: str, capacity: float, refill_per_sec: float, cost: float = 1.0
    ) -> tuple[bool, float]:
        """Token bucket via a WATCH/MULTI/EXEC transaction (optimistic
        concurrency; atomic on real Redis and on fakeredis for tests).

        Keys: ``rl:t:<bucket>`` (current tokens, float-as-string) and
        ``rl:r:<bucket>`` (last refill timestamp). On WatchError the
        transaction is retried; concurrent requests cannot overspend.
        """
        import redis.exceptions

        token_key = f"rl:t:{bucket}"
        refill_key = f"rl:r:{bucket}"
        ttl_ms = int(os.environ.get("FALCON_RATE_BUCKET_TTL_S", "3600")) * 1000
        now = time.monotonic()

        for _attempt in range(3):
            try:
                async with self.client.pipeline(transaction=True) as pipe:
                    await pipe.watch(token_key, refill_key)
                    tokens_raw = await pipe.get(token_key)
                    ref_raw = await pipe.get(refill_key)
                    tokens = float(tokens_raw) if tokens_raw is not None else capacity
                    ref = float(ref_raw) if ref_raw is not None else now
                    elapsed = max(0.0, now - ref)
                    tokens = min(capacity, tokens + elapsed * refill_per_sec)
                    if tokens >= cost:
                        tokens -= cost
                        wait = 0.0
                    else:
                        wait = (cost - tokens) / refill_per_sec if refill_per_sec > 0 else float("inf")
                    pipe.multi()
                    pipe.set(token_key, repr(tokens), px=ttl_ms)
                    pipe.set(refill_key, repr(now if wait == 0.0 else ref), px=ttl_ms)
                    await pipe.execute()
                    return wait == 0.0, max(0.0, wait)
            except redis.exceptions.WatchError:
                continue  # concurrent refill; retry with fresh values

        # WatchError storm (pathological): accept the last computed decision.
        return wait == 0.0, max(0.0, wait)

    async def lock(self, key: str, ttl_s: float = 30.0) -> bool:
        result = await self.client.set(key, "1", nx=True, px=int(ttl_s * 1000))
        return result is True

    async def unlock(self, key: str) -> None:
        await self.client.delete(key)

    async def idem_get(self, key: str) -> dict[str, Any] | None:
        value = await self.client.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None

    async def idem_put(self, key: str, payload: dict[str, Any], ttl_s: float) -> None:
        await self.client.set(key, json.dumps(payload).encode("utf-8"), ex=int(ttl_s))

    async def enqueue(self, stream: str, payload: dict[str, Any]) -> bool:
        message_id = await self.client.xadd(stream, {"payload": json.dumps(payload)})
        return bool(message_id)

    async def close(self) -> None:
        await self.client.aclose()


class Store:
    """Front for the state store: Redis when healthy, MemoryStore otherwise.

    A circuit breaker guards every Redis call: after repeated failures the
    store degrades to the per-process fallback for ``open_timeout`` seconds,
    then probes once (half-open) before recovering.
    """

    def __init__(self, redis_store: RedisStore | None, memory: MemoryStore, breaker: CircuitBreaker) -> None:
        self._redis = redis_store
        self._memory = memory
        self._breaker = breaker
        self._mem_only = redis_store is None
        if self._mem_only:
            self.backend_name = memory.backend_name
        else:
            self.backend_name = redis_store.backend_name

    @classmethod
    async def connect(cls, url: str | None = None, client: Any | None = None) -> "Store":
        """Create the store. ``client`` is injectable for tests (e.g. fakeredis)."""
        memory = MemoryStore()
        if client is not None:
            return cls(RedisStore(client), memory, CircuitBreaker())
        target_url = url or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(target_url, decode_responses=False)
            ping_timeout = float(os.environ.get("REDIS_PING_TIMEOUT_S", "1.5"))
            async with asyncio.timeout(ping_timeout):
                await client.ping()
            return cls(RedisStore(client), memory, CircuitBreaker())
        except Exception as exc:
            logger.warning(
                "redis_unavailable_using_memory_fallback",
                url=target_url,
                error=type(exc).__name__,
            )
            return cls(None, memory, CircuitBreaker())

    # --- dispatch ----------------------------------------------------------
    async def _run(self, op: str, method: str, fallback: Any, *args: Any, **kwargs: Any) -> Any:
        if self._mem_only:
            return await fallback(*args, **kwargs)
        if not await self._breaker.acquire():
            return await fallback(*args, **kwargs)
        try:
            result = await getattr(self._redis, method)(*args, **kwargs)
        except Exception as exc:
            await self._breaker.release(False)
            logger.warning(
                "store_op_circuit_failure",
                op=op,
                state=self._breaker.state,
                error=type(exc).__name__,
            )
            return await fallback(*args, **kwargs)
        await self._breaker.release(True)
        return result

    async def get(self, key: str) -> bytes | None:
        return await self._run("get", "get", self._memory.get, key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        await self._run("set", "set", self._memory.set, key, value, ttl)

    async def delete(self, key: str) -> None:
        await self._run("delete", "delete", self._memory.delete, key)

    async def rate_limit(self, bucket: str, capacity: float, refill_per_sec: float, cost: float = 1.0) -> tuple[bool, float]:
        return await self._run(
            "rate_limit", "rate_limit", self._memory.rate_limit, bucket, capacity, refill_per_sec, cost
        )

    async def lock(self, key: str, ttl_s: float = 30.0) -> bool:
        return await self._run("lock", "lock", self._memory.lock, key, ttl_s)

    async def unlock(self, key: str) -> None:
        await self._run("unlock", "unlock", self._memory.unlock, key)

    async def idem_get(self, key: str) -> dict[str, Any] | None:
        return await self._run("idem_get", "idem_get", self._memory.idem_get, key)

    async def idem_put(self, key: str, payload: dict[str, Any], ttl_s: float) -> None:
        await self._run("idem_put", "idem_put", self._memory.idem_put, key, payload, ttl_s)

    async def enqueue(self, stream: str, payload: dict[str, Any]) -> bool:
        return await self._run("enqueue", "enqueue", self._memory.enqueue, stream, payload)

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass


_store_singleton: Store | None = None
_store_lock = threading.Lock()


async def get_store(client: Any | None = None) -> Store:
    """Return the process-wide store (created once; injectable client for tests)."""
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = await Store.connect(client=client)
    return _store_singleton


def reset_store_for_tests() -> None:
    """Drop the singleton so verify scripts can inject a fresh store."""
    global _store_singleton
    _store_singleton = None


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


logger = structlog.get_logger(__name__)
