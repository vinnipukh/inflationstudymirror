# Falcon API Backend Optimization: Investigation & Synthesis Report

**Date:** 2026-09-03
**Scope:** How to optimize the Falcon API backend of `inflationstudymirror` (Falcon 4.3.1 WSGI, Python 3.14.7 GIL build, orjson media handlers, in-process TTL caches, read-only WAL SQLite, Granian/Gunicorn/Waitress launcher).
**Method:** Four parallel deep-research agents (framework internals, deployment/server, benchmarks/case studies, profiling/DB/caching). Claims were cross-checked between agents, verified against the installed Falcon 4.3.1 source in the repo venv, and grounded in local measurements on the real `prices.db` (2.68 GB, 4.09M rows) and the real app. Detailed evidence with full citations lives in four notes files in this repo:

| Notes file | Coverage |
|---|---|
| `docs/research-notes-falcon-framework-optimization.md` | Framework internals, ETag/304, middleware, routing, media, WSGI vs ASGI |
| `docs/FALCON-DEPLOYMENT-TUNING-RESEARCH.md` | Server selection, worker/thread sizing, launch bugs, OS/proxy tuning |
| `docs/research/falcon-benchmarks-case-studies.md` | TechEmpower data, independent benchmarks, production users, scaling pitfalls |
| `docs/research-notes-profiling-db-caching-falcon.md` | Measured hot paths, SQLite tuning, serialization, caching, precompute strategy |

---

## Executive Summary

1. **The hot path is the first SQLite load per filter signature (2.4–15 s), not pandas, orjson, or Falcon itself.** Framework overhead measures ~63 µs/request; pandas groupbys 54–83 ms; orjson 0.1 s; serialization 0.72 s/310k rows. The 2.4–15 s `cur.execute`+`fetchall` cost is masked by 300 s TTL caches that duplicate per worker. [prof-db §1]
2. **Biggest untapped, zero-risk win is the HTTP layer: ETag + If-None-Match 304s, `Cache-Control`, and gzip.** The API emits no cache headers and no compression today; a 77 MB history payload gzips to ~2 MB (2.4%). Repeat GETs (the dashboard fires ~5 identical requests per rerun) would stop hitting the origin entirely. [core §4, prof-db §4]
3. **Server choice dwarfs framework choice (8–60×).** Granian WSGI is the right engine and is already the launcher default: ~125k req/s single-worker in official benches vs ~9k gunicorn-gthread (10 KB static tests); loopback test on this repo's real app: Granian 5.1k rps vs gthread 3.5k, Waitress 3.5k, gunicorn-sync 2.1k (client-capped, comparative). [deploy §1]
4. **Two launcher engines are broken today (verified live):** the `waitress` engine 500s (passes a factory name), and the `uvicorn` engine 500s (missing `--interface wsgi`). Granian and gunicorn-gthread are correct. Additionally, `pyproject.toml`/`uv.lock` only declare `waitress` — Granian/Gunicorn aren't even installable deps. [deploy §3, bench §4]
5. **SQLite config is ~90% right (WAL, busy_timeout 5000, mode=ro, query_only).** Real gaps: a fresh connection per call (~20 ms + `-shm` churn → rare `SQLITE_BUSY` even with zero writers), a tuning-constant mismatch (adapter 1 GB mmap / −128000 cache vs launcher env 256 MB / −64000), and per-worker cache memory risk. Do **not** wire in the unused SQL-pushdown functions — they measured 3.0–18.1 s vs ~2.5 s for the pandas path. [prof-db §2, bench §4–5]
6. **Stay on WSGI.** Async (Falcon-ASGI) only wins ~4–5× for concurrent *blocking I/O*; this workload is CPU/DB-bound and already byte-cached, so processes (`--workers`) are the scaling lever. Migrating would add event-loop/threadpool complexity for no gain. [core §5, bench §2]

---

## Core Findings

### 1. Where time actually goes (measured on this repo)

- `/api/history` default filters (3 retailers × 45 newest files): connect 18 ms, `cur.execute` **2.43 s**, `fetchall` 0.65 s, DataFrame 0.38 s → **3.74 s / 425k rows**; 1-month window 2.44 s; `all_history=true` **14.96 s / 1.67M rows**. ~65% of load time is SQL execution. [prof-db §1]
- `/api/products/search` is 20 ms warm; the 687 ms cold call is OS page-cache warm-up, not the query → fixed by boot-time warmup. [prof-db §1]
- Framework overhead per request: bare GET 63 µs; +CORSMiddleware 66 µs (+5%); routing 0.35 µs; query-string parse 0.25 µs. All noise at this API's scale. [core §1]
- Serialization: `records_from_frame` 0.72 s / 310k rows vs pandas `to_dict('records')` 1.71 s; `orjson.dumps` of the 77 MB envelope 0.10 s. Already near-optimal for the current record format. [prof-db §3]

