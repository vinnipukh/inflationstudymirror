#!/usr/bin/env python
"""Verify the Redis-backed store (rate limiting, locks, idempotency, queue,
and circuit-breaker degradation) against fakeredis.

Run from the repository root with:
    python scripts/verify_redis_store.py

Uses fakeredis (dev dependency) so the checks run without a Redis server.
To exercise a real server, set REDIS_URL and run the produced checks against
inflation_dashboard.adapters.redis_store.Store.connect().
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inflation_dashboard.adapters.redis_store import RedisStore, Store, MemoryStore, CircuitBreaker  # noqa: E402

PASS: list[str] = []


def _record(name: str) -> None:
    PASS.append(name)
    print(f"PASS {name}")


async def main() -> int:
    import fakeredis.aioredis
    import redis.exceptions

    fake = fakeredis.aioredis.FakeRedis()
    store = RedisStore(fake)

    # 1) key/value with TTL
    await store.set("k:1", b"hello", ttl=2)
    assert await store.get("k:1") == b"hello"
    await asyncio.sleep(2.1)
    assert await store.get("k:1") is None
    _record("redis: get/set with TTL expiry")

    # 2) token bucket via Lua
    allowed1, wait1 = await store.rate_limit("bucket:a", capacity=2.0, refill_per_sec=0.001)
    allowed2, wait2 = await store.rate_limit("bucket:a", capacity=2.0, refill_per_sec=0.001)
    allowed3, wait3 = await store.rate_limit("bucket:a", capacity=2.0, refill_per_sec=0.001)
    assert allowed1 and allowed2, (allowed1, allowed2)
    assert not allowed3 and wait3 > 0, (allowed3, wait3)
    _record("redis: token bucket allows burst then throttles (WATCH transaction)")

    # 3) distributed lock
    got = await store.lock("lock:x", ttl_s=10)
    got_again = await store.lock("lock:x", ttl_s=10)
    assert got is True and got_again is False, (got, got_again)
    await store.unlock("lock:x")
    got_after = await store.lock("lock:x", ttl_s=10)
    assert got_after is True
    await store.unlock("lock:x")
    _record("redis: distributed lock mutual exclusion + release")

    # 4) idempotency round-trip
    await store.idem_put("idem:k1", {"status": "200 OK", "body_b64": "e30="}, ttl_s=60)
    stored = await store.idem_get("idem:k1")
    assert stored == {"status": "200 OK", "body_b64": "e30="}, stored
    assert await store.idem_get("idem:missing") is None
    _record("redis: idempotency store round-trip")

    # 5) queue offload (Redis Streams)
    await store.enqueue("falcon:events", {"event": "api.response_computed", "endpoint": "/api/history"})
    entries = await fake.xrange("falcon:events")
    assert len(entries) == 1
    payload = json.loads(entries[0][1][b"payload"] if isinstance(entries[0][1][b"payload"], bytes) else entries[0][1]["payload"])
    assert payload["endpoint"] == "/api/history"
    _record("redis: queue offload -> Redis Stream entry")

    # 6) Store facade: healthy redis uses the redis backend
    facade = await Store.connect(client=fakeredis.aioredis.FakeRedis())
    assert facade.backend_name == "redis"
    await facade.set("f:k", b"v")
    assert await facade.get("f:k") == b"v"
    _record("facade: redis backend active when Redis healthy")

    # 7) Store facade: failing redis degrades to memory (circuit breaker)
    class FailingRedis:
        """Wrapper that raises a Redis connection error on every command."""

        def __init__(self, inner) -> None:
            self._inner = inner
            self.failures = 0

        async def get(self, *a, **k):
            self.failures += 1
            raise redis.exceptions.ConnectionError("boom")

        async def set(self, *a, **k):
            self.failures += 1
            raise redis.exceptions.ConnectionError("boom")

    failing = Store(RedisStore(FailingRedis(fake)), MemoryStore(), CircuitBreaker(failure_threshold=2, open_timeout=0.2))
    await failing.set("k", b"v")  # fail -> memory fallback
    assert await failing.get("k") == b"v"
    await failing.set("k2", b"v2")
    assert await failing.get("k2") == b"v2"
    _record("facade: circuit breaker degrades Redis failures to memory fallback")

    print(f"\nAll {len(PASS)} Redis store checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
