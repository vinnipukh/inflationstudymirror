# Falcon Framework Core Optimization — Research Notes

Research subagent output for topic: **FALCON FRAMEWORK CORE OPTIMIZATION** (request path, middleware,
routing, media handling, response generation).
Repo grounded in `/mnt/e/Projects/inflationstudymirror` (Falcon 4.3.1 WSGI, orjson media handlers,
pre-serialized byte TTL cache, read-only SQLite, Granian/Gunicorn launcher, Python 3.14.7).
Method: official Falcon 4.3.1 docs + GitHub falconry/falcon issues/PRs + installed 4.3.1 source
(verified directly in the repo venv) + local micro-benchmarks in the repo venv + Tier-2/3 benchmarks.
Companion notes (already in repo): `docs/research-notes-profiling-db-caching-falcon.md` covers DB/profiling/caching/compression measurements.

## Executive summary

- Framework overhead is tiny relative to this API's work: a full WSGI request through Falcon 4.3.1
  measures ~63 µs (bare GET), CORSMiddleware adds ~3 µs (+5%), and routing is ~0.35 µs. The pandas/SQLite
  aggregations (ms–s) dominate, so app-level wins (caching, conditional requests, compression, worker
  counts) dwarf any Falcon-internal micro-tuning. [^local]
- The repo's response path is already optimal at the framework level: `resp.data = raw_bytes` bypasses
  media-handler serialization entirely (render precedence: `text` → `data` → `media`), and `orjson`
  pre-serialization is the officially recommended CPython pattern. The redundant `resp.media = envelope_dict`
  that precedes it is dead weight (harmless, ~40 ns) and removable. [^local] [^13]
- Biggest framework-level gap: no ETag/If-None-Match conditional handling and no Cache-Control headers,
  so every repeat GET re-transfers multi-MB history payloads even though the TTL cache already holds the
  bytes. Falcon parses conditional headers for free (`req.if_none_match`) and strips 304 bodies
  automatically; adding ETag/304 to the cache-hit path is the highest-value change (~15 lines). [^13] [^app]
- WSGI + multi-process Granian/Gunicorn- gthread is the right shape for this CPU-bound pandas workload;
  ASGI only wins for I/O-bound work (~5× under sleep-dominated load in 2026 benchmarks) and adds
  websockets/background tasks/SSE if those features are ever needed. Keep WSGI; scale `--workers`. [^25] [^14]