### 2. HTTP layer: the biggest untapped win

- **Zero cache headers today** (no `Cache-Control`, `ETag`, `Last-Modified` anywhere; verified by grep). [prof-db §4]
- Falcon provides native primitives: `req.if_none_match` (lazy ~0.3 µs when absent), `resp.etag` (auto-quotes), `resp.cache_control`, and **automatic body/Content-Type stripping for 304s** — a 304 responder only sets status. [core §4]
- The TTL cache already holds `raw_bytes`; an ETag can be derived once at cache-put (`md5(raw_bytes).hexdigest()`), making 304s ~15 lines of code. Identical bytes → identical ETag across workers, so multi-worker correctness holds. Estimated dashboard behavior: repeated identical GETs return 304 with empty body. [core §4, prof-db §4]
- **No gzip anywhere** (Falcon core has none; Granian 2.8.2 has none; gunicorn none; community WSGI options don't exist — ASGI-only packages). Measured: 27.5 MB → 0.7 MB gzip (2.4%) in 0.12 s; a 77 MB envelope → ~2 MB. Compress **cached** bytes once per TTL entry (deterministic), set `Vary: Accept-Encoding`, or terminate at nginx/Caddy. [core §4, prof-db §4]

### 3. Server & deployment

**Server ranking (multiple sources, mutually consistent):** Granian WSGI ≫ gunicorn-gthread ≈ Waitress > gunicorn-sync for this app; uWSGI is Falcon-docs-recommended but slow on I/O sims and unverified on Python 3.14; Uvicorn is only relevant for an ASGI port.

| Source | Granian | gunicorn gthread | Waitress | gunicorn sync |
|---|---|---|---|---|
| Granian official bench (10 KB static) | ~125.8k rps | 9.2k | — | — |
| TFB R23 (gunicorn+Meinheld / stock waitress) | — | 715–903k | 1.1–1.4k | — |
| Local loopback on this repo (client-capped) | 5.1k | 3.5k | 3.5k | 2.1k |

[deploy §1, bench §1.1, core §5] — treat absolute numbers per-machine; direction is consistent: **server ≫ framework overhead**.

- **Worker/thread sizing:** CPU-bound pandas + GIL (verified `sys._is_gil_enabled()=True`) ⇒ scale **processes**. Recommend `--workers 8` (16-core box) and `--blocking-threads 4–8`; 16 threads/worker × 8 workers = 128 threads is wasteful. [deploy §2]
- **Granian trap (verified in source):** if `--blocking-threads` is omitted, Granian WSGI defaults to `max(1, backpressure//2)` — with backlog 1024–2048 that's **512–1024 Python threads/worker**. Always pass it explicitly (the launcher does, but document it). [deploy §2]
- **Launcher bugs (verified live):** waitress engine (`waitress ...:create_app`) → `TypeError: create_app() takes 0 positional arguments but 2 were given` (factory name passed where a WSGI app is expected); uvicorn engine lacks `--interface wsgi` → WSGI app run as ASGI → 500 (fix verified; note native uvicorn WSGI is deprecated → a2wsgi). [deploy §3]
- **Dependency gap:** `pyproject.toml`/`uv.lock` declare only `waitress`; `granian`, `gunicorn` are referenced by the launcher but missing from deps. [bench §4]
- **Topology:** nginx/Caddy in front (TLS, serve the built SvelteKit SPA as static files, proxy `/api` with `proxy_http_version 1.1; proxy_set_header Connection "";` and `upstream keepalive 32`); systemd `LimitNOFILE=65535`; `net.core.somaxconn ≥ 2048`, `tcp_tw_reuse=1`, widened `ip_local_port_range`. HTTP/2 is a non-goal for this JSON API (only matters if serving the SPA same-origin). [deploy §3–4]
- **Lifecycle:** gunicorn `max_requests 10k–50k + jitter` or Granian `--workers-lifetime 1h` / `--workers-max-rss 4–6 GiB`; `--graceful-timeout ≥ 60–120 s` so long aggregations finish during restarts. [deploy §2]

### 4. Data layer (SQLite)

**Already correct (verified):** WAL persistent, `busy_timeout=5000`, `synchronous=NORMAL`, URI `mode=ro`, `query_only=1`, `temp_store=MEMORY`, per-connection page cache 64–128 MB, mmap enabled. Matches documented best practice for read-mostly APIs (SQLite docs: many readers + one writer; appropriate for local read-heavy data). [prof-db §2, bench §5]

**Gaps (prioritized):**
1. **Per-thread connection reuse.** `get_db_connection()` opens and every helper closes per call (~20 ms + PRAGMA setup per request). Thread-local reuse removes the cost and the `-shm` open/close lock windows behind rare `SQLITE_BUSY` for short-lived WAL readers (Hynek 2026 repro; busy_timeout suppresses it, long-lived connections eliminate it). The launcher already contains a working `get_readonly_sqlite_connection(check_same_thread=False)` — the app never calls it. [prof-db §2, bench §5]
2. **Tuning constants mismatch.** Adapter hardcodes `mmap_size=1 GB`, `cache_size=-128000`; launcher env advertises 256 MB / −64000 and is ignored by the repository. DB is 2.68 GB, so even 1 GB maps only part of the file; raise to ~file size on 64-bit (a *maximum*, SQLite demotes safely) or document the hot-prefix rationale. One config source. [prof-db §2, bench §5]
3. **WAL read-only edges.** After a writer's last close, SQLite deletes `-shm`/`-wal`; a read-only opener then needs *directory* write permission (or pre-existing shm files, or `immutable=1` for a truly static file). Keep the DB dir writable; don't copy the DB to a read-only FS without the sidecar files. [bench §5]
4. **Don't enable the unused SQL-pushdown functions** (`load_movers_from_db`, `load_retailer_averages_from_db`, `load_coverage_from_db`): measured 3.0–18.1 s vs ~2.5 s for the pandas path because they scan all dates in range and miss the "45 newest file-dates per retailer" semantics. Precompute artifacts instead. [prof-db §5]

### 5. Framework layer (already near-optimal; small cleanups)

- `resp.data = raw_bytes` already bypasses media serialization (`render_body()` precedence: text → data → media). The `resp.media = envelope_dict` assignments on cached/data paths are dead state (~40 ns, but they retain a full 77 MB dict beside the bytes in `_response_cache`, doubling memory) — remove on data paths, keep only in the `except` fallback. [core §3, prof-db §4]
- Routing: keep `CompiledRouter`; optionally `compile=True` on the *last* `add_route` (first-request compile is 0.36 ms at 8 routes — cosmetic, deterministic). No custom router needed. [core §2]
- `_response_cache` has **no byte cap** (only 512 entries) while single entries can reach ~77 MB+/300 MB — cap by total bytes or store bytes only. [prof-db §4]
- CORS middleware costs +3 µs (+5%) and is fine as-is; it can be dropped only if the API and SPA become same-origin behind one proxy. [core §1]
- Keep-orjson confirmed: 2.8–8.7× stdlib; msgspec's ~25–64% edge requires a struct/column-major contract change — not worth it now. [prof-db §3, bench §2]

### 6. Benchmarks & case studies (context)

- TFB R23 (2025, 2× Xeon Gold 6330/40GbE): Falcon json **714,694 req/s**, falcon-orjson **903,324** (+26%), falcon-asgi 491k, **stock Waitress 1,448**. DB tests collapse to 27–112k (Postgres is the bottleneck — framework overhead is a rounding error on real work). Falcon's TFB entry is gunicorn+Meinheld with `workers=cpu×1.5` — TFB numbers measure that server config, not bare Falcon. [bench §1.1]
- Independent same-server benchmarks: Falcon ≈1.6× FastAPI, ≈11× Django (klen 2021); Falcon+Granian 120k vs gunicorn-sync ~12× less (rahm 2026); I/O-bound: Falcon-threaded 16.5k vs Falcon-async 68k (**only place async wins**). [bench §1.2]
- Production users verified in code: LinkedIn Iris (pin `falcon==1.4.1`), GNU Mailman 3 REST API. Open edX / Mailchimp / Rejected.us: no evidence. [bench §3]
- Methodology hygiene: exclude content-farm "benchmarks" (johal.in — AI-generated, fabricated 2.5M req/s); TFB R21→R22 deltas partly reflect CPU throttling after machine move (TFB #8397); treat cross-round/cross-machine absolute numbers as non-comparable. [bench §1.3, core gaps]
- Free-threaded CPython 3.14: Falcon 4.2+ ships 3.14t wheels and maintainers report near-linear thread scaling with Gunicorn — but pandas/numpy/orjson free-threading is version-sensitive; revisit only with a project-wide decision. [bench §2.4, core §5]

---

## Prioritized Action Plan

### P0 — HTTP layer (days; zero risk; biggest measured win)
1. **ETag + If-None-Match 304 + Cache-Control** in `inflation_dashboard/api/filters.py` + `resources.py`: store `etag = '"' + hashlib.md5(raw_bytes).hexdigest() + '"'` in the `_response_cache` entry at `put_cached_response`; on `get_cached_response` hit, if `req.if_none_match` matches (or `'*'`) → `resp.status = falcon.HTTP_304; resp.etag = etag` and return (Falcon strips body/Content-Type automatically); else set `resp.etag` and `resp.cache_control = ["private", "max-age=300"]` (align to `RESPONSE_CACHE_TTL_SECONDS = 300`). Verify with `curl -H "If-None-Match: <etag>" -i`.
2. **gzip for large cached payloads**: middleware (or nginx) that, on `Accept-Encoding: gzip` and `len(raw) > 1024`, serves a gzip variant cached once per TTL entry (deterministic); set `Content-Encoding: gzip` + `Vary: Accept-Encoding`; skip `/api/health`. Best done at nginx if/when a proxy exists.

### P1 — Data & server plumbing (week)
3. **Per-thread reusable read-only SQLite connections** in `sqlite_price_repository.get_db_connection` (threading.local, lazy create, close on worker shutdown) — reuse the strategy already prototyped in `scripts/benchmark_db_queries.py` and exposed by the launcher. Removes ~20 ms/request + WAL `-shm` churn.
4. **Reconcile SQLite tuning constants**: one module constant for `mmap_size` (raise to ~2.8 GB or min(file_size, 2.8 GB)), `cache_size` (−128000), `busy_timeout` (5000); delete the ignored `SQLITE_MMAP_SIZE`/`SQLITE_CACHE_SIZE` env path in the launcher.
5. **Declare real server deps**: add `granian` + `gunicorn` to `pyproject.toml`/`uv.lock`; keep `waitress` only as dev fallback. Fix or remove the waitress engine (pass module with `app = create_app()`, or drop it) and fix the uvicorn engine (`--interface wsgi`) or remove — granian + gunicorn-gthread are the supported paths.

### P2 — Cold loads, memory safety, observability (week+)
6. **Precompute per snapshot**: `scripts/precompute_artifacts.py` builds pickle artifacts (zero new deps; parquet needs pyarrow) of the default/all-history filtered frames + retailer averages + movers + coverage after `prices.db` rebuilds; resources load them once per worker. Removes the 2.4–15 s first-load per filter. **Do not** route through the unused SQL aggregate functions (measured slower).
7. **Boot-time warmup**: one query per hot path at worker start (or `preload`/fork-COW if supported) to kill first-request spikes.
8. **Cap `_response_cache` memory**: store bytes only on hit path (drop the duplicated `envelope_dict`), add a total-byte cap.
9. **TimingMiddleware** (perf_counter in `process_request` → `req.context`, log delta + route + cache_hit in `process_response`) — plain logs, no deps; plus `py-spy`/`snakeviz` for one-shot profiles and a wrk/oha smoke script across {granian, gthread, waitress} × endpoints, modeled on rahm's methodology.

### P3 — Response shape (only with frontend coordination)
10. **Pagination/limits/column pruning** for `/api/history` (cursor or date-bucket + `limit`; `source_file` is ~half the row string bytes — make optional; trim the default 45-file window).
11. **CSV/parquet format variant** via `MEDIA_CSV`/`MEDIA_PARQUET` + `client_prefers` if the SPA wants smaller transfers; **column-major envelope** (`{"columns","data"}`) only as a coordinated contract change (exploits orjson's native numpy path, ~10× serialization with lower RSS).
12. **Do not** go ASGI or free-threaded CPython for this workload now; revisit only for SSE/websockets or after a stack-wide 3.14t decision.

---

## Trade-offs & Critical Evaluation

- **gzip CPU vs bandwidth**: compressing a 77 MB payload costs ~0.3 s CPU per miss — cache compressed bytes; at nginx this is amortized and standard. Brotli squeezes more but adds deps/CPU — gzip at the proxy is sufficient.
- **Process count vs cache duplication**: more workers = more parallel CPU but N× cache memory and N× cold-start cost (per-worker 300 MB DataFrame cache + response bytes). P2 precompute/warmup mitigates; a shared Redis tier is *not* warranted yet — HTTP caching delivers the same cross-worker benefit with zero new infrastructure. [prof-db §4]
- **ETag correctness with TTL caching**: 304s are as stale as the cached payload (max 300 s) — identical to today's cache-hit behavior, not a regression. A scrape can bump a `data_version` to invalidate ETags early if needed.
- **SQLite vs PostgreSQL**: stay on SQLite for this shape (ETL writes a snapshot; API read-only, single host). Move only if multi-host shared writes or network DB access become requirements; the TFB data shows DB-bound endpoints drop framework throughput 7–15× regardless of framework. [bench §5]
- **Benchmark humility**: the 15k → 120k → 715k+ req/s spread for "the same Falcon app" is entirely server/hardware; never quote one number without its server config. This repo's real ceiling today is the 2.4–15 s cold load, not any framework or server limit. [bench §1.3]

---

## Remaining Gaps & Uncertainty

- **Absolute local loopback numbers are client-capped** (~5.2k rps ceiling); re-measure with wrk/oha before tuning past them. [deploy gaps]
- **SQL-pushdown comparison is not apples-to-apples** (SQL aggregates all dates in range vs pandas' 45-newest-files semantics); the measured 3–18 s vs 2.5 s gap is still decisive against wiring them in, but a rewritten SQL path honoring the same semantics could close part of it — untested. [single-source = local]
- **mmap ≥ file size** (2.8 GB on 2.68 GB DB) is safe per docs, but page-fault behavior on this box is unmeasured; mmap turns I/O errors into signals (SIGBUS) — a trade-off to accept or avoid. [bench §5]
- **Free-threaded CPython 3.14** claims are Falcon-maintainer self-reported and unverified end-to-end here (pandas/numpy/orjson gating). [single-source]
- **Granian HTTP/2 + WSGI** is unverified (official benches exercise h2 on ASGI only); assume h1 behind nginx unless tested. [deploy gaps]
- **Version sensitivity**: Granian 2.8.x, Gunicorn 26.x, Falcon 4.4 (teardown callbacks, OpenTelemetry — absent in 4.3.1) are fast-moving; re-run `--help` and changelog checks after upgrades. Several non-Tier-1 microbenchmarks are single-source; they agree directionally but not in absolute values. [core gaps, deploy gaps]
- **ETag/frontend interplay** (Svelte fetch caching behavior) and **gzip full-payload costs** were not end-to-end tested against the deployed frontend.

---

## Sources & Provenance

Primary evidence is consolidated in the four notes files listed at the top of this report (38, 30, 37, and 37 KB; ~140 numbered citations total, tiered Tier1/2/3). Tier-1 anchors cited across them:

- [^core-13]: Falcon 4.3.1 WSGI Request & Response docs — ETag/conditional primitives, `data` vs `media`. https://falcon.readthedocs.io/en/stable/api/request_and_response_wsgi.html
- [^core-app]: Installed Falcon 4.3.1 source (app.py, response.py, request.py, middleware.py, routing/compiled.py, media/json.py) — verified in repo venv.
- [^deploy-1]: Granian official benchmarks. https://github.com/emmett-framework/granian/blob/master/benchmarks/vs.md
- [^deploy-3]: Granian source (`server/common.py`, installed 2.8.2) — blocking-threads default derivation.
- [^deploy-5]: Gunicorn Settings reference. https://gunicorn.org/reference/settings/
- [^bench-1]: TechEmpower Round 22/23 physical results JSON (via Wayback). https://www.techempower.com/benchmarks/
- [^bench-14]: SQLite WAL documentation (read-only rules, SQLITE_BUSY cases). https://www.sqlite.org/wal.html
- [^bench-15]: Hynek Schlawack, "SQLite WAL Mode Can Lock Short-Lived Readers" (2026). https://hynek.me/til/sqlite-read-only-wal-locked/
- [^prof-17]: orjson vs ujson vs msgspec benchmarks (Python 3.13). https://www.aijsons.com/blog/json-in-python-working-data/
- [^prof-27]: RFC 9111 — HTTP Caching. https://datatracker.ietf.org/doc/html/rfc9111/
- Local measurements (`[^local]`-family): taken on this repo 2026-09-07 (Falcon 4.3.1, Python 3.14.7, pandas 3.0.5, orjson 3.12.0, SQLite 3.53.1, prices.db 2.68 GB / 4.09M rows, 16-core WSL host).


---

## Implementation status (updated after report)

### P0 implemented 2026-09-03 (HTTP layer)
Verified with `scripts/verify_falcon_api.py`, `scripts/test_new_endpoints.py`, and live HTTP runs.

- **ETag + If-None-Match 304 + Cache-Control** on all cached GET endpoints (`inflation_dashboard/api/filters.py`, `inflation_dashboard/api/resources.py`). Strong ETags are derived once per cache entry from the pre-serialized bytes (`make_etag`, md5 — deterministic and identical across workers); `Cache-Control: public, max-age=300` matches the 300 s TTL. 304s are emitted via Falcon's native conditional primitives (body/Content-Type auto-stripped); wildcard `*` and weak/strong list matching per RFC 7232.
- **gzip for cached payloads >= 1 KB**: a deterministic gzip variant (`gzip.compress(mtime=0)`) is stored once per TTL entry; served when `Accept-Encoding` permits (proper `q=` weighting), with `Content-Encoding: gzip` and `Vary: Accept-Encoding`. Raw and gzip variants carry **distinct strong ETags** (a gzip representation is a different representation). Measured: 1.08 MB history payload → 83 KB (7.7% for a small window; ~2.4% for full 77 MB history).
- **Cache memory cleanup**: `_response_cache` now stores bytes only (raw + gzip + ETags) instead of `bytes + envelope dict` (~2× memory previously retained per entry), plus a 1 GiB total-byte cap with FIFO eviction (previously unbounded 512 entries).
- Removed the redundant `resp.media` assignments on cached/data paths (kept in the `except` fallback).

### P1 implemented 2026-09-03 (data layer, launcher, deps)
Verified with `scripts/verify_falcon_api.py`, `scripts/test_sqlite_adapter.py` (all 7/7 sections), `scripts/test_new_endpoints.py`, 120-concurrent-request stress (120× 200, zero SQLITE_BUSY), and live HTTP runs on granian, waitress, and uvicorn engines.

- **Thread-local reusable SQLite connections** (`inflation_dashboard/adapters/sqlite_price_repository.py`): every request-serving read helper now uses `get_reusable_connection()` (one persistent read-only connection per worker thread, lazily created) instead of a fresh `connect()`+PRAGMA per call (~20 ms/request saved; the 8 `finally: conn.close()` sites became `close_connection()` no-ops for the shared reader). `close_local_connections()` is provided for worker shutdown/tests. Verified: second `load_inventory_from_db` call drops 124 ms → ~0 ms.
- **Pragma constants reconciled to a single source of truth** (`pragma_values()` in the adapter, env-var overridable): `SQLITE_BUSY_TIMEOUT=5000`, `SQLITE_CACHE_SIZE=-128000`, `SQLITE_MMAP_SIZE=1 GiB`. The launcher no longer hardcodes conflicting 256 MiB / −64000 values; it imports `pragma_values()` and exports exactly what the repository applies; `get_readonly_sqlite_connection()` (previously dead code) now delegates to the adapter.
- **Launcher engine fixes** (`scripts/run_falcon_server.py`): waitress engine now passes `--call` (was: factory invoked as a WSGI app → 500 on every request); uvicorn engine now passes `--interface wsgi` (was: WSGI app driven as ASGI → 500). Default `--threads` reduced 16 → 8 (GIL-bound CPU workload; research recommendation). Both engines verified live (200s, ETag/304, gzip).
- **Declared server dependencies**: `pyproject.toml`/`uv.lock` now include `granian>=2.8.2` and `gunicorn>=26.2.0` (previously only `waitress` was declared despite the launcher supporting all four engines).
- **Router precompile** (`falcon_app.py`): `compile=True` on the final `add_route` removes the lazy first-request router compile (~0.36 ms) per worker.
- **Opt-in TimingMiddleware** (`falcon_app.py`, enabled via `FALCON_TIMING_LOG=1`): per-request INFO log with method, path, status, duration_ms, cache_hit (resources now tag `req.context["_cache_hit"]`).

### Remaining P1/P2/P3
Precomputed per-snapshot artifacts (pickle) to kill the 2.4–15 s first-load, boot-time warmup, response-cache per-worker memory right-sizing under many workers, pagination/column pruning for `/api/history`, CSV/parquet format variants, nginx/systemd deployment layer, and load-testing with wrk/oha.
