<!-- generated-by: gsd-doc-writer -->
# Testing

## Verification Scripts

The repository provides core verification scripts under `scripts/` plus scaling-refactor verifiers (see `docs/ASGI-SCALING-REFACTOR.md`):

### 1. Falcon API Smoke Test (`verify_falcon_api.py`)

The primary backend verifier. Tests Falcon API endpoints using in-process `TestClient` (no server needed):

```bash
uv run python scripts/verify_falcon_api.py
```

Expected output:
```text
PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource
PASS source contracts: endpoint routes and stable response keys
PASS endpoint smoke: health, inventory, history, retailer averages, movers, coverage, invalid-filter
```

### 2. Streamlit Frontend Verifier (`verify_streamlit_api_frontend.py`)

Tests that the Streamlit frontend correctly uses the Falcon API client:

```bash
uv run python scripts/verify_streamlit_api_frontend.py
```

Expected output:
```text
PASS source: final Streamlit tab/API boundary assertions
PASS source: final frontend API client assertions
PASS behavior: client params, endpoint wrappers, envelope validation, ApiClientError, timeouts
PASS final Phase 03 Streamlit API frontend verifier
```

### 3. Combined Full-Stack Smoke Test (`verify_full_stack.py`)

Runs all checks from both verifiers above plus cross-layer integration tests:

```bash
uv run python scripts/verify_full_stack.py
```

Expected output:
```text
PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource
PASS source contracts: endpoint routes and stable response keys
PASS endpoint smoke: health, inventory, history, retailer averages, movers, coverage, invalid-filter
PASS source: final Streamlit tab/API boundary assertions
PASS source: final frontend API client assertions
PASS behavior: client params, endpoint wrappers, envelope validation, ApiClientError, timeouts
PASS final Phase 03 Streamlit API frontend verifier
PASS full-stack: end-to-end frontend client <-> Falcon API integration
```

This is the recommended single command for verifying the entire dashboard/API stack.

### 4. ASGI Scaling Verifier (`verify_asgi_api.py`)

Covers the additive ASGI entry point (`inflation_dashboard/api/asgi_app.py`). Part A runs in-process middleware checks, Part B runs a live uvicorn server:

```bash
uv run python scripts/verify_asgi_api.py
```

Expected tail output:
```text
All 12 ASGI checks passed.
```

### 5. Redis Store Verifier (`verify_redis_store.py`)

Covers the Redis-backed store (`inflation_dashboard/adapters/redis_store.py`) via `fakeredis`, including circuit-breaker fallback to memory:

```bash
uv run python scripts/verify_redis_store.py
```

Expected tail output:
```text
All 7 Redis store checks passed.
```

## Run Commands Reference

```bash
# Run a specific verifier
uv run python scripts/verify_falcon_api.py
uv run python scripts/verify_streamlit_api_frontend.py

# Run all verifiers at once
uv run python scripts/verify_full_stack.py

# Scaling-refactor verifiers (additive ASGI path)
uv run python scripts/verify_asgi_api.py
uv run python scripts/verify_redis_store.py

# Start the API server for manual testing
uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app

# Start the production Svelte frontend
cd frontend && npm run dev

# Start the legacy Streamlit frontend (alternative)
uv run streamlit run streamlit_app.py
```

## What the Verifiers Check

### Falcon API Smoke Test
- API import boundaries (no Streamlit, Plotly, or streamlit_app.py in `inflation_dashboard/api/`)
- Core import boundaries (no Falcon, Streamlit, or Plotly in domain/application/adapter modules)
- No forbidden cache/database imports in the API layer
- Lightweight health-resource behavior
- Registered route strings for all six endpoints
- Response envelope keys (`data`, `meta`, `errors`)
- JSON-native serialization (no pandas/numpy leaks, no NaN/Infinity)
- In-process endpoint smoke coverage for health, inventory, history, retailer averages, movers, coverage, product-history empty state, and invalid-filter handling

### Streamlit Frontend Verifier
- `streamlit_app.py` no longer imports CSV loading functions directly
- Sidebar exposes configurable Falcon API base URL
- All four tab labels are preserved
- Each tab calls the correct API endpoint with correct parameters
- API client has correct envelope validation, timeout constants, and error handling
- Empty/error states display properly
- Search/autocorrect controls remain functional
- All history checkbox maps to `max_files=0` semantics

### Combined Full-Stack Smoke Test
- Everything from both verifiers above
- End-to-end integration: frontend API client calls through Falcon TestClient
- Cross-layer error propagation (invalid filter → API 400 → client raises ApiClientError)
- Response envelope parsing by frontend code

### ASGI Scaling Verifier
- Middleware in-process checks plus live uvicorn server (see `docs/ASGI-SCALING-REFACTOR.md`)

### Redis Store Verifier
- `fakeredis` store checks with circuit-breaker fallback to memory

## Dependency Setup

All dependencies are declared in `pyproject.toml`:

```bash
uv sync
```

Then run verifiers with `uv run python ...`.

## Python Syntax Checks