- Falcon 4.2+ Cythonized URI encode/decode (~9–12×), and the installed 4.3.1 binary wheel already carries
  `cyutil` (.so) so this repo gets those wins. No 4.x-vs-3.x regression was found (maintainers: "no
  significant regression"; cythonized wheels faster). [^8] [^7] [^22]

## Findings

### 1. Middleware: cost, lightweight patterns, hooks vs middleware, CORS overhead

- Global vs scoped: middleware methods apply globally to the whole app; hooks are attached per-responder
  or per-resource at route-registration time. Use middleware only for logic that must run for every
  request (auth, CORS, request-id); use hooks (or plain decorators) for per-resource logic so unrelated
  routes don't pay for it. [^1] [^12]
- Execution model (Falcon 4.x, verified in installed source `app_helpers.prepare_middleware`): middleware
  methods are looked up and bound **once** at app preparation ("PERF(kgriffs): do getattr calls once, in
  advance, so we don't have to do them every time in the request path"), so the per-request cost is
  just the loop over pre-bound callables — not getattr. Order: `process_request` in list order (before
  routing), `process_resource` in list order (after routing, only when a route matches),
  `process_response` in reverse list order. `independent_middleware=True` is the default in
  `falcon.App(...)` (verified in 4.3.1 signature) and controls whether `process_response` still runs when
  a request middleware aborts. [^1] [^app] [^local]
- Measured cost in this repo's env: full request path no middleware ~63 µs; with one no-op two-method
  middleware ~65 µs (+2 µs); with `CORSMiddleware(allow_origins='*')` ~66 µs (+3 µs, ≈ +5%). So one
  lightweight middleware is noise at this API's scale; a stack of 5+ does matter at microservice RPS. [^local]
- CORS internals (verified in installed `middleware.py`): `process_response` reads `req.get_header('Origin')`
  (~0.29 µs, pure dict lookup when absent) and returns immediately when Origin is missing; with `'*'` it
  sets two headers when Origin is present. Preflight (OPTIONS + `Access-Control-Request-Method`) is
  handled by the middleware; Falcon auto-adds OPTIONS responders to routes that lack `on_options`
  (documented). `Access-Control-Max-Age: 86400` is emitted on preflight, so browsers cache CORS checks
  for 24 h — repeat same-origin-style requests do not re-preflight. [^2] [^mw] [^local]
- Current repo CORS setup is fine: `expose_headers=[]` normalizes to `''` (falsy → header not sent);
  `allow_origins='*'` avoids the frozenset membership check (wildcard fast path). If this API is served
  same-origin behind a reverse proxy that also serves the Svelte app, the middleware could be dropped
  (+3 µs and preflight handling), but keeping it at this cost is defensible. Docs also recommend a real
  AuthN/Z layer regardless of CORS. [^2] [^app] Known CORS edge cases
  (header casing, preflight replies) are discussed in falconry/falcon discussion #2095. [^38]
- Short-circuiting: `resp.complete = True` from `process_request`/`process_resource` skips remaining
  request middleware, `process_resource` methods, and the responder, while still running all
  `process_response` methods. Official docs explicitly mention this for "responses that may be
  pre-constructed, such as in the case of caching." If the repo ever moves caching into middleware,
  this is the sanctioned fast path. [^1]
- No per-request allocation antipatterns in the repo's middleware (there is exactly one, CORSMiddleware).
  General rule: pre-bind everything at import (regexes via `re.compile`, header names, cached lookups),
  avoid building new dicts/lists per request, pass cross-middleware data via `req.context`/`resp.context`,
  never import modules or instantiate loggers per request. [^1] [^13]
- Concrete overhead data point from TechEmpower's Falcon entry: emitting extra headers (Server/Date) in
  app code cost ~18% throughput at 433k→356k req/s on a raw-throughput test — evidence that per-request
  header/allocation work is the only big middleware-class lever left at framework level; skip gratuitous
  per-request work. Context: sibling repo notes report the API broadens when scraping updates change
  payload size; header/ETag work here is µs-level. [^29] [^local]

### 2. Routing: default vs custom routers, match cost, route registration, compiled routers

- Falcon 4.x default router is `falcon.routing.CompiledRouter` (also exported as `DefaultRouter`,
  verified: same class). It compiles the route table into generated Python code once, then `find()` is a
  single function call (segment-by-segment dict/tuple dispatch, no regex per request). [^3] [^4] [^app]
- Measured (repo venv, 4.3.1): steady-state `find()` ≈ **0.35 µs median** with 8 routes — negligible
  against the ~63 µs request path. Routing is not a bottleneck at this scale; a custom router is only
  justified for hundreds+ of routes, object-based traversal, or versioning-by-header (interface:
  `add_route(uri_template, resource, **kwargs)` + `find(uri, req)` returning
  `(resource, method_map, params, uri_template)`). [^local] [^3]
- Compilation is **lazy** by default: `_find` is swapped from `_compile_and_find` to the compiled
  function on the first routed request (verified in source; docs: "the decision tree is compiled only
  when the router handles the first request"). With the repo's 8 routes this costs ~361 µs once per
  worker process (measured); with 1000 routes it is ~66 ms. First-request latency after every worker
  restart therefore includes this compile unless forced. [^4] [^local] [^3]
- `add_route(..., compile=True)` forces compilation immediately — docs advise passing it on the **last**
  route added ("Always setting this flag to True may slow down the addition of new routes when hundreds
  are added at once. It is advisable to only set this flag to True when adding the final route.").
  A thread-safe lock guards concurrent first-use compilation. [^3] [^4] [^5]
- Historical context (why lazy compile exists): issue #1550 reported O(n²) route-addition + recompilation;
  PR #1665 fixed it by delaying compile and removing per-add verification. Startup-to-first-response
  measurements from that PR: 9 routes 3.5 ms→1.5 ms; 81 routes 120 ms→9.4 ms; 729 routes 11.2 s→88 ms;
  6561 routes 1144 s→0.96 s; 59049 routes →10.4 s. Field converters are validated at `add_route` time
  (no hidden first-request check remains). [^5] [^6]
- Suffixed responders (`add_route(..., suffix='items')` → `on_get_items`) are mapped at registration
  time via `map_http_methods`; they add zero per-request cost vs normal responders. Issue #2167 documents
  a behavior nuance (params dict differs), not performance. [^3] [^16]
- Practical conclusion for the repo: keep the default CompiledRouter; optionally pass `compile=True` on
  the last `add_route` in `create_app()` to make first-response latency deterministic (cosmetic at 8
  routes — 0.36 ms). Do not add a custom router.

### 3. Media/body handling: JSONHandler vs custom, resp.data vs resp.media, streaming, double deserialization

- `resp.data` (bytes) bypasses the media pipeline entirely: `Response.render_body()` (verified in
  installed 4.3.1) short-circuits `text` → `_data` → serialized `_media`. Setting `resp.data = raw_bytes`
  means the orjson handler's `serialize()` and the handler `_resolve()` lookup **never run**; the only
  costs are the attribute sets and the auto Content-Length (`len(data)`, always emitted for the data
  path — verified in `App.__call__`). [^13] [^local] [^app]
- Measured in the repo env: pre-serialized `resp.data` path ~67 µs vs `resp.media` + orjson handler
  ~75 µs for a tiny object (≈8 µs serialization+resolution). For the repo's real payloads serialization
  is dominated by orjson itself (already memoized into the TTL cache), so the data path is correct.
  The official docs say the same: for byte content "use the `data` attribute instead (it's faster)". [^local] [^13]
- Official JSONHandler docs explicitly recommend swapping in `msgspec`, `orjson`, `python-rapidjson`,
  or `mujson` under CPython "for a significant performance boost" (stdlib `json` is only recommended on
  PyPy) — exactly what the repo did. [^11]
- The repo sets both `resp.media = envelope_dict` and `resp.data = raw_bytes` in `_send_response` and in
  every cache-hit block. Because `data` wins in `render_body()`, the media assignment is never
  serialized; it is redundant state (it also resets `_media_rendered` to `_UNSET`, which is harmless
  here). Recommendation: drop the `resp.media` line on the cached/data paths, keep the `resp.media`
  fallback in the `except` branch of `_send_response` (it only runs if orjson.dumps fails). [^13] [^app] [^local]
- Request side: `req.media` / `req.get_media()` deserializes once and caches the result on the Request
  (`_media`), so repeated access never re-parses; the docs push new WSGI apps toward `get_media()`
  (the property is a 3.0+ backward-compat alias). No double-deserialization exists in this repo (all
  GETs, no body parsing); if POST endpoints are added later, call `get_media()` once and reuse. [^13]
- `req.bounded_stream` is a **lazy** wrapper over `wsgi.input` (verified: `self._bounded_stream = None  # Lazy wrapping`),
  so it costs nothing on GETs. It is Content-Length-aware (never blocks on out-of-bounds reads, safe with
  0/missing Content-Length) and works directly with `json.load(req.bounded_stream)` — the right primitive
  for streaming large request bodies instead of buffering everything. Default media handlers buffer the
  whole body; ASGI `BaseHandler.deserialize_async()` adapts sync `deserialize()` via `io.BytesIO`
  ("For improved performance, media handlers should override this method") — relevant only if an ASGI
  port happens. [^13] [^11]
- Query-string parsing is **eager**: `Request.__init__` (verified in installed source) calls
  `parse_query_string(...)` whenever `QUERY_STRING` is non-empty, before any `get_param` call. Measured:
  `Request` construction 0.75 µs with a 3-param query string vs 0.50 µs without — the eager parse is
  ~0.25 µs, and `req.get_param` then costs ~0.10 µs (dict lookup). So the repo's cache key
  `req.query_string` does not add parse cost, and the parse itself is far below noise. There is no
  double parse. (Historical note: #1604 cythonized `parse_query_string`; #1594 optimized `uri.decode`
  for form parsing.) [^13] [^local] [^17] [^18]
- New in 4.3.0 (available in this repo): `req.get_query_string_as_media()` (#2546) and
  `req.get_param_as_media()` (#2549) deserialize whole-query/param JSON in one step, plus
  `get_param_as_dict()` and `get_param_as_list(delimiter=...)` — use these instead of hand-rolled
  JSON-in-query parsing (avoids double deserialization) if such filters are ever added. [^10]
- `falcon.media.Handlers.copy()` (4.0+) allows per-app handler-map copies; `MEDIA_CSV` and
  `MEDIA_PARQUET` constants exist since 4.1.0 — both relevant if the API ever offers alternative
  formats for the large history payload (see recommendations). [^11] [^9]

### 4. Response optimizations: ETag/conditional requests, cache headers, compression, streaming, keep-alive

- Falcon ships **first-class conditional-request primitives** (docs + installed source):
  `req.if_none_match` (parsed list of `falcon.ETag` objects including weak/strong flags), `req.if_match`,
  `req.if_modified_since` (timezone-aware since 4.0), `req.if_range`, and response side `resp.etag`
  (auto-wraps the value in double quotes), `resp.cache_control` (iterable joined with ", "),
  `resp.expires`, `resp.last_modified`. Parsing is lazy and header-absent-cheap: `if_none_match` reads
  `env.get('HTTP_IF_NONE_MATCH')` only when accessed (verified). [^13] [^local]
- The official `falcon.ETag` docstring contains the canonical 304 pattern: compare `req.if_none_match`
  entries (`etag == '*'` or strong/weak equality per RFC 7232), set `resp.status = falcon.HTTP_304`
  and return; otherwise set `resp.etag` and 200. [^13] [^21] [^24]
- Falcon itself will strip the body and Content-Type from 304/204 automatically (verified in
  `App.__call__`: `_BODILESS_STATUS_CODES`, `_TYPELESS_STATUS_CODES` → `default_media_type = None`,
  body `[]`), so a 304 responder only sets status (and ideally `resp.etag` for consistency). No
  manual body-clearing needed. [^app]
- Framework-level ETag/304 exists **only for static routes** (`StaticRoute` renders ETag + If-None-Match
  304 since 4.1.0 via PR #2450, and Last-Modified + If-Modified-Since 304 via #2244). Dynamic resources
  must implement conditional handling themselves — which is exactly the repo's situation. [^9] [^19] [^20]
- The repo's TTL cache (entry: `(timestamp, raw_bytes, envelope_dict)`, 512 entries, 300 s) makes
  ETag/304 nearly free: compute one short hash of `raw_bytes` at cache-put (e.g. `md5(raw_bytes).hexdigest()`
  — microseconds for MBs, one time per entry), store it, and on cache-hit compare against
  `req.if_none_match`. Cost when the header is absent: one env lookup (~0.3 µs). Benefit: 350k-row
  history payloads stop being re-transferred on every dashboard rerun; browsers/proxies absorb repeats.
  Since the TTL already bounds staleness (300 s), `Cache-Control: private, max-age=300` is consistent. [^local] [^13]
- Compression: **Falcon core has no gzip/brotli middleware** (verified: no compression module in the
  installed package; nothing in the 4.x changelogs). The third-party `falcon-caching` package caches response body+Content-Type via msgpack but has no ETag/304 logic; the repo's own byte-cache is already leaner (no msgpack round-trip). [^30] Community compression options are ASGI-only (`asgi-compression`,
  `fullonic/brotli-asgi`). WSGI options: reverse proxy (nginx/Caddy/HAProxy) or a small custom
  middleware. Sibling research measured the repo's big payloads: 77 MB `/api/history` gzips to ~2 MB
  (≈2.4%), ~0.12 s CPU per 27 MB compressed — so compress **cached** bytes once per cache entry
  (store both raw and gzip variants, set `Vary: Accept-Encoding`, only compress >1 KB, skip
  `/api/health`). Granian 2.8.2 (installed) exposes no compression flag; it does expose `--http 2`. [^31] [^32] [^35]
- Chunked/streaming responses: `resp.stream` (file-like → `wsgi.file_wrapper`, or any byte iterable)
  yields chunked transfer when Content-Length is unknown. For this API's pre-serialized orjson bytes,
  `resp.data` (single chunk + Content-Length) is strictly better; streaming would only matter for
  generated CSV/parquet streams on the big payloads. Note Falcon always overrides Content-Length to
  match the body for keep-alive correctness (verified in `App.__call__`). [^13] [^app]
- HTTP keep-alive is a server concern, but it dominates framework-vs-server outcomes: the 2026
  Wolfrahm benchmark measured the *same* Falcon app at ~120k req/s through Granian WSGI vs a
  connection-per-request gunicorn default `sync` worker at ~10×–12× less (ephemeral-port exhaustion);
  Gunicorn's `gthread` (used by this repo) does keep-alive (default `--keep-alive 2` s; sync worker
  ignores it — verified in installed gunicorn 26.2.0 config). Waitress supports keep-alive too
  (verified in installed parser). Granian's HTTP/1 keep-alive is on by default. Practical: prefer
  Granian, or raise gunicorn `--keep-alive` to 5–10 s for direct clients; Falcon already emits
  Content-Length so keep-alive works. [^25] [^34] [^35] [^local]
- HTTP/2 (Granian `--http auto|1|2`): the dashboard fires several API calls per render; HTTP/2
  multiplexing removes connection/serialization stalls — a server-flag change, no code change. [^35]
- HEAD requests: Falcon maps HEAD to the GET responder and strips the body automatically (verified in
  `App.__call__`; keeps Content-Length). Monitoring/health probes can use `HEAD /api/history` for free
  and get real Content-Length — useful, zero work. [^app]

### 5. Falcon-specific patterns: async/ASGI vs WSGI, websockets, background tasks, pitfalls

- WSGI vs ASGI: Falcon ships both; the async stack (`falcon.asgi.App`) adds websockets, SSE emitters,
  and `resp.schedule()` / `resp.schedule_sync()` background callbacks (run after the response is sent;
  sync variant runs on the event loop's default ThreadPoolExecutor; docs warn CPU-bound callbacks block
  the loop). 2026 cross-framework benchmark (Falcon 4.3.1): ping 142k req/s (ASGI/Uvicorn) vs 120k
  (WSGI/Granian); CPU-bound 14.0k vs 11.2k (roughly equal); I/O-bound (3×~9 ms sleeps) 68k vs 16.5k —
  async's advantage is exclusively I/O concurrency (thread-pool ceiling). [^14] [^15] [^25]
- For this repo: pandas aggregations are CPU-bound and already cached; SQLite reads under WAL are
  fast. WSGI + N processes is the right model (threads share the GIL; `--workers` scales CPU).
  An ASGI port would add complexity (blocking pandas/vectorized code must be pushed to
  `asyncio.to_thread`/executors or it stalls the loop) with no CPU-bound win. Revisit only if
  SSE/websocket/streaming features are requested. [^25] [^14] Tier-3 looks at the same
  WSGI-vs-ASGI tradeoff for Falcon [^37], and Manjusaka's 2024 gevent-vs-asyncio study shows the
  identical concurrency ceiling for SQL-backed frameworks (non-Falcon context). [^36]
- Server choice evidence (Falcon-specific): Web Frameworks Benchmark (community TechEmpower-style
  harness, 2026-08-29, **Python 3.14**): falcon 4.2 ≈ 14.7–15.0k req/s at 64/256/512 concurrency —
  sitting next to other WSGI entries (baize-wsgi ≈ 14.2–14.5k), well above flask (7.6–8.9k) and django
  (1.5–4.5k); WSGI is capped by that harness's server. klen/py-frameworks-bench (2022, Falcon 3.0.1
  ASGI under gunicorn+uvicorn): 15.5k req/s simple endpoint — 3rd tier behind blacksheep/sanic.
  Deploy Mastery (2023, older Falcon): server choice swings hello-world throughput from 6.5k
  (gunicorn sync) to 13.7k (uwsgi) to 62.7k (bjoern); I/O-bound tests show WSGI ~10 req/s vs ASGI
  uvicorn 2.6k. Framework–server interaction is the top-level performance lever, not Falcon internals. [^27] [^26] [^28]
- Falcon 4.x performance history: maintainers' issue #1822 (open tracking task) — no significant
  regression vs 3.0; cythonized wheels a few µs faster; official `falconry/falcon-bench` docker images
  exist for reproducible cross-framework runs. Falcon "compiles itself with Cython when available"
  (README); installed 4.3.1 binary wheel contains `cyutil.misc/reader/uri` (.so) — URI encode/decode
  reimplemented in Cython in 4.2.0 (~9–12× per changelog). [^7] [^22] [^8]
- Free-threaded CPython 3.14: Falcon 4.2+ publishes free-threaded wheels (changelog). The repo is on
  CPython 3.14.7; switching to the free-threaded build is a big cross-cutting change (pandas/numpy
  free-threading status dominates), out of framework-level scope — flag only. [^8]
- Routing/responder niceties in 4.3.0: `default_to_on_request` router option (resources may define
  `on_request()` as the default responder for missing methods instead of 405). Not a perf lever for
  this repo. 4.4 will bring response teardown callbacks + OpenTelemetry integration (not in 4.3.1). [^10]
- Pitfalls checklist vs the repo: per-request imports (none); request-path logging (none); `json.dumps`
  in hot path (already orjson); `resp.text` with str payloads (not used — data/bytes is right);
  repeated `req.get_media()` (n/a, GET-only); regex recompilation per request (none); getattr in
  middleware (none; Falcon itself pre-binds); creating per-request logger/caches (TTL caches are module
  singletons — fine). Remaining cheat-sheet items: bind `req.get_param`-style lookups early where a
  code path calls them dozens of times; keep `req.context`/`resp.context` for cross-middleware data
  instead of new objects. [^13] [^1] [^11]

## Recommended actions for the repo (prioritized, grounded)

1. **P0 — ETag/If-None-Match 304 + Cache-Control on the TTL-cache fast path** (framework-native, ~15
   lines, biggest user-visible win). Mechanics (all verified): store `etag = '"' + hashlib.md5(raw_bytes).hexdigest() + '"'`
   in the cache entry at `put_cached_response` time (one hash per entry, not per request); on cache hit,
   if `req.if_none_match` contains the value or `'*'` → `resp.status = falcon.HTTP_304; resp.etag = etag`
   and return (Falcon strips body + Content-Type + sets no Content-Length for 304 automatically);
   else set `resp.etag = etag` and `resp.cache_control = ['private', 'max-age=300']` (aligned with the
   300 s TTL) before serving cached bytes. Cost with no header: one env lookup. Add to
   `_send_response`/`get_cached_response` and curl-test: `curl -H 'If-None-Match: <etag>' -i ...` → 304
   with empty body. Multi-worker note: identical bytes → identical etag across workers, so 304s stay
   correct. [^13] [^21] [^app] [^24]
2. **P1 — Compression for the big payloads**, cached: store gzip (and optionally brotli) byte variants
   alongside raw bytes in the same TTL entry; select by `req.get_header('Accept-Encoding')`; set
   `Content-Encoding` + `Vary: Accept-Encoding`; compress once per entry (sibling notes: 77 MB → ~2 MB,
   ~0.12 s/27 MB CPU) rather than per request. If a reverse proxy fronts the API, do it there instead.
   Skip for tiny responses (<1 KB) and `/api/health`. [^31] [^32] (sibling repo notes `docs/research-notes-profiling-db-caching-falcon.md` measured 77 MB → ~2 MB, ~0.12 s/27 MB CPU)
3. **P2 — Remove the redundant `resp.media = envelope_dict`** on cache-data paths (keep it in the
   `except` fallback). `data` wins in `render_body()`; the media set is dead state and makes the cached
   path depend on `_media` semantics. Low risk, small diff across `resources.py`. [^13] [^local]
4. **P2 — Deterministic first request**: pass `compile=True` on the last `add_route()` in
   `create_app()` (per official docs) so each worker's first request doesn't pay the ~0.36 ms router
   compile (or the ~66 ms if route count ever grows to 1000). Cosmetic now; free. [^3] [^4] [^5]
5. **P2 — Keep-alive/server flags**: prefer Granian (keep-alive on by default, `--http 2` available for
   the frontend's parallel requests); if gunicorn gthread, raise `--keep-alive` to 5–10 s for direct
   clients (default 2 s). Never use gunicorn `sync` (no persistent connections). Falcon already emits
   Content-Length so keep-alive works on the data path. [^34] [^35] [^25]
6. **P2 — Worker/thread ratio for CPU-bound pandas work**: scale `--workers` (processes) for parallel
   CPU; keep `--threads` modest (threads share the GIL for CPU, but help SQLite CLI read + orjson +
   I/O interleave). Validate with the repo's existing locust artifacts under `docs/benchmarks/`. [^25]
7. **P3 — Do not migrate to ASGI** for the current workload (CPU-bound); revisit only if SSE,
   websockets, or streaming features are requested (then `resp.schedule()`/`schedule_sync()` and
   `falcon.asgi` websockets are the native primitives). [^14] [^15] [^25]
8. **P3 — Optional format variant**: `MEDIA_CSV`/`MEDIA_PARQUET` constants exist (4.1+); an
   `?format=csv|parquet` handler for `/api/history` (or `req.client_prefers([...])` negotiation) could
   cut transfer for 350k-row payloads if the frontend ever wants it. Not needed for the current JSON
   SPA. [^9] [^11]
9. **P3 — Free-threading**: Falcon 4.2+ free-threaded wheels exist, but pandas/numpy free-threading is
   the gating factor — out of framework scope, do not pursue without a project-wide decision. [^8]

## Sources

1. [^1]: Falcon 4.3.1 Middleware docs — https://falcon.readthedocs.io/en/stable/api/middleware.html — Tier1: official framework reference (order, short-circuit, independent_middleware, exception unwinding).
2. [^2]: Falcon 4.3.1 CORS docs — https://falcon.readthedocs.io/en/stable/api/cors.html — Tier1: CORSMiddleware behavior, auto-OPTIONS responders, preflight, 4.0 ValueError on cors_enable+instance.
3. [^mw]: falcon.middleware source (4.3.1) — https://falcon.readthedocs.io/en/stable/_modules/falcon/middleware.html — Tier1: CORSMiddleware per-request process_response internals (Origin get_header, wildcard fast path, preflight headers, Max-Age 86400).
4. [^3]: Falcon 4.3.1 Routing docs — https://falcon.readthedocs.io/en/stable/api/routing.html — Tier1: CompiledRouter, lazy compile, compile=True kwarg, custom router interface, suffixed responders.
5. [^4]: falcon.routing.compiled source (4.3.1) — https://falcon.readthedocs.io/en/stable/_modules/falcon/routing/compiled.html — Tier1: `_find = _compile_and_find`, compiled finder source, converter validation at add_route, compile lock.
6. [^5]: PR falconry/falcon#1665 "Delay compilation until first use of the router" — https://github.com/falconry/falcon/pull/1665 — Tier1: startup-to-first-response tables (9→59049 routes), compile kwargs decision.
7. [^6]: Issue falconry/falcon#1550 "Adding many routes to CompiledRouter is slow (O(n^2))" — https://github.com/falconry/falcon/issues/1550 — Tier1: fixed by #1665.
8. [^7]: Issue falconry/falcon#1822 "4.x Benchmarking and Performance Tuning" (open) — https://github.com/falconry/falcon/issues/1822 — Tier1: no-significant-regression comments; falcon-bench docker images.
9. [^8]: Falcon 4.2.0 changelog — https://falcon.readthedocs.io/en/stable/changes/4.2.0.html — Tier1: Cython URI functions ~9–12×, free-threaded 3.14 wheels, Python 3.8 EOL.
10. [^9]: Falcon 4.1.0 changelog — https://falcon.readthedocs.io/en/stable/changes/4.1.0.html — Tier1: StaticRoute ETag/304 (#2243) + Last-Modified/304 (#2244), CPython 3.14 support, MEDIA_CSV/MEDIA_PARQUET (#2335).
11. [^10]: Falcon 4.3.0 changelog — https://falcon.readthedocs.io/en/stable/changes/4.3.0.html — Tier1: get_query_string_as_media (#2546), get_param_as_media (#2549), get_param_as_dict (#2542), delimiter (#2538), default_to_on_request (#2071); 4.4 plans (teardown callbacks, OpenTelemetry).
12. [^11]: Falcon 4.3.1 Media docs — https://falcon.readthedocs.io/en/stable/api/media.html — Tier1: JSONHandler third-party libs recommendation, BaseHandler.deserialize_async BytesIO adaptation note, Handlers.copy() 4.0, MEDIA_* constants.
13. [^12]: Falcon 4.3.1 Hooks docs — https://falcon.readthedocs.io/en/stable/api/hooks.html — Tier1: global middleware vs per-resource hooks.
14. [^13]: Falcon 4.3.1 WSGI Request & Response docs — https://falcon.readthedocs.io/en/stable/api/request_and_response_wsgi.html — Tier1: bounded_stream, data-vs-text, media/get_media, if_none_match/etag/cache_control, ETag 304 example in ETag docstring.
15. [^14]: Falcon 4.3.1 ASGI Request & Response docs — https://falcon.readthedocs.io/en/stable/api/request_and_response_asgi.html — Tier1: schedule()/schedule_sync() background callbacks, executor caveats.
16. [^15]: Falcon 4.3.1 WebSocket docs — https://falcon.readthedocs.io/en/stable/api/websocket.html — Tier1: on_websocket, ws_options/max_receive_queue, media handlers.
17. [^16]: Issue falconry/falcon#2167 — suffixed responders behavior nuance — https://github.com/falconry/falcon/issues/2167 — Tier1: not performance.
18. [^17]: PR falconry/falcon#1604 cythonized parse_query_string — https://github.com/falconry/falcon/pull/1604 — Tier1 (merged 2019).
19. [^18]: Issue falconry/falcon#1594 form-urlencoded parse perf / uri.decode — https://github.com/falconry/falcon/issues/1594 — Tier1.
20. [^19]: PR falconry/falcon#2450 StaticRoute ETag + If-None-Match 304 — https://github.com/falconry/falcon/pull/2450 — Tier1 (merged 2025, shipped 4.1.0).
21. [^20]: Issue falconry/falcon#2244 Last-Modified for static files — https://github.com/falconry/falcon/issues/2244 — Tier1 (shipped 4.1.0).
22. [^21]: PR falconry/falcon#1459 ETag class improvements — https://github.com/falconry/falcon/pull/1459 — Tier1.
23. [^22]: falconry/falcon README — https://github.com/falconry/falcon/blob/master/README.rst — Tier1: Cython self-compilation, PyPy, positioning.
24. [^app]: Local verification against installed Falcon 4.3.1 in the repo venv — `falcon/app.py` (`__call__`, `_get_body`, bodiless/typeless status handling, Content-Length), `falcon/response.py` (render_body, text/data/media), `falcon/request.py` (eager query parse, lazy bounded_stream, lazy if_none_match), `falcon/app_helpers.py` (prepare_middleware pre-binding), `falcon/middleware.py` (CORSMiddleware), `falcon/routing/compiled.py`, `falcon/media/json.py`, `falcon/util/structures.py` (ETag) — Tier1 (source inspection).
25. [^local]: Local micro-benchmarks run 2026-09-07 in the repo venv (Falcon 4.3.1, CPython 3.14.7, `falcon.testing` harness, median of 5 runs): bare GET 62.97 µs; +CORSMiddleware 65.97 µs; +noop middleware 65.21 µs; resp.data path 67.03 µs; resp.media+orjson 74.57 µs; CompiledRouter first find 361 µs (8 routes) / 66 ms (1000 routes); steady find 0.352 µs; Request init 0.754 µs (with qs) vs 0.503 µs (without); get_param 0.103 µs; get_header 0.290 µs — Tier1 (own measurements; absolute values include TestClient overhead, deltas are what count).
26. [^24]: RFC 7232 (HTTP conditional requests) — https://www.rfc-editor.org/rfc/rfc7232.html — Tier1 standard.
27. [^25]: Wolfrahm/rahm_http_benchmarks_py — https://github.com/Wolfrahm/rahm_http_benchmarks_py — Tier2: Falcon 4.3.1 vs FastAPI/Starlette/Robyn, equal-process-budget, ping/CPU/I-O; Granian-12×-faster-than-gunicorn-sync observation.
28. [^26]: klen/py-frameworks-bench — https://github.com/klen/py-frameworks-bench — Tier2: 2022-03-14 ASGI framework benchmark; Falcon 3.0.1 ≈15.5k req/s simple test; methodology (gunicorn+uvicorn, wrk -t4 -c64).
29. [^27]: Web Frameworks Benchmark (community TFB-style, latest 2026-08-29, python 3.14) — https://web-frameworks-benchmark.netlify.app/result?l=python — Tier2: falcon 4.2 ≈14.7–15.0k req/s @64–512 concurrency; flask 7.6–8.9k; django 1.5–4.5k.
30. [^28]: Deploy Mastery Python webserver framework benchmark (2023-10-11) — https://www.deploymastery.com/2023/10/11/complete-python-webserver-framework-performance-benchmark/ — Tier2/3: WSGI server choice 6.5k→62.7k req/s (gunicorn sync→bjoern); I/O-bound WSGI ~10 rps vs ASGI 2.6k.
31. [^29]: TechEmpower/FrameworkBenchmarks issue #8137 (Falcon unification; Server/Date header overhead 433k→356k) — https://github.com/TechEmpower/FrameworkBenchmarks/issues/8137 — Tier1/2.
32. [^30]: falcon-caching docs (zoltan-fedor) — https://falcon-caching.readthedocs.io/en/latest/ — Tier3: caching-middleware pattern (body+Content-Type, msgpack roundtrip; simpler than repo's own byte cache).
33. [^31]: "Compress Files with gzip in Falcon" (ssojet.com) — https://ssojet.com/compression/compress-files-with-gzip-in-falcon — Tier3, likely AI-generated quality — server/proxy-level compression; treat as weak evidence, corroborated by sibling repo measurements.
34. [^32]: asgi-compression (PyPI) and fullonic/brotli-asgi (GitHub) — https://pypi.org/project/asgi-compression/ , https://github.com/fullonic/brotli-asgi — Tier3: community ASGI-only gzip/brotli middleware; confirms no core Falcon compression.
35. [^34]: Gunicorn 26.2.0 installed config (`--keep-alive` default 2 s; sync worker ignores it) — Tier1 (installed source), doc: https://docs.gunicorn.org.
36. [^35]: Granian 2.8.2 installed CLI (`--http auto|1|2`, HTTP/1 keep-alive default on, no compression flag) — Tier1 (installed), doc: https://granian.dev.
37. [^36]: Manjusaka "In 2024, Gevent or asyncio?" — https://www.manjusaka.blog/posts/2024/08/19/benchmark-for-python-web-framework-2024-part1-en/index.html — Tier2 (context on async-vs-sync I/O scaling; not Falcon-specific).
38. [^37]: GeeksforGeeks "Python Falcon - WSGI vs ASGI" — https://www.geeksforgeeks.org/python/python-falcon-wsgi-vs-asgi/ — Tier3 (basic overview).
39. [^38]: falconry/falcon discussion #2095 (CORS headers) — https://github.com/falconry/falcon/discussions/2095 — Tier3 (CORS behavior Q&A).

## Gaps & uncertainty

- **Local benchmark absolute numbers** include `falcon.testing.TestClient` overhead (environ construction, response capture); only the *deltas* (middleware/CORS/serialization/routing) are authoritative. No network-level wrk/oha run was made from this session; see sibling notes / `docs/benchmarks/` for load tests. [single-source]
- **Wolfrahm benchmark** (Falcon 4.3.1) is a single Tier-2 source; hardware is an M1 Max and each server was hand-tuned. Ratios (WSGI thread-pool ceiling vs async under I/O load; Granian-vs-gunicorn-sync) are the takeaways, not absolute RPS. [single-source]
- **Web Frameworks Benchmark** falcon row (≈15k req/s, py3.14) uses the harness's own server for the WSGI entry (undocumented here) and is therefore server-capped; it does not contradict the Granian-WSGI number from [^25]. Do not quote it as "Falcon is 15k RPS".
- **no official published 4.x-vs-3.x benchmark table**; "no significant regression" comes from maintainer comments on issue #1822 [single-source]. 4.2 Cython URI numbers (~9–12×) are from the changelog itself (Tier1 but single-source).
- **ETag/304 on cached bytes**: correctness depends on the 300 s TTL semantics already in place; if scraped data updates mid-TTL, 304s are as stale as the cached payload itself (same behavior as today's cache hits). Not a regression.
- **Compression middleware**: no first-party or battle-tested WSGI compression middleware for Falcon was found; recommendations lean on reverse-proxy practice or a small custom middleware + sibling measurements of gzip ratio/CPU on this repo's actual payloads. Verify `Vary: Accept-Encoding` and cache-variant behavior with a test before enabling. [single-source for cost figures]
- **johal.in articles** ("Falcon... 1M req/s", "Cython middleware boost") surfaced repeatedly in search results; content is implausible and appears AI-generated — deliberately **excluded** from evidence.
- **jetthoughts "Falcon in Production"** is about the **Ruby** Falcon HTTP server (Rails ecosystem), not the Python Falcon framework — excluded after reading; do not cite for this repo.
- **Version sensitivity**: ETag/Last-Modified for static routes → 4.1.0; Cython URI speedups + free-threaded wheels → 4.2.0; `get_query_string_as_media`/`get_param_as_media`/`get_param_as_dict`/`default_to_on_request` → 4.3.0; `Handlers.copy()` → 4.0; tz-aware `if_modified_since` → 4.0; response teardown callbacks + OpenTelemetry → planned 4.4 (absent in 4.3.1). All claims above are for the installed 4.3.1 unless flagged.
