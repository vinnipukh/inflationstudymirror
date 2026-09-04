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
| `InflationItems/Codes/` | Source-specific scraper scripts that collect raw retailer/service data. |
| `InflationItems/Datas/` | Tracked raw CSV data consumed by calculators, the dashboard, and the API. |
| `Inflations/Codes/` | Inflation calculation scripts and TUIK-style category/weight configuration. |
| `Inflations/Datas/` | Tracked calculated inflation outputs. |
| `inflation_dashboard/domain/` | Framework-independent parsing and normalization helpers. |
| `InflationItems/prices_json/` | Clean partitioned JSON time-series files per retailer. |
| `InflationItems/prices.db` | Local SQLite WAL database (gitignored, rebuilt via script). |
| `inflation_dashboard/adapters/` | SQLite (`sqlite_price_repository.py`) and CSV (`csv_price_repository.py`) repository adapters. |
| `inflation_dashboard/application/` | Use cases and chart/table output contracts shared by UI and API. |
| `inflation_dashboard/api/` | Falcon HTTP resources, query parsing, and JSON serialization. |
| `inflation_dashboard/frontend/` | Legacy Streamlit API client for HTTP communication with Falcon. |
| `frontend/` | **Svelte 5 / SvelteKit production dashboard** (static SPA) consuming the Falcon API; `frontend/src/lib/api/` and `frontend/src/lib/types/` mirror `docs/FALCON_API_CONTRACT.md`. |
| `streamlit_app.py` | Legacy Streamlit dashboard that reads data from the Falcon API (frozen; feature development happens in `frontend/`). |
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
python InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py
```

## Common Development Commands

| Command | Purpose |
|---|---|
| `python scripts/run_falcon_server.py --engine granian --workers 4 --port 8000` | Start production Falcon API server with Granian (Rust Hyper WSGI) |
| `python scripts/run_falcon_server.py --engine gunicorn --workers 4 --port 8000` | Start production Falcon API server with Gunicorn (gthread) |
| `python scripts/build_sqlite_from_json.py` | Rebuild `InflationItems/prices.db` from JSON files in 17 seconds |
| `python scripts/migrate_csv_to_sqlite.py` | Ingest all raw historical CSV files into `prices.db` |
| `python scripts/benchmark_concurrent_api.py --concurrency 100` | Stress-test Falcon API with 100 concurrent clients |
| `python scripts/test_sqlite_adapter.py` | Run SQLite repository adapter query benchmark suite |
| `python scripts/test_new_endpoints.py` | Test new `/api/products/search` and `/api/product` endpoints |
| `python scripts/benchmark_db_queries.py --mode compare --concurrency 100 --requests 600` | Compare SQLite connection strategies under concurrent readers |
| `python scripts/benchmark_falcon_api.py` | Measure endpoint warm/cold latency (TestClient) |
| `python scripts/verify_falcon_api.py` | Run bounded Falcon API smoke verification |
| `python scripts/verify_streamlit_api_frontend.py` | Run frontend API client verification |
| `python scripts/verify_full_stack.py` | Run combined full-stack smoke test |
| `uv run streamlit run streamlit_app.py` | Launch the legacy Streamlit dashboard frontend |
| `cd frontend && npm run dev` | Start the Svelte dashboard dev server (http://localhost:5173, proxies `/api` → :8000) |
| `cd frontend && npm run check` | Run `svelte-check` (types, a11y, unused CSS) |
| `cd frontend && npm run build` | Build the static SPA into `frontend/build/` |
| `cd frontend && npm run preview` | Preview the production build |
| `python InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py` | Run the Gurmar scraper |
| `python InflationItems/Codes/HousesRent/KayseriSivasTokat/main.py --city kayseri --rooms 3+1` | Run the rental scraper (sarı site; selenium engine — persistent profile, manual-solve loop). See `docs/APPROACH.md` first |
| `python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h` | Inspect Gurmar inflation calculator options |
| `python -m py_compile <path>` | Syntax-check a changed Python file |

## Frontend Development (Svelte, production)

The production dashboard lives in `frontend/` (Svelte 5 runes, SvelteKit with
`adapter-static` — a client-side static SPA, `ssr = false`). All data flows from
the Falcon API over HTTP; the SPA never scans CSVs.

- `frontend/src/lib/api/client.ts` — typed `fetchApi` + query serialization (repeated `retailer` params).
- `frontend/src/lib/types/api.ts` — TypeScript contracts; keep in sync with `docs/FALCON_API_CONTRACT.md` when endpoints change.
- `frontend/src/lib/stores/filters.svelte.ts` — global filter state (runes); `DEFAULT_RETAILERS = ["Markets / Gurmar"]` (auto-loads Gurmar on open).
- `frontend/src/lib/views/` — one component per tab (ProductExplorer, RetailerAverages, PriceMovers, CoverageOverview).
- Charts use Apache ECharts (`frontend/src/lib/components/Chart.svelte`); themes come from the Minimalism & Swiss Style tokens in `frontend/src/app.css`.
- Product Explorer shows the **monthly average price chart** by default (months × ₺, computed client-side from `/api/product` full history) and an optional **daily chart** behind the “Show daily chart” toggle.
- The API base URL is set at build time via `VITE_API_BASE_URL` (default `http://localhost:8000`) and can be overridden at runtime in the sidebar.
- Checks: `npm run check` (0 errors/warnings expected) and `npm run build` before committing frontend changes.