For quick syntax validation of changed files:

```bash
python -m py_compile streamlit_app.py
python -m py_compile scripts/verify_falcon_api.py
python -m py_compile scripts/verify_streamlit_api_frontend.py
python -m py_compile scripts/verify_full_stack.py
python -m py_compile scripts/verify_asgi_api.py
python -m py_compile scripts/verify_redis_store.py
python -m py_compile inflation_dashboard/domain/prices.py
python -m py_compile inflation_dashboard/application/use_cases.py
```

These are syntax checks only — not unit, integration, or coverage tests.

## Writing New Tests

No repository-wide test naming convention is established yet. If a suite is added, prefer small fixture-driven tests around reusable modules rather than full-history scans.

Good first targets for a test suite:

- `inflation_dashboard/domain/prices.py::coerce_price()` — price format normalization
- `inflation_dashboard/domain/prices.py::parse_date_from_name()` — filename date extraction
- `inflation_dashboard/adapters/csv_price_repository.py::discover_csv_inventory()` — with tiny synthetic CSVs
- `inflation_dashboard/application/use_cases.py` — aggregation functions with small in-memory DataFrames
- `inflation_dashboard/api/filters.py` — filter validation logic
- `inflation_dashboard/api/serialization.py` — JSON-safe conversion of pandas/numpy values

**Rental scrapers:** per the project principle in `AGENTS.md` (added 2026-09-02), scraper code under `InflationItems/Codes/` carries **no unit or smoke tests** — the way to test a scraper is to *use* it. The previous fixture-driven Emlakjet parser/pagination tests (`tests/test_houses_rent_scrapers.py`) were deleted on that date. Verification happens via bounded live runs (e.g. `--start-url <small province> --max-pages-per-scope N`), scheduled runs, and the CSVs/checkpoints/logs they produce. See `docs/TECH-STACK-SEARCH.md` §3.1 for the Emlakjet verification runs.

When adding tests, keep data fixtures small and synthetic. Avoid tests that scan every CSV under `InflationItems/Datas/` unless explicitly marked as slow.

## Coverage

No coverage tool or threshold is configured. Do not claim coverage percentages until a tool and command are added.

## GitHub Actions

The workflows under `.github/workflows/` are operational scraper jobs, not test workflows. They install source-specific dependencies, run scraper scripts, and commit generated data files. Passing schedules do not imply dashboard/API contract or unit test coverage.


## Svelte Frontend Checks

The Svelte frontend (`frontend/`) is verified with its own toolchain:

```bash
cd frontend
npm run check    # svelte-check — TypeScript types, a11y warnings, unused CSS
npm run build    # production static build (must succeed, writes frontend/build/)
```

End-to-end verification against a running stack:

1. Start the Falcon API: `uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app`
2. Build + preview the frontend: `cd frontend && npm run build && npm run preview`
3. Open the dashboard in a browser and exercise all four tabs (product explorer
   incl. monthly-average chart + daily-chart toggle, retailer averages, movers,
   coverage), change filters, and confirm API warnings/errors surface correctly.

Checks must stay at **0 errors / 0 warnings** before committing frontend changes.

## What the Verifiers Check (detailed)

Consolidated from the 2026-09 API verification/contract work (source: former SUBAGENT_5 report).

### Falcon API Smoke Test
- **Import boundaries**: `inflation_dashboard/api/*` must not import `streamlit`, `streamlit_app`, `plotly`, or
  database engines (`redis`, `sqlalchemy`, `django`, `peewee`, `sqlite3`); core/adapters must not import
  presentation frameworks (`falcon`, `streamlit`, `plotly`). The adapter scan covers the **whole
  `inflation_dashboard/adapters/` directory** (previously hardcoded to `csv_price_repository.py`).
- **Health isolation**: `HealthResource` must not touch inventory/history loaders.
- **Source contracts**: required routes registered (`/api/health`, `/api/inventory`, `/api/history`,
  `/api/retailer-averages`, `/api/movers`, `/api/coverage`) and stable JSON keys present in `resources.py`
  (`retailers`, `min_date`, `max_date`, `history`, `summary`, `records`, `biggest_drops`, `biggest_gains`,
  `coverage_over_time`, `category_coverage`, `skipped_files`, `skipped_file_count`).
- **Endpoint smoke**: in-process `TestClient` GETs against all routes; every response must be a
  `{data, meta, errors}` envelope; JSON-native serialization (no `NaN`, `Infinity`, `pd.NA`, `pd.NaT`, numpy
  scalars); invalid retailer → HTTP 400 with `errors[0].code == "invalid_filter"`.
- **CORS preflight** is validated as part of the full-stack / contract checks (`OPTIONS` returns
  `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Methods: GET`).

### Legacy Streamlit Frontend Verifier
- `streamlit_app.py` routes all data through `inflation_dashboard.frontend.api_client` (no direct adapter/domain
  imports), correct endpoint wrappers, envelope validation, `ApiClientError` for 400/invalid envelope/bad JSON,
  and preserved tab labels/controls/empty states.
