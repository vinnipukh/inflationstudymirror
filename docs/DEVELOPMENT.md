<!-- generated-by: gsd-doc-writer -->
# Development

This guide describes the development workflow that is visible in the repository. It is grounded in the current Python/Streamlit/Falcon codebase and does not assume untracked build tooling.

For related context, see:

- `README.md` for project overview, quick start, and API endpoint summary.
- `docs/ARCHITECTURE.md` for component boundaries and data flow.
- `docs/CONFIGURATION.md` for environment variables, dependency metadata, workflow schedules, and API defaults.

## Repository Shape

The repository combines legacy standalone scraper/calculator scripts with a newer shared dashboard/API package:

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
| `streamlit_app.py` | Current Streamlit dashboard UI. |
| `scripts/verify_falcon_api.py` | Bounded in-process Falcon API smoke verification. |

## Local Setup

### Python environment

Create and activate a local virtual environment with your preferred tool. The repository has both minimal `uv` metadata and a broader scraper-oriented `requirements.txt`.

```bash
# Minimal package metadata path; pyproject.toml currently declares Falcon only.
uv sync

# Broader scraper/runtime dependency list.
python -m pip install -r requirements.txt

# Dashboard dependencies imported by streamlit_app.py but not currently tracked
# in pyproject.toml or requirements.txt.
python -m pip install pandas streamlit plotly
```

Important dependency notes:

- `pyproject.toml` currently declares `requires-python = ">=3.14"` and dependency `falcon` only.
- `requirements.txt` includes scraper dependencies such as `requests`, `beautifulsoup4`, `seleniumbase`, `camoufox`, `cloudscraper`, `curl-cffi`, `python-dotenv`, and `falcon`.
- `streamlit_app.py` imports `pandas`, `plotly.express`, and `streamlit`; install those explicitly for dashboard work unless the dependency metadata is updated.
- Use `python -m pip ...` rather than relying on a bare `pip` command when the environment is ambiguous.

### Secrets and local configuration

Keep secrets out of source control. `.gitignore` ignores `.env`, `.env.*`, and `.streamlit/secrets.toml`.

The Vakko scraper reads these environment variables through `python-dotenv`:

```bash
export VAKKO_COOKIE="..."
export VAKKO_USER_AGENT="..."
python Codes/ClothingStores/Vakko/vakko_master_scraper.py
```

No `.env.example`, `.env.sample`, Streamlit config, Docker Compose file, or checked-in deployment config was found. See `docs/CONFIGURATION.md` before adding or changing configuration conventions.

## Common Development Commands

No canonical build, lint, formatter, or test scripts are defined in `pyproject.toml`, `requirements.txt`, a Makefile, or package scripts.

Useful commands discovered in the repository:

| Command | Purpose |
|---|---|
| `streamlit run streamlit_app.py` | Launch the current dashboard over tracked `Datas/` CSV files. |
| `python scripts/verify_falcon_api.py` | Run bounded Falcon API verification with Falcon's in-process test client. |
| `uv run python scripts/verify_falcon_api.py` | Run the same API smoke verification through the `uv` environment. |
| `python Codes/Markets/Gurmar/gurmar_scraper.py` | Run the Gurmar scraper and write raw CSV output under `Datas/Markets/Gurmar/`. |
| `python Codes/ClothingStores/Vakko/vakko_master_scraper.py` | Run the Vakko scraper; requires `VAKKO_COOKIE` and `VAKKO_USER_AGENT`. |
| `python Codes/HousesRent/KayseriSivasTokat/main.py -h` | Inspect rental scraper CLI options. |
| `python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h` | Inspect Gurmar inflation calculator options. |
| `python -m py_compile <path>` | Syntax-check a changed Python file. |

## Dashboard Development

The current dashboard entry point is `streamlit_app.py`.

Development expectations:

- UI concerns, widgets, Streamlit cache decorators, and Plotly rendering belong in `streamlit_app.py`.
- Reusable data loading, normalization, filtering, summaries, movers, coverage, and chart/table contracts belong under `inflation_dashboard/`.
- The dashboard currently reads the shared package directly; it does not yet consume the Falcon API over HTTP.
- Keep dashboard data loading bounded while iterating. The shared repository default is `DEFAULT_MAX_FILES_PER_RETAILER = 45` in `inflation_dashboard/adapters/csv_price_repository.py`.
- When reading CSVs, preserve tolerant parsing patterns already used by the adapter: auto-detected separators, `engine="python"`, `encoding="utf-8-sig"`, and skipped bad lines.

## Falcon API Development

The Falcon app factory is `inflation_dashboard.api.falcon_app.create_app()`.

Registered routes are:

- `GET /api/health`
- `GET /api/inventory`
- `GET /api/history`
- `GET /api/retailer-averages`
- `GET /api/movers`
- `GET /api/coverage`

API development expectations:

