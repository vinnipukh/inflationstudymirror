<!-- generated-by: gsd-doc-writer -->
# Testing

## Current Testing Posture

This repository does not currently define a conventional automated test suite. Live inspection found no `tests/` directory, no `test*.py` files, and no canonical `pytest`, lint, or coverage command in `pyproject.toml`, `requirements.txt`, or project scripts.

The current canonical verification target is the Falcon API smoke/boundary checker:

```bash
uv run python scripts/verify_falcon_api.py
```

This script is the primary regression check for the Phase 2 API backend described in `README.md` and `docs/ARCHITECTURE.md`. It uses Falcon's in-process `TestClient`; it does not bind a port, launch a persistent server, or require a browser.

## Dependency Setup for Verification

Use the repository root as the working directory.

### Minimal Falcon API verification environment

`pyproject.toml` currently declares the minimal Falcon dependency path:

```bash
uv sync
uv run python scripts/verify_falcon_api.py
```

`uv.lock` records Falcon as the locked dependency for this path. `docs/CONFIGURATION.md` has more detail about the split between `pyproject.toml`, `uv.lock`, and `requirements.txt`.

### Broader scraper/dashboard environment

The older scraper and dashboard workflows are not fully represented by `pyproject.toml`:

```bash
python -m pip install -r requirements.txt
python -m pip install pandas streamlit plotly
```

Use this path when manually running scraper scripts or the Streamlit dashboard. The Streamlit dashboard imports `pandas`, `plotly.express`, and `streamlit`; those packages are not currently listed in `requirements.txt`.

## Falcon API Smoke and Boundary Check

Run:

```bash
uv run python scripts/verify_falcon_api.py
```

Expected output shape:

```text
PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource
PASS source contracts: endpoint routes and stable response keys
PASS endpoint smoke: health, inventory, history, retailer averages, movers, coverage, invalid-filter
```

The script verifies:

- `inflation_dashboard/api/` does not import `streamlit`, `streamlit_app`, `plotly`, or database/cache frameworks listed in the verifier.
- Core dashboard modules under `inflation_dashboard/domain/`, `inflation_dashboard/application/`, and `inflation_dashboard/adapters/csv_price_repository.py` do not import Falcon, Streamlit, or Plotly.
- `HealthResource` remains lightweight and does not load CSV inventory/history.
- `inflation_dashboard.api.falcon_app.create_app()` registers:
  - `/api/health`
  - `/api/inventory`
  - `/api/history`
  - `/api/retailer-averages`
  - `/api/movers`
  - `/api/coverage`
- API response envelopes keep the stable top-level keys `data`, `meta`, and `errors`.
- Response payloads are JSON-native and do not leak pandas/numpy scalar objects, NaN, or Infinity values.
- In-process endpoint smoke checks cover health, inventory, history, retailer averages, movers, coverage, an empty product-history response, and invalid-filter handling.

The checker uses bounded API requests such as `max_files=1` for data endpoints so routine verification does not scan all tracked CSV history.

## Python Syntax Checks

For changes outside the Falcon API verifier, use targeted syntax checks on the files you touched:

```bash
python -m py_compile streamlit_app.py
python -m py_compile inflation_dashboard/domain/prices.py
python -m py_compile inflation_dashboard/adapters/csv_price_repository.py
python -m py_compile inflation_dashboard/application/use_cases.py
python -m py_compile inflation_dashboard/api/filters.py
python -m py_compile inflation_dashboard/api/resources.py
python -m py_compile inflation_dashboard/api/serialization.py
python -m py_compile inflation_dashboard/api/falcon_app.py
```

These are syntax checks only. Do not report them as unit-test, integration-test, or coverage results.

## Streamlit Dashboard Checks

There is no automated browser or snapshot suite for `streamlit_app.py`.

For manual dashboard verification:

```bash
streamlit run streamlit_app.py
```

Recommended checks after dashboard changes:

