<!-- generated-by: gsd-doc-writer -->
# Getting Started

This guide gets a new local checkout to a working dashboard/API development state using commands verified against the current repository. For deeper context, see `README.md`, `docs/ARCHITECTURE.md`, and `docs/CONFIGURATION.md`.

## What You Can Run Locally

The repository has three practical workflows:

1. **Falcon API backend**: `inflation_dashboard.api.falcon_app:create_app` exposes CSV-backed dashboard use cases as JSON endpoints served over HTTP.
2. **Streamlit dashboard frontend**: `streamlit_app.py` reads dashboard data from the Falcon API through `inflation_dashboard.frontend.api_client` and renders views with Streamlit/Plotly.
3. **Standalone scrapers and inflation calculators**: scripts under `Codes/` and `Inflations/Codes/`.

## Prerequisites

- Python. `pyproject.toml` declares `requires-python = ">=3.14"`; checked GitHub Actions workflows still use Python 3.10, 3.11, or 3.12 for individual scrapers.
- `uv` for the project/Falcon/Streamlit workflow.
- `pip` or `python -m pip` for legacy scraper/dashboard dependency installs.

## Clone and Enter the Project

```bash
git clone <repository-url>
cd inflationstudymirror
```

Run commands from the repository root so relative paths such as `Datas/`, `scripts/`, and `streamlit_app.py` resolve correctly.

## Install Dependencies

### Full dashboard environment (recommended)

All dependencies are now declared in `pyproject.toml` and `requirements.txt`:

```bash
uv sync
```

### Legacy scraper dependency path

```bash
python -m pip install -r requirements.txt
```

## Verify the Environment

Run the combined smoke test to confirm everything is wired correctly:

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

## Run the Stack

The Falcon API and Streamlit frontend run as **two separate processes**:

### Terminal 1: Start the Falcon API

```bash
uv run waitress-serve --port=8000 inflation_dashboard.api.falcon_app:create_app
```

The API is now available at `http://localhost:8000`.

### Terminal 2: Start the Streamlit dashboard

```bash
uv run streamlit run streamlit_app.py
```

The dashboard opens in a browser. It connects to the Falcon API at `http://localhost:8000` by default — you can change this in the sidebar.

### Run individual verifiers

```bash
# Falcon API smoke test (in-process, no server needed)
uv run python scripts/verify_falcon_api.py

# Streamlit frontend API client test (source + behavior checks)
uv run python scripts/verify_streamlit_api_frontend.py

# Combined full-stack smoke test
uv run python scripts/verify_full_stack.py
```

## What the Dashboard Does

The dashboard provides four tabs:

| Tab | Description | API Endpoint Used |
|---|---|---|
| **Product explorer** | Select a product, view its price chart, cheapest date/price, and stats | `/api/history` |
| **Retailer averages** | Compare average/median prices across retailers over time | `/api/retailer-averages` |
| **Price movers** | See biggest price drops and gains across products | `/api/movers` |
| **Coverage overview** | Dataset summary, coverage over time, categories, and skipped files | `/api/coverage` |

## Dashboard Controls

- **Falcon API base URL**: Set in the sidebar (default: `http://localhost:8000`)
- **Retailer filter**: Select one or more retailers to scope the data
- **Date range**: Choose start/end dates
- **Max files per retailer**: Limit recent CSV files loaded (default: 25)
- **Load all files**: Check to bypass the file cap (may be slow)
- **Search with autocorrect**: Type partial names — misspellings are handled automatically
- **Dashboard start prediction**: Optional ML-powered price trend estimation (sidebar toggle)

## Dashboard Dependencies

All dependencies are declared in `pyproject.toml`. The key dashboard packages are:

- `falcon` — API backend
- `streamlit` — Dashboard frontend framework
- `plotly` — Interactive charts
- `pandas` — Data processing
- `requests` — HTTP client (for API calls from the frontend)
- `waitress` — Production-quality WSGI server

## Verify the Falcon API Backend

```bash
uv run python scripts/verify_falcon_api.py
```

This verification script uses Falcon's in-process `TestClient`; it does not bind a port or start a long-running server. It checks:

- API/core import boundaries
- Registered route strings for all six endpoints
- Stable response envelope keys (`data`, `meta`, `errors`)
- JSON-native serialization for pandas/numpy/date values
- Bounded endpoint smoke coverage, including invalid-filter handling

## Common Setup Issues

### `pyproject.toml` and script Python versions differ

`pyproject.toml` declares Python `>=3.14`, while checked GitHub Actions workflows use Python 3.10, 3.11, and 3.12 for individual scraper jobs. Use the workflow/script-specific Python version or adjust project metadata intentionally.

### Falcon verification should use `uv run`

Use `uv run python scripts/verify_falcon_api.py` — this matches the current project metadata path. Running plain `python scripts/verify_falcon_api.py` works only if the dependencies are already available in that Python environment.

### Large CSV history can be slow

The shared CSV adapter defaults to `DEFAULT_MAX_FILES_PER_RETAILER = 25`. Keep bounded defaults while exploring locally. Use uncapped history only intentionally through `max_files=0` / `all_history=true`.

## Next Steps

- Read `docs/ARCHITECTURE.md` for component boundaries, data flow, API routes, and verification scope.
- Read `docs/CONFIGURATION.md` for environment variables, dependency metadata, dashboard/API defaults, and GitHub Actions runtime settings.
- Read `README.md` for the broader scraper and inflation-analysis overview.
- Read `docs/USER_GUIDE.md` for a step-by-step walkthrough of using the dashboard.
