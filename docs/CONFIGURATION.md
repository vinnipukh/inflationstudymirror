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
| `InflationItems/Codes/**/config.py` and `Inflations/**/tuik_config.py` | Script-specific constants, TUIK category mappings, and weight settings. |
| `inflation_dashboard/adapters/csv_price_repository.py` | Dashboard/API CSV data-root, supported-retailer, and file-limit defaults. |
| `inflation_dashboard/api/filters.py` | Falcon API query-parameter defaults, validation rules, and TTL caches. |
| `inflation_dashboard/frontend/api_client.py` | Frontend API client defaults (base URL, timeouts, data limits). |

## Environment Variables

| Variable | Required | Default | Read by |
|---|---|---|---|
| `VAKKO_COOKIE` | Required for Vakko scraping | `None` | `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` |
| `VAKKO_USER_AGENT` | Required for Vakko scraping | `None` | `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` |
| `VAKKO_HEADED` | Optional; `=1` runs Vakko's cookie-factory Chrome headed | `None` (headless) | `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` |
| `CHROME_DEBUGGER_ADDRESS` | Optional Emlakjet CDP attach endpoint (e.g. `127.0.0.1:9222`) | `None` | `InflationItems/Codes/HousesRent/Emlakjet/scraper.py` |

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
    "orjson>=3.12.0",
    "pandas>=2.0",
    "plotly",
    "requests>=2.32.0",
    "scikit-learn>=1.9.0",
    "seaborn>=0.13.2",
    "selenium>=4.47.0",
    "streamlit",
    "waitress>=3.0.2",
    "xgboost>=3.3.0",
]
```

This replaces the previous setup where dashboard deps (streamlit, plotly, pandas) were **not** tracked and required separate manual installs.

### `requirements.txt`

`requirements.txt` contains both scraper and dashboard dependencies:

- **Pinned packages**: `certifi`, `charset-normalizer`, `idna`, `packaging`, `python-dotenv`, `requests`, `urllib3`, `wheel`
- **Unpinned packages**: `falcon`, `camoufox`, `beautifulsoup4`, `seleniumbase`, `cloudscraper`, `curl-cffi`, `selenium`, `undetected-chromedriver`, `lxml`, `tqdm`, `pandas`, `plotly`, `streamlit`

## Dashboard and API Defaults

| Setting | Default | Location |
|---|---|---|
| Project root | Two parents above `inflation_dashboard/adapters/` | `PROJECT_ROOT` |
| Raw data root | `<project-root>/Datas` | `RAW_DATA_ROOT` |
| Default dashboard/API retailers | `("Markets / Gurmar", "ClothingStores / Vakko", "HomeGoods")` | `DEFAULT_RETAILERS` |
| Default max files per retailer | `25` | `DEFAULT_MAX_FILES_PER_RETAILER` |
| CSV parsing | auto-detected separator, `engine="python"`, `encoding="utf-8-sig"`, `on_bad_lines="skip"` | `load_price_history()` |
| Frontend API base URL | `http://localhost:8000` | `DEFAULT_API_BASE_URL` |
| Frontend short timeout | `10` seconds | `SHORT_TIMEOUT_SECONDS` |
| Frontend data timeout | `60` seconds | `DATA_TIMEOUT_SECONDS` |
| Frontend default max files | `25` | `FRONTEND_DEFAULT_MAX_FILES_PER_RETAILER` |

Supported dashboard/API retailer labels:

- `ClothingStores / Vakko`
- `Markets / Gurmar`
- `HomeGoods`
- `Technology`
- `Cosmetics / Watson`
- `ConstructionSuppliesMarkets / TasciYapiMarket`
- `HousesRent / Kayseri`, `Sivas`, `Tokat`
- `HousesRent / Emlakjet`
- `ConstructionSuppliesMarkets / yapimaks`

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
| `max_files` | `25` | Integer ≥ 0; `0` = uncapped |
| `all_history` | `false` | Boolean strings accepted |

For the Falcon API full endpoint documentation, see `docs/API.md`.

### Server-side caching & performance (2026-08-16)

The Falcon API keeps in-process, stdlib-only TTL caches so repeated/interleaved
requests do not re-read CSVs from disk (the original hot path cost ~4.4s per
request; a single Streamlit rerun fired ~5 overlapping data requests):

- **Loaded history cache** (`filters.py`): `load_filtered_history` results
  keyed by `(retailers, start, end, max_files, all_history)`; TTL 300s, LRU
  with a ~300MB byte budget, entries > 120MB skipped, copy-on-return.
- **Per-file frame cache** (`csv_price_repository.py`): built product frames
  keyed by `(path, mtime_ns, size)`; TTL 600s, maxsize 512, frames > 200k
  rows skipped. Overlapping filter sets reuse parsed files.
- **Filter-parse dedupe** (`filters.py`): `parse_common_filters` results keyed
  by the raw request signature, TTL 300s.
- **Fast serialization** (`serialization.py`): vectorized per-column JSON
  conversion (typed fast paths + distinct-value date mapping); output is
  byte-identical to the generic walk. `orjson` is the Falcon JSON media
  handler (`falcon_app.py`) for large payloads.

