<!-- generated-by: gsd-doc-writer -->
# Configuration

This document records configuration that is present in the repository. It does not list inferred settings, private deployment values, or untracked local files.

## Configuration Sources

| Source | Role |
|---|---|
| `pyproject.toml` | Python project metadata for the extracted dashboard/API package. |
| `uv.lock` | Locked `uv` dependency state for the `pyproject.toml` project metadata. |
| `requirements.txt` | Practical scraper/runtime dependency list used outside the minimal `pyproject.toml` metadata. |
| `.github/workflows/*.yml` | Scheduled scraper runtime configuration for GitHub Actions. |
| `Codes/**/config.py` and `Inflations/**/tuik_config.py` | Script-specific constants, scraper tuning, TUIK category mappings, and weight settings. |
| `inflation_dashboard/adapters/csv_price_repository.py` | Dashboard/API CSV data-root, supported-retailer, and file-limit defaults. |
| `inflation_dashboard/api/filters.py` | Falcon API query-parameter defaults and validation rules. |

## Environment Variables

| Variable | Required | Default | Read by | Description |
|---|---:|---|---|---|
| `VAKKO_COOKIE` | Required for Vakko scraping | `None` | `Codes/ClothingStores/Vakko/vakko_master_scraper.py` | Cookie header value sent to `https://api.vakko.com/occ/v2/vsite/products/search`. Loaded after `load_dotenv()`. |
| `VAKKO_USER_AGENT` | Required for Vakko scraping | `None` | `Codes/ClothingStores/Vakko/vakko_master_scraper.py` | User-Agent header value sent by the Vakko scraper. Loaded after `load_dotenv()`. |

No other `os.getenv()`, `os.environ`, `load_dotenv()`, `st.secrets`, or `streamlit.secrets` usage was found in tracked Python files.

### Local `.env` files

No `.env.example` or `.env.sample` file is present. `.gitignore` ignores `.env`, `.env.*`, and `.streamlit/secrets.toml`, so local secret values should stay outside git.

Example local setup for the Vakko scraper:

```bash
export VAKKO_COOKIE="..."
export VAKKO_USER_AGENT="..."
python Codes/ClothingStores/Vakko/vakko_master_scraper.py
```

Do not commit real cookie, token, or user-agent values into source files, generated documentation, logs, or workflow output.

## Python Project Metadata

### `pyproject.toml`

```toml
[project]
name = "inflationstudymirror"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "falcon",
]
```

`pyproject.toml` currently declares only the Falcon dependency used by `inflation_dashboard/api/`. It does not declare every package imported by the dashboard, scraper, and inflation scripts.

### `uv.lock`

`uv.lock` matches `pyproject.toml` and records:

- `requires-python = ">=3.14"`
- package `inflationstudymirror` version `0.1.0`
- dependency `falcon`
- resolved Falcon package version `4.3.1`

Use the `uv` workflow for the minimal Falcon API package metadata. Use `requirements.txt` or explicit installs for the older scraper and Streamlit workflows that are not fully represented in `pyproject.toml`.

### `requirements.txt`

`requirements.txt` contains the broader scraper-oriented dependency set:

- pinned: `certifi==2026.1.4`, `charset-normalizer==3.4.4`, `idna==3.11`, `packaging==26.0`, `python-dotenv==1.2.1`, `requests==2.32.5`, `urllib3==2.6.3`, `wheel==0.46.3`
- unpinned: `falcon`, `camoufox`, `beautifulsoup4`, `seleniumbase`, `cloudscraper`, `curl-cffi`

`streamlit_app.py` imports `pandas`, `plotly.express`, and `streamlit`, but those packages are not listed in the current `pyproject.toml` dependency list or in `requirements.txt`.

## Dashboard and API Defaults

Dashboard and Falcon API data loading share `inflation_dashboard/adapters/csv_price_repository.py`.

| Setting | Default | Location |
|---|---|---|
| Project root | Two parents above `inflation_dashboard/adapters/csv_price_repository.py` | `PROJECT_ROOT` |
| Raw data root | `<project-root>/Datas` | `RAW_DATA_ROOT` |
| Default dashboard/API retailers | `("Markets / Gurmar", "ClothingStores / Vakko", "HomeGoods")` | `DEFAULT_RETAILERS` |
| Default max files per retailer | `45` | `DEFAULT_MAX_FILES_PER_RETAILER` |
| CSV parsing | auto-detected separator, `engine="python"`, `encoding="utf-8-sig"`, `on_bad_lines="skip"` | `load_price_history()` |

Supported dashboard/API retailer labels are:

- `ClothingStores / Vakko`
- `Markets / Gurmar`
- `HomeGoods`
- `Technology`
- `Cosmetics / Watson`
- `ConstructionSuppliesMarkets / TasciYapiMarket`
- `HousesRent / Kayseri`
- `HousesRent / Sivas`
- `HousesRent / Tokat`
- `yapimaks`

### Falcon API routes and filter parameters

`inflation_dashboard/api/falcon_app.py` registers these routes:

- `/api/health`
- `/api/inventory`
- `/api/history`
- `/api/retailer-averages`
- `/api/movers`
- `/api/coverage`

The API filter parser accepts query parameters from request URLs, not environment variables:

| Query parameter | Default | Validation / behavior |
|---|---|---|
| `retailer` | available defaults from `DEFAULT_RETAILERS`, falling back to up to the first 3 available retailers | May be repeated as a list. Unknown retailers return a 400-style `invalid_filter` error. |
| `start_date` | latest available inventory date minus 60 days, bounded by minimum available date | Must be ISO date format accepted by `date.fromisoformat()`. |
| `end_date` | latest available inventory date | Must be ISO date format accepted by `date.fromisoformat()`. |
| `max_files` | `45` | Must be an integer greater than or equal to `0`. `0` means uncapped/all history. |
| `all_history` | `false` | Boolean strings accepted: `1,true,t,yes,y,on` and `0,false,f,no,n,off`. When true, CSV loading is uncapped. |

