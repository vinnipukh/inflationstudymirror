<!-- generated-by: gsd-doc-writer -->
# Getting Started

This guide gets a new local checkout to a working dashboard/API development state using commands verified against the current repository. For deeper context, see `README.md`, `docs/ARCHITECTURE.md`, and `docs/CONFIGURATION.md`.

## What You Can Run Locally

The repository currently has three practical workflows:

1. **Streamlit dashboard**: `streamlit_app.py` reads tracked CSV files under `Datas/` through the shared `inflation_dashboard` core package and renders Streamlit/Plotly views directly.
2. **Falcon API backend**: `inflation_dashboard.api.falcon_app:create_app` exposes the same CSV-backed core use cases as JSON endpoints under `/api/*`.
3. **Standalone scrapers and inflation calculators**: scripts under `Codes/` and `Inflations/Codes/` can be run independently when their dependencies and any required secrets are available.

Phase 3 has not yet moved Streamlit to consume the Falcon API over HTTP. The current Streamlit app imports the shared adapter, use-case, and chart-spec modules directly.

## Prerequisites

- Python. `pyproject.toml` declares `requires-python = ">=3.14"`; checked GitHub Actions workflows still use Python 3.10, 3.11, or 3.12 for individual scrapers. Use the Python version required by the workflow or script you are running.
- `uv` for the minimal project/Falcon workflow. The current lockfile includes Falcon through `pyproject.toml`.
- `pip` or `python -m pip` for legacy scraper/dashboard dependency installs when you are not using a fully populated local environment.
- Optional dashboard packages: `pandas`, `streamlit`, and `plotly`. These are imported by `streamlit_app.py` but are not currently declared in `pyproject.toml` or `requirements.txt`.
- Optional scraper packages and browser tooling from `requirements.txt` for source-specific scraper runs.

## Clone and Enter the Project

```bash
git clone <repository-url>
cd inflationstudymirror
```

If you are already in this repository, run commands from the repository root so relative paths such as `Datas/`, `scripts/verify_falcon_api.py`, and `streamlit_app.py` resolve correctly.

## Install Dependencies

### Minimal Falcon API/core environment

Use the repository's `uv` metadata when you want to work on or verify the Falcon API package path:

```bash
uv sync
```

Then run commands through `uv run ...` so they use the synced environment.

### Legacy scraper dependency path

For scraper scripts and older runtime paths, install the tracked `requirements.txt` dependencies:

```bash
python -m pip install -r requirements.txt
```

`requirements.txt` contains the broader scraper-oriented dependencies, including `falcon`, `beautifulsoup4`, `seleniumbase`, `cloudscraper`, `curl-cffi`, and related HTTP/runtime packages.

### Streamlit dashboard dependencies

Install dashboard imports explicitly if your environment does not already have them:

```bash
python -m pip install pandas streamlit plotly
```

## Verify the Falcon API Backend

The current bounded API smoke check is:

```bash
uv run python scripts/verify_falcon_api.py
```

This verification script uses Falcon's in-process `TestClient`; it does not bind a port or start a long-running server. It checks:

- API/core import boundaries.
- Registered route strings for `/api/health`, `/api/inventory`, `/api/history`, `/api/retailer-averages`, `/api/movers`, and `/api/coverage`.
- Stable response envelope keys: `data`, `meta`, and `errors`.
- JSON-safe serialization for pandas/numpy/date values.
- Bounded endpoint smoke coverage, including invalid-filter handling.

A successful run prints these pass lines:

```text
PASS boundary checks: imports, stdlib-only cache boundary, lightweight health resource
PASS source contracts: endpoint routes and stable response keys
PASS endpoint smoke: health, inventory, history, retailer averages, movers, coverage, invalid-filter
```

## Run the Streamlit Dashboard

After installing `pandas`, `streamlit`, and `plotly`, start the current dashboard with:

```bash
streamlit run streamlit_app.py
```

The dashboard:

