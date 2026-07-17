<!-- generated-by: gsd-doc-writer -->
# Configuration

This document records configuration that is present in the repository.

## Configuration Sources

| Source | Role |
|---|---|
| `pyproject.toml` | Python project metadata for the dashboard/API/scraper package. |
| `uv.lock` | Locked `uv` dependency state. |
| `requirements.txt` | Alternative dependency list for non-`uv` environments. |
| `.github/workflows/*.yml` | Scheduled scraper runtime configuration for GitHub Actions. |
| `Codes/**/config.py` and `Inflations/**/tuik_config.py` | Script-specific constants, TUIK category mappings, and weight settings. |
| `inflation_dashboard/adapters/csv_price_repository.py` | Dashboard/API CSV data-root, supported-retailer, and file-limit defaults. |
| `inflation_dashboard/api/filters.py` | Falcon API query-parameter defaults and validation rules. |
| `inflation_dashboard/frontend/api_client.py` | Frontend API client defaults (base URL, timeouts, data limits). |

## Environment Variables

| Variable | Required | Default | Read by |
|---|---|---|---|
| `VAKKO_COOKIE` | Required for Vakko scraping | `None` | `Codes/ClothingStores/Vakko/vakko_master_scraper.py` |
| `VAKKO_USER_AGENT` | Required for Vakko scraping | `None` | `Codes/ClothingStores/Vakko/vakko_master_scraper.py` |

No checked-in `.env.example` or `.env.sample` file is present. `.gitignore` ignores `.env`, `.env.*`, and `.streamlit/secrets.toml`.

## Python Project Metadata

### `pyproject.toml`

All dependencies are now declared in `[project.dependencies]`:

```toml
[project]
name = "inflationstudymirror"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "catboost>=1.2.10",
    "falcon",
    "ipykernel>=7.3.0",
    "jupyter>=1.1.1",
    "lightgbm>=4.6.0",
    "matplotlib>=3.11.0",
    "notebook>=7.6.0",
    "pandas>=2.0",
    "plotly",
    "requests>=2.32.0",
    "scikit-learn>=1.9.0",
    "seaborn>=0.13.2",
    "streamlit",
    "waitress>=3.0.2",
    "xgboost>=3.3.0",
]
```

This replaces the previous setup where dashboard deps (streamlit, plotly, pandas) were **not** tracked and required separate manual installs.

### `requirements.txt`

`requirements.txt` contains both scraper and dashboard dependencies:

- **Pinned packages**: `certifi`, `charset-normalizer`, `idna`, `packaging`, `python-dotenv`, `requests`, `urllib3`, `wheel`
- **Unpinned packages**: `falcon`, `camoufox`, `beautifulsoup4`, `seleniumbase`, `cloudscraper`, `curl-cffi`, `pandas`, `plotly`, `streamlit`

## Dashboard and API Defaults

| Setting | Default | Location |
|---|---|---|
| Project root | Two parents above `inflation_dashboard/adapters/` | `PROJECT_ROOT` |
| Raw data root | `<project-root>/Datas` | `RAW_DATA_ROOT` |
| Default dashboard/API retailers | `("Markets / Gurmar", "ClothingStores / Vakko", "HomeGoods")` | `DEFAULT_RETAILERS` |
| Default max files per retailer | `45` | `DEFAULT_MAX_FILES_PER_RETAILER` |
| CSV parsing | auto-detected separator, `engine="python"`, `encoding="utf-8-sig"`, `on_bad_lines="skip"` | `load_price_history()` |
| Frontend API base URL | `http://localhost:8000` | `DEFAULT_API_BASE_URL` |
| Frontend short timeout | `10` seconds | `SHORT_TIMEOUT_SECONDS` |
| Frontend data timeout | `60` seconds | `DATA_TIMEOUT_SECONDS` |
| Frontend default max files | `45` | `FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER` |

Supported dashboard/API retailer labels:

- `ClothingStores / Vakko`
- `Markets / Gurmar`
- `HomeGoods`
- `Technology`
- `Cosmetics / Watson`
- `ConstructionSuppliesMarkets / TasciYapiMarket`
- `HousesRent / Kayseri`, `Sivas`, `Tokat`
- `yapimaks`

### Falcon API routes and filter parameters

`inflation_dashboard/api/falcon_app.py` registers:

- `/api/health`
- `/api/inventory`
- `/api/history`
- `/api/retailer-averages`
- `/api/movers`
- `/api/coverage`

The API filter parser accepts query parameters from request URLs:

| Query parameter | Default | Validation |
|---|---|---|
| `retailer` | Available defaults from `DEFAULT_RETAILERS`, up to first 3 | Repeated; unknown → 400 `invalid_filter` |
| `start_date` / `end_date` | Latest 60-day window | ISO date format |
| `max_files` | `45` | Integer ≥ 0; `0` = uncapped |
| `all_history` | `false` | Boolean strings accepted |

For the Falcon API full endpoint documentation, see `docs/API.md`.

## Frontend API Client

The frontend API client (`inflation_dashboard/frontend/api_client.py`) configures:

- **Base URL**: Default `http://localhost:8000`, configurable via sidebar text input in `streamlit_app.py`
- **Timeouts**: `SHORT_TIMEOUT_SECONDS = 10` (health check), `DATA_TIMEOUT_SECONDS = 60` (data endpoints)
- **Envelope validation**: Every response is validated for `data`, `meta`, `errors` keys
- **Error handling**: Non-envelope, non-JSON, and non-200 responses raise `ApiClientError`
- **Repeated params**: `build_common_params()` serializes `retailer` as list-of-pairs for correct HTTP handling

## GitHub Actions Runtime Configuration

| Workflow | Schedule | Python | Script |
|---|---|---|---|
| `gurmar.yml` | `0 0 * * *` | 3.10 | `Codes/Markets/Gurmar/gurmar_scraper.py` |
| `yapimaks.yml` | `0 2 * * *` | 3.10 | `Codes/ConstructionMarkets/yapimaks/scraper.py` |
| `vakko_scraper.yml` | `0 4 * * *` | 3.12 | `Codes/ClothingStores/Vakko/vakko_master_scraper.py` |
| `watsons.yml` | `0 6 * * *` | 3.10 | `Codes/Cosmetics/Watson/scraper.py` |
| `chakra_scraper.yml` | `0 8 * * *` | 3.10 | `Codes/HomeGoods/scraper.py` |
| `beymen.yml` | `0 10 * * *` | 3.10 | `Codes/Technology/scraper.py` |
| `tasciyapi.yml` | `0 14 * * *` | 3.11 | `Codes/ConstructionMarkets/tasciyapimarket/tasciyapi_scraper.py` |

## Running the Stack Locally

```bash
# Terminal 1: Start the Falcon API
uv run waitress-serve --port=8000 inflation_dashboard.api.falcon_app:create_app

# Terminal 2: Start the Streamlit frontend
uv run streamlit run streamlit_app.py
```

## Verification

```bash
uv run python scripts/verify_falcon_api.py
uv run python scripts/verify_streamlit_api_frontend.py
uv run python scripts/verify_full_stack.py
```
