<!-- generated-by: gsd-doc-writer -->
# Testing

## Verification Scripts

The repository provides three verification scripts under `scripts/`:

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
PASS full-stack: end-to-end frontend client ↔ Falcon API integration
```

This is the recommended single command for verifying the entire dashboard/API stack.

## Run Commands Reference

```bash
# Run a specific verifier
uv run python scripts/verify_falcon_api.py
uv run python scripts/verify_streamlit_api_frontend.py

# Run all verifiers at once
uv run python scripts/verify_full_stack.py

# Start the API server for manual testing
uv run waitress-serve --port=8000 inflation_dashboard.api.falcon_app:create_app

# Start the Streamlit frontend
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

When adding tests, keep data fixtures small and synthetic. Avoid tests that scan every CSV under `Datas/` unless explicitly marked as slow.

## Coverage

No coverage tool or threshold is configured. Do not claim coverage percentages until a tool and command are added.

## GitHub Actions

The workflows under `.github/workflows/` are operational scraper jobs, not test workflows. They install source-specific dependencies, run scraper scripts, and commit generated data files. Passing schedules do not imply dashboard/API contract or unit test coverage.