- Discovers supported dated CSV files under `Datas/`.
- Defaults to the shared retailers configured in `inflation_dashboard/adapters/csv_price_repository.py`.
- Uses a bounded max-file control to avoid loading every tracked CSV file by default.
- Renders product history, retailer averages, biggest price movers, coverage over time, category coverage, and skipped-file diagnostics.
- Calls the shared `inflation_dashboard.adapters`, `inflation_dashboard.application`, and `inflation_dashboard.domain` modules directly; it does not call the Falcon API yet.

## Work with the Falcon App Locally

The app factory is:

```text
inflation_dashboard.api.falcon_app:create_app
```

The repository does not currently include a checked-in WSGI server command, host, or port configuration. For development, prefer the verified in-process check above until an intended server runner is selected and documented.

Registered API routes are:

| Route | Purpose |
|---|---|
| `GET /api/health` | Lightweight health check that does not load CSV history. |
| `GET /api/inventory` | Lists available retailers plus discovered minimum/maximum dates and file counts. |
| `GET /api/history` | Returns normalized price history, or a single product history when `product_name` is provided. |
| `GET /api/retailer-averages` | Returns average or median price trends by date and retailer. |
| `GET /api/movers` | Returns biggest price drops and gains for repeated product observations. |
| `GET /api/coverage` | Returns dataset summary, coverage-over-time rows, category coverage, and skipped-file diagnostics. |

Common data-endpoint query parameters include repeatable `retailer`, `start_date`, `end_date`, `max_files`, and `all_history`. See `docs/CONFIGURATION.md` for defaults and validation behavior.

## Run Standalone Scripts Carefully

Start with help or a bounded run before launching scraper/calculator scripts that may write files or contact external services:

```bash
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h
```

Example scraper/calculator entry points referenced by the repository include:

```bash
python Codes/Markets/Gurmar/gurmar_scraper.py
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h
```

Some scrapers require source-specific dependencies, browser tooling, or secrets. Check the script and `docs/CONFIGURATION.md` before running them.

## Secrets and Local Configuration

Most dashboard/API behavior is configured in source constants and query parameters, not environment variables. The tracked environment variables currently documented for local use are for the Vakko scraper:

```bash
export VAKKO_COOKIE="..."
export VAKKO_USER_AGENT="..."
python Codes/ClothingStores/Vakko/vakko_master_scraper.py
```

Keep secrets in shell exports or ignored local files such as `.env`. Do not commit real cookies, tokens, user-agent values, logs, or generated files containing secrets.

## Common Setup Issues

### `pyproject.toml` and script Python versions differ

`pyproject.toml` declares Python `>=3.14`, while checked GitHub Actions workflows use Python 3.10, 3.11, and 3.12 for individual scraper jobs. If tooling refuses to create an environment because of the metadata constraint, use the workflow/script-specific Python version or adjust project metadata intentionally.

### Dashboard dependencies are not fully tracked

`streamlit_app.py` imports `pandas`, `plotly.express`, and `streamlit`, but those packages are not in the current `pyproject.toml` dependency list or `requirements.txt`. Install them explicitly before running the dashboard.

### Falcon verification should use `uv run`

Use:

```bash
uv run python scripts/verify_falcon_api.py
```

This matches the current project metadata path and was verified against the repository. Running plain `python scripts/verify_falcon_api.py` can work only if Falcon and the project imports are already available in that Python environment.

### Large CSV history can be slow

The shared CSV adapter defaults to `DEFAULT_MAX_FILES_PER_RETAILER = 45`. Keep bounded defaults while exploring locally. Use uncapped history only intentionally through dashboard controls or API filters such as `max_files=0` / `all_history=true`.

### Vakko scraper needs local secrets

`Codes/ClothingStores/Vakko/vakko_master_scraper.py` reads `VAKKO_COOKIE` and `VAKKO_USER_AGENT` after loading environment values. Missing or mismatched names will prevent authenticated Vakko scraping from working as intended.

## Next Steps

- Read `docs/ARCHITECTURE.md` for component boundaries, data flow, API routes, and verification scope.
- Read `docs/CONFIGURATION.md` for environment variables, dependency metadata, dashboard/API defaults, and GitHub Actions runtime settings.
- Read `README.md` for the broader scraper and inflation-analysis overview.