Caches clear automatically on TTL expiry; `clear_inventory_cache()` (api
filters) also clears the derived history/parse/file caches for tests and when
new scraped CSVs land. New data becomes visible within ≤5 minutes of landing.

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
| `gurmar.yml` | `0 0 * * *` | 3.10 | `InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py` |
| `yapimaks.yml` | `0 2 * * *` | 3.10 | `InflationItems/Codes/ConstructionMarkets/yapimaks/scraper.py` |
| `vakko_scraper.yml` | `0 4 * * *` | 3.12 | `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` |
| `watsons.yml` | `0 6 * * *` | 3.10 | `InflationItems/Codes/Cosmetics/Watson/scraper.py` |
| `chakra_scraper.yml` | `0 8 * * *` | 3.10 | `InflationItems/Codes/HomeGoods/scraper.py` |
| `beymen.yml` | `0 10 * * *` | 3.10 | `InflationItems/Codes/Technology/scraper.py` |
| `tasciyapi.yml` | `0 14 * * *` | 3.11 | `InflationItems/Codes/ConstructionMarkets/tasciyapimarket/scraper.py` |
| `emlakjet_scraper.yml` | `0 16 * * *` | 3.11 | `InflationItems/Codes/HousesRent/Emlakjet/scraper.py` |

Runtime notes (2026-09-02):

- **yapimaks.yml**: `timeout-minutes: 360` — the platform hard cap for public
  repos (the previous `480` was never reachable). The scraper runs async
  (aiohttp) with `--refresh-budget 2500` (daily, stalest-first) and
  `--max-duration 240` (min); a full catch-up completes in ≈1 h. All limits
  are CLI-overridable (`--workers`, `--rate`, `--refresh-budget`,
  `--max-duration`).
- **emlakjet_scraper.yml**: runs with `--resume` and commits the whole
  `InflationItems/Datas/HousesRent/Emlakjet/` dir (CSV + checkpoint state), so an
  interrupted crawl continues on the next run. `--max-page-retries` (default
  3) and `--page-timeout` (45 s) tune the browser-restart behavior.

## Rental Scraper Configuration (`InflationItems/Codes/HousesRent/KayseriSivasTokat/config.py`)

The rental scraper (sarı site — Kayseri/Sivas/Tokat) is configured entirely in its own `config.py` — no environment variables. It uses the **friend-tactics** engine (`engine_selenium.py`): `undetected-chromedriver` bound to a **persistent** Chrome profile + a manual-solve-retry loop + adaptive pacing (no auto-Turnstile code; the day-one Turnstile is solved manually and the warm session is reused thereafter).

| Setting | Default | Notes |
|---|---|---|
| `BASE_URL` | `https://www.sahibinden.com` | Site domain (kept literal — required by the scraper) |
| `CITIES` | kayseri, sivas, tokat | Each with `DEFAULT_BRACKETS` |
| `DEFAULT_BRACKETS` | 5 TL ranges: 0–19,999 → 100,000–9,999,999 | Price segmentation for pagination |
| `ROOMS_FILTER` | `"3+1"` | Only rows whose Rooms cell matches exactly are saved (compliance scope). `None` = all room types (e.g. via `--rooms` CLI flag) |
| `PAGE_SIZE` | 50 | Listings per page (`pagingSize`) |
| `MAX_PAGES_PER_BRACKET` | 20 | Safety page cap per price range (`MAX_LISTINGS_PER_QUERY` = 1000) |
| `PROFILE_DIR` | `SeleniumProfile/` | Persistent `--user-data-dir` carrying `cf_clearance`/`_px3` across daily runs |
| Adaptive pacing | `PAGE_LOAD_DELAY` 2.5 s (±50%), `ADAPTIVE_*` shrink/grow 1.5–8.0 s | Success streaks shrink delay; errors grow it |
| Retry / backoff | `MAX_RETRIES` 3, `RETRY_BACKOFF_BASE` 2.0 s, `RETRY_BACKOFF_MAX` 30 s | Exponential backoff on failed page fetches |
| Output | `InflationItems/Datas/HousesRent/{City}/{date}.csv` | `District, Rooms, Price, ilanId` columns (B0 compliance — `docs/APPROACH.md`) |

The engine (`engine_selenium.py`) uses the friend-tactics pattern: persistent SeleniumProfile + manual solve-retry loop (no auto-Turnstile code needed). The sister browser-backed Emlakjet adapter is documented in `InflationItems/Codes/HousesRent/README.md`; its live-site recon and the planned evolution of both rental scrapers are in `docs/APPROACH.md` and `docs/TECH-STACK-SEARCH.md`.

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

## API TTL Cache

The API layer (`inflation_dashboard/api/filters.py`) maintains two in-memory TTL caches to reduce redundant disk reads when multiple endpoints are called with the same filter parameters:

| Cache | TTL | Max entries | Key |
|---|---|---|---|
| CSV inventory (`get_inventory`) | 60 seconds | 1 | — |
| Loaded price history (`load_filtered_history`) | 45 seconds | 32 | `(retailers, start_date, end_date, max_files)` |

The history cache is the primary performance win: when the Streamlit frontend renders four tabs, each calls a different API endpoint, but all load the same bounded CSV files. The first request reads the CSVs from disk (~280ms); the next three hit the cache and return in ~5ms each. The cache automatically expires after 45 seconds, so new data from scheduled scraper runs becomes visible without restarting the API server.
