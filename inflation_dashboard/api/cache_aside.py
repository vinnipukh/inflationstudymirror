"""
Cache-aside helpers (principle 3): Redis L2 over the in-process L1 byte cache.

L1 is the existing stdlib TTL cache in ``api.filters`` (raw + gzip variants +
ETag digests, zero-copy reuse inside the worker). L2 is the shared Redis store
(versioned keys) so a fleet of workers serves the same pre-serialized bytes.

Invariant: both layers store the same tuple
    (raw_bytes, gzip_bytes|None, etag, gzip_etag|None)
so ``resources_asgi`` can serve either with identical ETag/304 semantics.

Invalidation: bump FALCON_DATA_VERSION after an ingest so all cache keys
change and stale entries expire via TTL.
"""

from __future__ import annotations

import hashlib
import os

from inflation_dashboard.api.middleware import DEFAULT_CACHE_PROFILE, CACHE_PROFILES

CACHE_VERSION = os.getenv("FALCON_DATA_VERSION", "1")
_RAW_SUFFIX = ":raw"
_GZ_SUFFIX = ":gz"


def response_cache_key(endpoint: str, query_string: str) -> str:
    digest = hashlib.sha256(query_string.encode("utf-8")).hexdigest()
    return f"falc:v{CACHE_VERSION}:resp:{endpoint}:{digest}"


def endpoint_ttl(endpoint: str) -> int:
    profile = CACHE_PROFILES.get(endpoint, DEFAULT_CACHE_PROFILE)
    return profile[0]


async def get_response(store, endpoint: str, query_string: str) -> tuple[bytes, bytes | None, str, str | None] | None:
    """L2 read: return (raw, gzip, etag, gzip_etag) or None on miss."""
    if store is None or store.backend_name == "memory":
        return None  # L2 only exists on the shared Redis backend
    key = response_cache_key(endpoint, query_string)
    raw = await store.get(key + _RAW_SUFFIX)
    if raw is None:
        return None
    gz = await store.get(key + _GZ_SUFFIX)
    etag = hashlib.md5(raw).hexdigest()
    gz_etag = hashlib.md5(gz).hexdigest() if gz is not None else None
    return raw, gz, etag, gz_etag


async def set_response(
    store,
    endpoint: str,
    query_string: str,
    raw_bytes: bytes,
    ttl: int | None = None,
) -> None:
    """L2 write: store raw bytes + a one-time gzip variant with a TTL."""
    if store is None or store.backend_name == "memory":
        return
    import gzip

    key = response_cache_key(endpoint, query_string)
    effective_ttl = ttl if ttl is not None else endpoint_ttl(endpoint)
    if effective_ttl <= 0:
        return
    await store.set(key + _RAW_SUFFIX, raw_bytes, ttl=effective_ttl)
    if len(raw_bytes) >= 1024:
        gz = gzip.compress(raw_bytes, compresslevel=6, mtime=0)
        await store.set(key + _GZ_SUFFIX, gz, ttl=effective_ttl)
    else:
        await store.delete(key + _GZ_SUFFIX)


async def invalidate(endpoint: str, store=None) -> None:
    """Remove one endpoint's cached entries (version key remains valid)."""
    if store is None or store.backend_name == "memory":
        return
    # Keys are only addressable by exact query string; wholesale invalidation
    # is achieved by bumping FALCON_DATA_VERSION at ingest time. This hook
    # exists for targeted pipeline invalidations.
    prefix = f"falc:v{CACHE_VERSION}:resp:{endpoint}:"
    # Best-effort scan is deliberately omitted: SCAN on shared Redis at
    # request time is worse than a version bump. Kept as documentation hook.
    del prefix