- Keep responses in the stable envelope shape: `{"data": ..., "meta": ..., "errors": []}`.
- Use `inflation_dashboard.api.serialization` when returning pandas, numpy, dates, mappings, or frame records to ensure JSON-native output.
- Keep `/api/health` lightweight; it should not load CSV inventory/history.
- Keep data endpoints bounded by default through `max_files` / `DEFAULT_MAX_FILES_PER_RETAILER`; `all_history=true` and `max_files=0` intentionally opt into uncapped loading.
- Validate filters in the API layer and return error envelopes rather than leaking exceptions to clients.
- There is no checked-in WSGI server command or deployment port. Local verification uses Falcon's in-process `TestClient`, not a bound HTTP port.

## Architectural Boundaries

Preserve these boundaries when changing code:

- `Codes/` owns website/API ingestion and source-specific scraper behavior.
- `Inflations/Codes/` owns inflation calculations and TUIK-style category weighting logic.
- `Datas/` and `Inflations/Datas/` are tracked data stores, not places for reusable application logic.
- `inflation_dashboard/domain/`, `inflation_dashboard/adapters/`, and `inflation_dashboard/application/` must remain free of Streamlit, Plotly, and Falcon imports.
- `inflation_dashboard/api/` owns Falcon HTTP concerns and JSON contracts. It must not import Streamlit, Plotly, or `streamlit_app.py`.
- `streamlit_app.py` owns UI rendering and Streamlit-specific caching/state.

A quick boundary check is built into `scripts/verify_falcon_api.py`. Run it after changing `inflation_dashboard/api/`, `inflation_dashboard/domain/`, `inflation_dashboard/adapters/`, or `inflation_dashboard/application/`.

## Data and CSV Conventions

- Raw scraper outputs are stored under `Datas/` and are intentionally tracked in git.
- Inflation outputs are stored under `Inflations/Datas/` and are also intentionally tracked.
- Avoid broad `.gitignore` changes for `Datas/`, `Inflations/Datas/`, or `logs/` without an explicit repository decision.
- The dashboard/API adapter discovers dated CSV files from `Datas/` and derives retailer labels from paths.
- Date extraction expects filenames containing a `20xx-MM-DD` or `20xx_MM_DD` pattern.
- When adding a new data source, update the supported retailer logic and verify that date parsing, price column detection, and row normalization work for the new CSV shape.

## Verification

The current repository does not have a general test suite. Use focused verification for the code path you changed.

### Falcon API verification

Run:

```bash
python scripts/verify_falcon_api.py
```

or, when using the `uv` environment:

```bash
uv run python scripts/verify_falcon_api.py
```

The script verifies:

- API import boundaries: no Streamlit, Plotly, or `streamlit_app.py` imports in `inflation_dashboard/api/`.
- Core import boundaries: no Falcon, Streamlit, or Plotly imports in the shared domain/application/adapter path.
- No forbidden cache/database imports in the API layer.
- Lightweight health-resource behavior.
- Registered route strings and response contract tokens.
- JSON-native response envelopes.
- In-process endpoint smoke coverage for health, inventory, history, retailer averages, movers, coverage, product-history empty state, and invalid-filter handling.

### Other focused checks

- For a changed Python file, run `python -m py_compile <path>`.
- For scraper changes, run the specific scraper in a controlled way and confirm the expected output path under `Datas/`.
- For inflation calculator changes, inspect `-h` where available and run the smallest representative input that exercises the changed path.
- For documentation-only changes, review the generated Markdown against the live repository and avoid claiming suite results that were not run.

## Code Style and Review Notes

- Scripts are mostly standalone Python modules with constants near the top, helper functions in the middle, and a `main()` or `if __name__ == "__main__"` entrypoint.
- New shared package code should prefer small functions and explicit data contracts over script-level side effects.
- Use `pathlib.Path` for new shared code where practical; older scraper code may still use `os.path` and script-relative paths.
- Keep secrets, cookies, user-agent values, and generated credentials out of source, docs, logs, and workflow output.
- If dependency metadata is updated, keep `pyproject.toml`, `uv.lock`, `requirements.txt`, and documentation consistent.
- Clearly distinguish canonical verification from ad-hoc checks in commits and PR summaries.

No formatter or linter configuration was found for Ruff, Black, Flake8, ESLint, Prettier, Biome, or EditorConfig.

## Branch and PR Process

No branch naming convention, pull request template, or contributing guide is present. The checked-out branch during documentation generation was `main`.

A practical review process for this repository is:

1. Keep scraper, calculator, dashboard/API, data, and documentation changes separated when possible.
2. State which files and data outputs were intentionally changed.
3. Run the focused verification command for the changed area.
4. Include any skipped checks and the reason they were skipped.
5. Do not commit local secrets, `.env` files, Streamlit secrets, virtual environments, cache directories, or browser/session artifacts.