- The app starts without import errors.
- Retailer/date filters populate from tracked `Datas/` CSV inventory.
- Product history selection handles empty and populated selections.
- Charts and tables render with bounded data rather than forcing all history to load.
- Any behavior that depends on the planned API frontend is called out explicitly; Phase 3 has not landed, so the current Streamlit UI still reads the shared package directly rather than calling Falcon over HTTP.

## Scraper and Inflation Script Checks

Scraper and inflation scripts under `Codes/` and `Inflations/Codes/` are source-specific and mostly standalone. There is no common test harness for them.

For script changes, prefer the smallest safe check available:

```bash
python -m py_compile path/to/script.py
python path/to/script.py --help
```

Only run a live scraper when you intentionally want network access and new CSV output. Many scheduled GitHub Actions workflows commit generated CSV files back to the repository, so inspect `git status --short` after scraper runs.

## GitHub Actions

The workflows under `.github/workflows/` are operational scraper jobs, not test workflows. They install source-specific dependencies, run scraper scripts, and commit generated data files.

Examples include:

| Workflow | Purpose |
|---|---|
| `.github/workflows/gurmar.yml` | Runs the Gurmar market scraper. |
| `.github/workflows/yapimaks.yml` | Runs the Yapimaks construction-market scraper. |
| `.github/workflows/vakko_scraper.yml` | Runs the Vakko clothing scraper. |
| `.github/workflows/watsons.yml` | Runs the Watson cosmetics scraper. |
| `.github/workflows/chakra_scraper.yml` | Runs the home-goods scraper. |
| `.github/workflows/beymen.yml` | Runs the technology scraper. |
| `.github/workflows/tasciyapi.yml` | Runs the Tasci Yapi construction-market scraper. |

Passing scheduled scraper automation means a particular scraper completed in GitHub Actions. It should not be interpreted as proof that dashboard/API contracts, unit behavior, or coverage thresholds passed.

## Writing New Tests

No repository-wide test naming convention is established yet. If a suite is added, prefer small fixture-driven tests around reusable modules rather than full-history scans over all tracked data.

Good first targets:

- `inflation_dashboard/domain/prices.py::coerce_price()` for Turkish lira strings, decimal commas, thousands separators, numeric inputs, and invalid values.
- `inflation_dashboard/domain/prices.py::parse_date_from_name()` for supported filename date patterns.
- `inflation_dashboard/domain/prices.py::build_product_frame()` for source-specific row normalization.
- `inflation_dashboard/adapters/csv_price_repository.py::discover_csv_inventory()` with a temporary directory of tiny CSV files.
- `inflation_dashboard/adapters/csv_price_repository.py::load_price_history()` for date filtering, `max_files` limits, retailer filtering, and skipped-file diagnostics.
- `inflation_dashboard/application/use_cases.py` aggregation functions using small in-memory pandas DataFrames.
- `inflation_dashboard/api/filters.py` for date, boolean, retailer, and `max_files` validation.
- `inflation_dashboard/api/serialization.py` for JSON-safe conversion of pandas/numpy/date values.

When adding tests, keep data fixtures small and synthetic. Avoid tests that depend on scanning every CSV under `Datas/` unless they are explicitly marked as slow/manual.

## Coverage

No coverage tool or threshold is configured. Live inspection found no `.coveragerc`, coverage configuration, or CI coverage gate.

| Type | Threshold |
|---|---|
| Lines | Not configured |
| Branches | Not configured |
| Functions | Not configured |
| Statements | Not configured |

Do not claim coverage percentages until a coverage tool and command are added to the repository.

## Reporting Verification Results

When documenting or reporting verification, distinguish the type of evidence:

- `scripts/verify_falcon_api.py` passing: Falcon API smoke, source-contract, response-envelope, JSON-serialization, and boundary checks passed.
- `python -m py_compile ...` passing: targeted syntax check passed.
- `streamlit run streamlit_app.py` manual check: local dashboard startup/UI behavior was manually exercised.
- Scraper workflow or local scraper passing: a source-specific scraper ran; generated files and side effects still need review.

Avoid describing the current project as having a full test suite until one is actually added.