## Dashboard Development (legacy Streamlit)

The dashboard entry point is `streamlit_app.py`. All dashboard data comes from the Falcon API via `inflation_dashboard.frontend.api_client`.

Development expectations:

- UI concerns, widgets, Streamlit cache decorators, and Plotly rendering belong in `streamlit_app.py`.
- API client logic, endpoint wrappers, and envelope validation belong in `inflation_dashboard/frontend/api_client.py`.
- Reusable data loading, normalization, filtering, and use cases belong under `inflation_dashboard/` (domain, adapters, application, api).
- The dashboard no longer directly scans CSVs — all tab data flows through the Falcon API.
- Keep dashboard data loading bounded while iterating (`FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER = 45`).

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

- `InflationItems/Codes/` owns website/API ingestion and scraper behavior.
- `Inflations/Codes/` owns inflation calculations and TUIK-style weighting.
- `InflationItems/Datas/` and `Inflations/Datas/` are tracked data stores.
- `inflation_dashboard/domain/`, `adapters/`, and `application/` must remain free of Streamlit, Plotly, and Falcon imports.
- `inflation_dashboard/api/` owns Falcon HTTP concerns and must not import Streamlit/Plotly/streamlit_app.py.
- `inflation_dashboard/frontend/` owns the HTTP API client and must not import Streamlit/Plotly/core modules.
- `streamlit_app.py` owns UI rendering and Streamlit-specific caching/state.
- `frontend/` owns browser UI concerns; it only talks to the Falcon API over HTTP (see `docs/FALCON_API_CONTRACT.md`) and must not import Python modules.

Boundary checks are built into `scripts/verify_falcon_api.py` and `scripts/verify_streamlit_api_frontend.py`.

## Data and CSV Conventions

- Raw scraper outputs are stored under `InflationItems/Datas/` and are intentionally tracked in git.
- Avoid broad `.gitignore` changes for `InflationItems/Datas/`, `Inflations/Datas/`, or `logs/`.
- Date extraction expects filenames containing a `20xx-MM-DD` or `20xx_MM_DD` pattern.
- When adding a new data source, update the supported retailer logic and verify date parsing, price column detection, and row normalization.

## Verification

Three verification scripts are available:

### Falcon API smoke test

```bash
uv run python scripts/verify_falcon_api.py
```

Verifies API import boundaries, registered routes, response envelope keys, JSON-native serialization, and bounded endpoint smoke coverage.

### Legacy Streamlit frontend verification

```bash
uv run python scripts/verify_streamlit_api_frontend.py
```

Verifies that `streamlit_app.py` uses only API client calls (not direct CSV loading), that the API client has correct endpoint wrappers and envelope validation, and that tab labels/controls/empty states are preserved.

### Svelte frontend checks

```bash
cd frontend
npm run check      # svelte-check: types, a11y, unused CSS — must be 0 errors / 0 warnings
npm run build      # production static build (adapter-static → frontend/build/)
npm run preview    # serve the build locally for browser verification
```

End-to-end verification: start the Falcon API (SQLite-backed) and preview the
build, then exercise all four tabs in a browser (data, charts, filters).

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