No checked-in ASGI/WSGI server command, port, host, or deployment config was found for serving the Falcon app. [VERIFY: choose and document the intended server command before deploying, for example a WSGI server pointed at `inflation_dashboard.api.falcon_app:create_app`.]

## Script-Specific Configuration Files

| File | Configuration role |
|---|---|
| `Codes/HousesRent/KayseriSivasTokat/config.py` | Rental scraper city list, price brackets, output/checkpoint paths, Rayobrowse endpoint and browser-fingerprint settings, viewport settings, retry/backoff limits, page caps, cooldowns, and anti-detection toggles. |
| `Inflations/Codes/Technology/tuik_config.py` | TUIK-style technology category mapping and weighting configuration. |
| `Inflations/Codes/Cosmetics/tuik_config.py` | TUIK-style cosmetics category mapping and weighting configuration. |
| `Inflations/Codes/HomeGoods/tuik_config.py` | TUIK-style home-goods category mapping and weighting configuration. |
| `Inflations/Codes/Markets/Gurmar/gurmar_tuik_config.py` | Gurmar category mapping and weighting configuration. |
| `Inflations/Codes/ClothingStores/Vakko/vakko_tuik_config.py` | Vakko category mapping and weighting configuration. |
| `Inflations/Codes/ConstructionMarkets/yapimaks/Category/yapimaks_config.py` | Yapimaks category configuration used by category tooling. |

### Rental scraper constants

`Codes/HousesRent/KayseriSivasTokat/config.py` is the largest explicit configuration module. Current notable defaults include:

- cities: Kayseri, Sivas, Tokat
- output base: `<project-root>/Datas/HousesRent`
- checkpoint dir: `Codes/HousesRent/KayseriSivasTokat/checkpoints`
- Rayobrowse endpoint: `http://localhost:9222`
- Rayobrowse target OS/browser: Windows, Chrome, browser version min/max `146`
- forced viewport: `1920x1080`
- maximum login retries per bracket: `3`
- maximum restarts per city: `3`
- maximum pages per bracket: `20`
- page size: `50`
- base URL: `https://www.sahibinden.com`

These settings are constants in the Python module, not environment variables.

## GitHub Actions Runtime Configuration

The repository includes scheduled scraper workflows under `.github/workflows/`.

| Workflow | Schedule | Python version | Dependency install command(s) | Script |
|---|---|---:|---|---|
| `gurmar.yml` | `0 0 * * *` | `3.10` | `pip install requests requests urllib3` | `Codes/Markets/Gurmar/gurmar_scraper.py` |
| `yapimaks.yml` | `0 2 * * *` | `3.10` | `pip install requests` | `Codes/ConstructionMarkets/yapimaks/scraper.py` |
| `vakko_scraper.yml` | `0 4 * * *` | `3.12` | `pip install requests pandas beautifulsoup4 python-dotenv` | `Codes/ClothingStores/Vakko/vakko_master_scraper.py` |
| `watsons.yml` | `0 6 * * *` | `3.10` | `pip install curl_cffi` | `Codes/Cosmetics/Watson/scraper.py` |
| `chakra_scraper.yml` | `0 8 * * *` | `3.10` | `pip install requests beautifulsoup4` | `Codes/HomeGoods/scraper.py` |
| `beymen.yml` | `0 10 * * *` | `3.10` | `pip install requests seleniumbase`; `seleniumbase install chromedriver` | `Codes/Technology/scraper.py` |
| `tasciyapi.yml` | `0 14 * * *` | `3.11` | `pip install requests beautifulsoup4` | `Codes\ConstructionMarkets\tasciyapimarket/tasciyapi_scraper.py` |

`vakko_scraper.yml` sets `VAKKO_COOKIE` from `secrets.VAKKO_COOKIE`, but it sets the user-agent secret as `USER_AGENT` from `secrets.VAKKO_USER_AGENT`. The tracked scraper reads `VAKKO_USER_AGENT`, so the workflow variable name and Python code currently do not match.

## Required vs Optional Settings

- Required for `Codes/ClothingStores/Vakko/vakko_master_scraper.py`: `VAKKO_COOKIE` and `VAKKO_USER_AGENT`.
- Required for the rental scraper when run as written: a local Rayobrowse-compatible service reachable at `http://localhost:9222`; this is a module constant, not an env var.
- Required for the Streamlit dashboard: install `pandas`, `plotly`, and `streamlit` in the active environment; the repository metadata does not currently provide a single canonical install command for these.
- Required for the Falcon API code path: install `falcon`; this is present in `pyproject.toml`, `uv.lock`, and `requirements.txt`.
- Optional API filters: `retailer`, `start_date`, `end_date`, `max_files`, and `all_history` query parameters.

## Per-Environment Overrides

No checked-in per-environment files such as `.env.development`, `.env.production`, `.env.test`, Streamlit config, Docker Compose, Kubernetes manifests, or deployment-specific settings were found. [VERIFY: if this project is deployed somewhere, document the external host, scheduler, server command, and secret-management mechanism from that deployment source.]

For local runs, use one of these approaches:

```bash
# Minimal Falcon dependency metadata path
uv sync

# Scraper dependency path
python -m pip install -r requirements.txt

# Dashboard dependencies that are imported but not tracked in requirements.txt
python -m pip install pandas streamlit plotly
```

Use ignored `.env` files or shell exports for secrets. Keep production-only settings in the deployment system or GitHub Actions secrets, not in tracked source files.
