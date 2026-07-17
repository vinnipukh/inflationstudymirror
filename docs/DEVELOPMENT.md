<!-- generated-by: gsd-doc-writer -->
# Development

This guide describes the development workflow for the repository. For related context, see:

- `README.md` for project overview and quick start.
- `docs/ARCHITECTURE.md` for component boundaries and data flow.
- `docs/CONFIGURATION.md` for environment variables and dependencies.
- `docs/GETTING-STARTED.md` for initial setup and run commands.
- `docs/USER_GUIDE.md` for end-user dashboard walkthrough.

## Repository Shape

| Path | Development role |
|---|---|
| `Codes/` | Source-specific scraper scripts that collect raw retailer/service data. |
| `Datas/` | Tracked raw CSV data consumed by calculators, the dashboard, and the API. |
| `Inflations/Codes/` | Inflation calculation scripts and TUIK-style category/weight configuration. |
| `Inflations/Datas/` | Tracked calculated inflation outputs. |
| `inflation_dashboard/domain/` | Framework-independent parsing and normalization helpers. |
| `inflation_dashboard/adapters/` | CSV repository adapter over `Datas/`. |
| `inflation_dashboard/application/` | Use cases and chart/table output contracts shared by UI and API. |
| `inflation_dashboard/api/` | Falcon HTTP resources, query parsing, and JSON serialization. |
| `inflation_dashboard/frontend/` | Streamlit API client for HTTP communication with Falcon. |
| `streamlit_app.py` | Dashboard frontend that reads data from the Falcon API. |
| `scripts/verify_falcon_api.py` | Bounded in-process Falcon API smoke verification. |
| `scripts/verify_streamlit_api_frontend.py` | Streamlit API client source/behavior verification. |
| `scripts/verify_full_stack.py` | Combined full-stack smoke test. |

## Local Setup

### Python environment

Create and activate a local virtual environment with your preferred tool:

```bash
# Full dependency path (all dependencies now declared in pyproject.toml)
uv sync
```

All dashboard, API, scraper, and inflation calculator dependencies are declared in `pyproject.toml`.

### Secrets and local configuration

Keep secrets out of source control. `.gitignore` ignores `.env`, `.env.*`, and `.streamlit/secrets.toml`.

The Vakko scraper reads `VAKKO_COOKIE` and `VAKKO_USER_AGENT` through `python-dotenv`:

```bash
export VAKKO_COOKIE="..."
export VAKKO_USER_AGENT="..."
python Codes/ClothingStores/Vakko/vakko_master_scraper.py
```

## Common Development Commands

| Command | Purpose |
|---|---|
| `uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app` | Start the Falcon API server |
| `uv run streamlit run streamlit_app.py` | Launch the Streamlit dashboard frontend |
| `uv run python scripts/verify_falcon_api.py` | Run bounded Falcon API smoke verification |
| `uv run python scripts/verify_streamlit_api_frontend.py` | Run frontend API client verification |
| `uv run python scripts/verify_full_stack.py` | Run combined full-stack smoke test |
| `python Codes/Markets/Gurmar/gurmar_scraper.py` | Run the Gurmar scraper |
| `python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h` | Inspect Gurmar inflation calculator options |
| `python -m py_compile <path>` | Syntax-check a changed Python file |

## Dashboard Development

The dashboard entry point is `streamlit_app.py`. All dashboard data comes from the Falcon API via `inflation_dashboard.frontend.api_client`.

Development expectations:

- UI concerns, widgets, Streamlit cache decorators, and Plotly rendering belong in `streamlit_app.py`.
- API client logic, endpoint wrappers, and envelope validation belong in `inflation_dashboard/frontend/api_client.py`.
- Reusable data loading, normalization, filtering, and use cases belong under `inflation_dashboard/` (domain, adapters, application, api).
- The dashboard no longer directly scans CSVs — all tab data flows through the Falcon API.
- Keep dashboard data loading bounded while iterating (`DEFAULT_MAX_FILES_PER_RETAILER = 25`).

## Falcon API Development

The Falcon app factory is `inflation_dashboard.api.falcon_app.create_app()`.

Registered routes:

- `GET /api/health`
- `GET /api/inventory`
- `GET /api/history`
- `GET /api/retailer-averages`
- `GET /api/movers`
- `GET /api/coverage`

API development expectations:

- Keep responses in the stable envelope shape: `{"data": ..., "meta": ..., "errors": []}`.
- Use `inflation_dashboard.api.serialization` when returning pandas/numpy/date data.
- Keep `/api/health` lightweight; it should not load CSV inventory/history.
- Keep data endpoints bounded by default through `max_files` / `DEFAULT_MAX_FILES_PER_RETAILER`.
- Validate filters in the API layer and return error envelopes.

## Architectural Boundaries

Preserve these boundaries when changing code:

- `Codes/` owns website/API ingestion and scraper behavior.
- `Inflations/Codes/` owns inflation calculations and TUIK-style weighting.
- `Datas/` and `Inflations/Datas/` are tracked data stores.
- `inflation_dashboard/domain/`, `adapters/`, and `application/` must remain free of Streamlit, Plotly, and Falcon imports.
- `inflation_dashboard/api/` owns Falcon HTTP concerns and must not import Streamlit/Plotly/streamlit_app.py.
- `inflation_dashboard/frontend/` owns the HTTP API client and must not import Streamlit/Plotly/core modules.
- `streamlit_app.py` owns UI rendering and Streamlit-specific caching/state.

Boundary checks are built into `scripts/verify_falcon_api.py` and `scripts/verify_streamlit_api_frontend.py`.

## Data and CSV Conventions

- Raw scraper outputs are stored under `Datas/` and are intentionally tracked in git.
- Avoid broad `.gitignore` changes for `Datas/`, `Inflations/Datas/`, or `logs/`.
- Date extraction expects filenames containing a `20xx-MM-DD` or `20xx_MM_DD` pattern.
- When adding a new data source, update the supported retailer logic and verify date parsing, price column detection, and row normalization.

## Verification

Three verification scripts are available:

### Falcon API smoke test

```bash
uv run python scripts/verify_falcon_api.py
```

Verifies API import boundaries, registered routes, response envelope keys, JSON-native serialization, and bounded endpoint smoke coverage.

### Streamlit frontend verification

```bash
uv run python scripts/verify_streamlit_api_frontend.py
```

Verifies that `streamlit_app.py` uses only API client calls (not direct CSV loading), that the API client has correct endpoint wrappers and envelope validation, and that tab labels/controls/empty states are preserved.

### Combined full-stack smoke test

```bash
uv run python scripts/verify_full_stack.py
```

Runs both verifiers above plus cross-layer integration checks through an in-process Falcon TestClient.

### Other focused checks

- For syntax checks: `python -m py_compile <path>`
- For scraper changes: run the specific scraper in a controlled way.
- For documentation changes: review against the live repository.

## Code Style and Review Notes

- Scripts are mostly standalone Python modules with constants, helper functions, and a `main()` entrypoint.
- New shared package code should prefer small functions and explicit data contracts.
- Use `pathlib.Path` for new shared code where practical.
- Keep secrets out of source, docs, logs, and workflow output.
- If dependency metadata is updated, keep `pyproject.toml`, `uv.lock`, `requirements.txt`, and documentation consistent.
- Clearly distinguish canonical verification from ad-hoc checks.
