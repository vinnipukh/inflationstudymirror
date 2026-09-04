# ASGI Scaling Refactor (Falcon.asgi for 100k+ users)

Status: **implemented and verified** (2026-09-03). The high-scale ASGI entry
point is additive: the WSGI path (`inflation_dashboard/api/falcon_app.py` +
`resources.py`) is untouched and still verified by
`scripts/verify_falcon_api.py`.

## How to run

```bash
# ASGI: falcon.asgi.App + Redis-backed middleware stack
python scripts/run_falcon_server.py --interface asgi --engine uvicorn --workers 4 --threads 8
python scripts/run_falcon_server.py --interface asgi --engine granian --workers 4 --blocking-threads 8

# WSGI (unchanged, legacy path)
python scripts/run_falcon_server.py                      # granian wsgi
```

Entry point: `inflation_dashboard.api.asgi_app.create_asgi_app()`.

## The 10 principles -> where they live

| # | Principle | Implementation |
|---|-----------|----------------|
| 1 | Strict statelessness | Resources and middleware never mutate `self` per request; all request state goes to `req.context` (`trace_id`, `store`, `db`, `queue`, `idem_hash`). `resources_asgi.py`, `middleware.py`. |
| 2 | Read/write DB split at session layer | `async_price_repository.get_db_session()` exposes `{read, write}` engines; `SessionMiddleware` binds it to `req.context.db`. Reads use a read-only SQLite URI (`mode=ro`); writes are opt-in via `FALCON_DB_WRITE_URL` (Postgres-ready, currently None for the read dashboard). |
| 3 | Cache-Aside with TTLs | Two layers: L1 in-process byte cache (`api/filters.py`, existing) + L2 shared Redis (`api/cache_aside.py`, versioned keys). Writes happen on compute and cache miss only; TTLs per endpoint (`CACHE_PROFILES` in `api/middleware.py`). Bump `FALCON_DATA_VERSION` after ingest to invalidate. |
| 4 | Offload heavy I/O to message queues | `Store.enqueue()` -> Redis Streams `XADD` (`redis_store.py`); `resources_asgi._offload_computed` publishes `api.response_computed` events for expensive endpoints. A consumer process can prewarm CDNs or refresh derived data. Degrades to a bounded in-process deque without Redis. |
| 5 | Idempotency via headers + distributed locks | `IdempotencyMiddleware`: `Idempotency-Key` on POST/PUT/PATCH/DELETE, distributed lock (`SET NX PX`, key-scoped), stored-response replay with `resp.complete` short-circuit, 409 on concurrent duplicates, 5xx never replayed. |
| 6 | Correct HTTP Cache-Control for edge caching | `CacheControlMiddleware` sets `Cache-Control: public, max-age=…, stale-while-revalidate=60, stale-if-error=86400` plus `CDN-Cache-Control` and `Vary: Accept-Encoding` per endpoint (health = `no-store`). |
| 7 | Token bucket rate limiting + circuit breakers | `RateLimitMiddleware` (per route+IP, 429 + `Retry-After`) uses a `WATCH`/`MULTI`/`EXEC` token bucket in Redis (`redis_store.py`); `CircuitBreaker` degrades Redis to a per-process fallback after repeated failures, with half-open recovery. In-process `TokenBucket` mirrors the same semantics. |
| 8 | Cursor-based (keyset) pagination | `api/pagination.py` (opaque base64url cursors, versioned); `ProductSearchResource` paginates over `(observations_count DESC, product_id ASC)` with `next_cursor` in `meta.pagination` and a 400 `invalid_cursor` on malformed input. |
| 9 | Structured JSON logs + correlation IDs | `api/observability.py`: structlog (+orjson) JSON lines; `TraceIDMiddleware` accepts/echoes `X-Request-ID`/`X-Correlation-ID`, binds contextvars, emits one `request_processed` line with status/duration/cache_hit/trace_id per request. |
| 10 | Async non-blocking I/O | `falcon.asgi.App` under uvicorn/granian ASGI. DB reads are awaited through the SQLAlchemy async engine (aiosqlite); CPU-bound pandas/JSON work and gzip run in `asyncio.to_thread` so the event loop never blocks. |

## Configuration (env vars)

| Variable | Default | Meaning |
|----------|---------|---------|
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis backend for cache L2 / rate limits / locks / queue |
| `FALCON_INTERFACE` | `wsgi` | Launcher app interface (`asgi` or `wsgi`) |
| `FALCON_DATA_VERSION` | `1` | Cache namespace version; bump on ingest to invalidate |
| `FALCON_RATE_LIMIT_ENABLED` | `1` | Master switch for rate limiting |
| `FALCON_RATE_CAPACITY` / `FALCON_RATE_REFILL_PER_SEC` | `300` / `5.0` | Token bucket burst + refill |
| `FALCON_IDEMPOTENCY_REQUIRED` | `1` | 400 when unsafe requests omit `Idempotency-Key` |
| `FALCON_IDEMPOTENCY_TTL_S` / `FALCON_IDEMPOTENCY_LOCK_TTL_S` | `86400` / `60` | Replay storage + lock TTLs |
| `FALCON_REDIS_CIRCUIT_FAILURES` / `FALCON_REDIS_CIRCUIT_OPEN_S` | `5` / `30` | Circuit breaker thresholds |
| `FALCON_DB_READ_URL` / `FALCON_DB_WRITE_URL` | sqlite `mode=ro` URI / unset | Async engine URLs (write = Postgres-ready) |
| `FALCON_OFFLOAD_ENABLED` | `1` | Publish `api.response_computed` queue events |
| `FALCON_CORS_ORIGINS` | `*` | CORS origins (same as WSGI) |

## Degraded modes (no Redis)

Without Redis the store falls back to a per-process `MemoryStore`:
rate limits, locks, idempotency and the L2 cache become worker-local (correct,
just no longer shared). A circuit breaker avoids error storms around a dying
Redis. All verify scripts exercise this path; the Redis path is verified with
`fakeredis` (`scripts/verify_redis_store.py`).

## Verification

```bash
python scripts/verify_falcon_api.py   # WSGI regression + import boundaries (still green)
python scripts/verify_asgi_api.py     # 12 ASGI checks: middleware in-process + live uvicorn
python scripts/verify_redis_store.py  # 7 Redis-store checks (fakeredis)
```

Known sizing note: the unfiltered `/api/history` payload is ~105 MB
(3 retailers x 45 snapshot files). It is served from the pre-serialized byte
cache with ETag/304 and gzip; large-history warnings are unchanged from the
WSGI behavior.

## Migration notes

* WSGI routes, response contracts and the frontend contract are unchanged
  (`docs/FALCON_API_CONTRACT.md`).
* `/api/products/search` gains `?cursor=` and `meta.pagination` (additive).
* All unsafe-method endpoints (none exist today) require an
  `Idempotency-Key` header when the middleware is in default mode.
* The next bottleneck step after this refactor is ingest-time precompute of
  the pandas aggregates (move the math out of request handlers entirely);
  the async repository and queue hooks are structured to support that.
