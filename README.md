# Inflation Study Mirror

A comprehensive data collection and inflation analysis project tracking price changes across Turkish retailers and services over time, **powered by a high-performance Falcon REST API (SQLite-backed), a minimal Svelte 5 dashboard, and ML-ready infrastructure.**

This project includes my personal contributions to https://github.com/urazkagangunes/InflationResearchStudy

---

## Installation

### Prerequisites

- **Python** `>=3.14` (declared in `pyproject.toml`)
- **Node.js `>=20` / npm** (for the Svelte frontend, `frontend/`)
- **uv** — fast Python package installer and resolver
- **Git** (to clone the repository)

### Clone and Install

```bash
git clone <repository-url>
cd inflationstudymirror
uv sync
cd frontend && npm install && cd ..
```

Python dependencies install everything for the Falcon API, scrapers, and inflation
calculators. `npm install` installs the Svelte frontend toolchain (SvelteKit, ECharts).

### Quick Start

Once installed, start the stack in two terminals:

```bash
# Terminal 1: Start the Falcon API backend (SQLite-backed, CORS open by default)
uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app

# Terminal 2: Start the Svelte frontend (production UI)
cd frontend && npm run dev
```

Open `http://localhost:5173` in your browser.

> The legacy Streamlit dashboard (`streamlit_app.py`) remains available for
> administrative use: `uv run streamlit run streamlit_app.py`.

### Verify the Installation

Run the combined full-stack smoke test to confirm the Python stack is wired correctly:

```bash
uv run python scripts/verify_full_stack.py
```

Expected output includes `PASS` across all checks: API imports, route contracts, endpoint smoke tests, frontend client, and end-to-end integration.

Verify the frontend:

```bash
cd frontend
npm run check    # svelte-check: types + a11y + CSS
npm run build    # production static build → frontend/build/
```

---

## Overview

This project scrapes product and service price data from various Turkish retailers, markets, and platforms, then processes the data to calculate inflation metrics. The repository focuses on real-time price monitoring and inflation analysis using TÜİK-style weighting standards.

The **dashboard stack** consists of:

- **Falcon REST API** — high-performance WSGI backend serving a stable `{data, meta, errors}` JSON envelope. Reads from the SQLite WAL database (`InflationItems/prices.db`) with transparent CSV fallback, multi-worker serving (Granian/Gunicorn), in-memory orjson caching, and open CORS for browser clients.
- **Svelte 5 / SvelteKit frontend** (`frontend/`) — a minimal, information-first static SPA (Apache ECharts) with four tabs, fuzzy autocorrect search, monthly-average and daily price charts, and light/dark themes.
- **Legacy Streamlit dashboard** (`streamlit_app.py`) — kept for administrative review and prototypes.

---

## Project Structure

```
inflationstudymirror/
├── InflationItems/
│   ├── Codes/                          # Web scrapers for different retailers
│   │   ├── Markets/                    # Gurmar scraper
│   │   ├── ClothingStores/             # Vakko scraper
│   │   ├── HomeGoods/                  # Chakra scraper
│   │   ├── Cosmetics/                  # Watson scraper
│   │   ├── Technology/                 # Beymen tech scraper
│   │   ├── ConstructionMarkets/        # TasciYapi, Yapimaks scrapers
│   │   └── HousesRent/                 # Rental property scrapers (sarı site, Emlakjet)
│   └── Datas/                          # Raw collected data (CSV files, tracked)
├── InflationItems/prices_json/         # Clean partitioned JSON time series
├── InflationItems/prices.db            # SQLite WAL database (built, gitignored)
├── Inflations/                         # Inflation calculation outputs
├── inflation_dashboard/                # Dashboard & API package
│   ├── domain/                         # Parsing and normalization
│   ├── adapters/                       # SQLite + CSV storage adapters
│   ├── application/                    # Use cases and chart specs
│   ├── api/                            # Falcon API (resources, filters, serialization)
│   └── frontend/                       # Legacy Streamlit API client
├── frontend/                           # Svelte 5 / SvelteKit dashboard (production UI)
│   ├── src/lib/api/                    # Falcon API client + TypeScript types
│   ├── src/lib/views/                  # One Svelte component per dashboard tab
│   └── ...
├── scripts/                            # Verification, DB build, benchmark scripts
├── docs/                               # Documentation (see below)
└── streamlit_app.py                    # Legacy Streamlit dashboard
```

---

## Features

### 8 Production-Ready REST API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service health & metadata |
| `GET /api/inventory` | Available retailers, date range, file count |
| `GET /api/history` | Price history, filterable by product & retailer |
| `GET /api/retailer-averages` | Average/Median price trends per retailer |
| `GET /api/movers` | Biggest price drops and gains |
| `GET /api/coverage` | Dataset coverage summary, category breakdown & diagnostics |
| `GET /api/products/search` | Fast product autocomplete (SQLite) |
| `GET /api/product` | Single-product full price history + summary (SQLite) |

All endpoints return a stable `{data, meta, errors}` JSON envelope with JSON-safe
serialization (no NaN/NaT), filter validation (HTTP 400 with error codes), and
open CORS (`FALCON_CORS_ORIGINS`, default `*`).

### 4 Dashboard Tabs (Svelte frontend)

| Tab | What It Shows |
|---|---|
| **Product Explorer** | Latest/cheapest metrics, **monthly average price chart** (default), optional **daily price chart** via a “Show daily chart” toggle, raw history table |
| **Retailer Averages** | Compare mean or median prices across selected retailers over time |
| **Price Movers** | Biggest drops vs. peak price & biggest gains since first observation |
| **Coverage Overview** | Total products/observations, tracked products per day, category breakdown, skipped file diagnostics |

Additional frontend behaviors:

- **Gurmar auto-load**: opens with `Markets / Gurmar` selected by default; add retailers via the searchable multi-select.
- **Smart autocorrect search** — Unicode-normalized (NFKD, Turkish characters), starts-with → contains → fuzzy ranking, with closest-match hints.
- **Minimal design system** — Minimalism & Swiss Style (UI/UX Pro Max): near-black ink + gold accent, Fira Sans/Fira Code, hairline grid, whitespace-driven; light/dark themes; reduced-motion and keyboard support.
- **Monthly vs. daily view** — the monthly average chart aggregates the full observed history (months on X, ₺ on Y); the daily chart is an optional overlay bound to the date-range filter.

### Flexible Filtering System (sidebar)

- **Multi-retailer selection** — pick any subset of available stores
- **Date range picker** — defaults to last 60 days
- **Max CSV files per retailer** — slider (default 45)
- **Load all files** — checkbox to bypass the file cap
- All filters sync across tabs via the API

### ML-Ready Infrastructure

- **Forecasting module** (`forecasting/`) — Jupyter notebook for ML-based price trend prediction
- Pre-installed ML stack: **scikit-learn, xgboost, lightgbm, catboost**

### Robust API Envelope Pattern

Every endpoint returns:

```json
{
  "data": { ... },           // Payload (JSON-safe, no NaN/NaT)
  "meta": { ... },           // Metadata (filters, warnings, file counts)
  "errors": []               // Errors array (empty on success)
}
```

Invalid filters return HTTP 400 with descriptive error codes and metadata.

### Verification

```bash
# Python stack
uv run python scripts/verify_full_stack.py

# Svelte frontend
cd frontend && npm run check && npm run build
```

---

## Dashboard Quick Start

```bash
# 1. Install dependencies
uv sync
cd frontend && npm install && cd ..

# 2. Start the API server (Terminal 1)
uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app
# (or the production launcher: python scripts/run_falcon_server.py --engine gunicorn --workers 4 --port 8000)

# 3. Start the Svelte dashboard (Terminal 2)
cd frontend && npm run dev
```

Then open your browser to `http://localhost:5173` (Svelte dev server). The Vite
dev server proxies `/api` to `http://localhost:8000`, so same-origin API calls
work out of the box.

---

## Key Features

### Data Collection
- **Multi-store scraping**: Automated data collection from diverse Turkish retailers including:
  - Cosmetics: Watson
  - Clothing: Vakko
  - Construction markets: TasciYapi, Yapımaks
  - Real Estate: Rental property data from Sarı site (Kayseri/Sivas/Tokat) and Emlakjet
  - Markets: Grocery items from Gurmar
  - Home goods: Chakra
  - Electronics: Beymen Tech products

### Architecture Phases
- **Phase 1 ✓**: Hexagonal core extraction — framework-independent domain and application modules
- **Phase 2 ✓**: Falcon API backend — REST endpoints with JSON envelopes and bounded loading
- **Phase 3 ✓**: Streamlit API frontend — four dashboard tabs reading from the Falcon API
- **Phase 4 ✓**: Deployment documentation, combined smoke tests, and dependency management
- **Phase 5 ✓**: SQLite database adapter + new `/api/products/search` & `/api/product` endpoints (2026-09)
- **Phase 6 ✓**: **Svelte 5 / SvelteKit production frontend** (`frontend/`) — minimal SPA replacing Streamlit as the default UI; CORS middleware registered in the API (2026-09)

### Inflation Analysis
- **TUIK-style metrics**: Several inflation calculators use tracked TUIK-style category mappings and weights
- **Category mapping**: Product categories mapped to tracked TUIK-style code groups
- **Time-series analysis**: Track inflation trends over days/months
- **Statistical validation**: Outlier detection and data quality filtering

### Key Technologies
- **Python 3.x** for scrapers, calculators, API, and DB tooling
- **Falcon** — high-performance Python web framework for the API backend
- **SQLite WAL** — read-only high-concurrency time-series store (`InflationItems/prices.db`)
- **Svelte 5 / SvelteKit** — production frontend (static SPA, adapter-static)
- **Apache ECharts** — canvas charts (line, area, bar)
- **Fira Sans / Fira Code** — Swiss minimal design system
- **Streamlit** — legacy dashboard frontend
- **waitress / gunicorn / granian** — WSGI servers
- **Web Scraping**: requests, BeautifulSoup, SeleniumBase, selenium + undetected-chromedriver, Camoufox, cloudscraper, curl-cffi
- **Data Storage**: CSV, JSON, SQLite formats
- **ML Stack**: scikit-learn, xgboost, lightgbm, catboost

---

## Main Components

### Dashboard
- `frontend/` — Svelte 5 / SvelteKit production dashboard (static SPA)
- `frontend/src/lib/api/client.ts` — typed Falcon API client (`$lib/api`)
- `frontend/src/lib/types/api.ts` — TypeScript contract matching `docs/FALCON_API_CONTRACT.md`
- `streamlit_app.py` — legacy Streamlit frontend (admin use)
- `inflation_dashboard/frontend/api_client.py` — legacy Python API client
- `inflation_dashboard/api/falcon_app.py` — Falcon WSGI app factory (CORS middleware)
- `inflation_dashboard/api/resources.py` — API endpoint implementations
- `inflation_dashboard/api/filters.py` — TTL-cached filter parsing, SQLite/CSV routing
- `inflation_dashboard/api/serialization.py` — JSON-safe envelope serialization
- `inflation_dashboard/application/use_cases.py` — dashboard data aggregation functions
- `inflation_dashboard/adapters/sqlite_price_repository.py` — SQLite data loading adapter
- `inflation_dashboard/adapters/csv_price_repository.py` — CSV fallback data loading adapter
- `inflation_dashboard/domain/prices.py` — price normalization and parsing

### Scrapers
- `InflationItems/Codes/HomeGoods/scraper.py` - HomeGoods category-based scraper (analytics-payload name extraction)
- `InflationItems/Codes/Cosmetics/Watson/scraper.py` - Watsons cosmetics scraper (serialised `curl_cffi`, full pagination)
- `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` - Vakko fashion items (live sitemap + cookie factory)
- `InflationItems/Codes/Technology/scraper.py` - Beymen tech products (dynamic pagination)
- `InflationItems/Codes/ConstructionMarkets/tasciyapimarket/scraper.py` - TasciYapi construction supplies
- `InflationItems/Codes/ConstructionMarkets/yapimaks/scraper.py` - Yapımaks construction supplies
- `InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py` - Gurmar supermarket products
- `InflationItems/Codes/HousesRent/KayseriSivasTokat/main.py` - Sarı site rentals (Kayseri/Sivas/Tokat; friend-tactics selenium engine — see `docs/APPROACH.md` first)
- `InflationItems/Codes/HousesRent/Emlakjet/scraper.py` - Emlakjet Turkey residential rentals (browser-backed; see `InflationItems/Codes/HousesRent/README.md`)

### Verification Scripts
- `scripts/verify_falcon_api.py` — API import boundaries, route contracts, endpoint smoke
- `scripts/verify_streamlit_api_frontend.py` — legacy Streamlit API client and tab wiring
- `scripts/verify_full_stack.py` — combined full-stack smoke test (recommended)
- `scripts/build_sqlite_from_json.py` — rebuild `prices.db` from JSON time series (~18 s)
- `scripts/benchmark_concurrent_api.py` — concurrency load testing

---

## Usage

### Collecting Data

```bash
# Scrape cosmetics data
python InflationItems/Codes/Cosmetics/Watson/scraper.py

# Scrape existing Sarı site rental properties (Kayseri, Sivas, Tokat)
python InflationItems/Codes/HousesRent/KayseriSivasTokat/main.py

# Scrape regular residential rental listings in Turkey
python -m InflationItems.Codes.HousesRent.Emlakjet.scraper

# Scrape market products
python InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py
```

### Calculating Inflation

```bash
# Calculate cosmetics inflation
python Inflations/Codes/Cosmetics/inflation.py --date 2026-03-15

# Calculate housing rental inflation
python Inflations/Codes/HousesRent/sahibinden_inflation.py --date 2026-03-15

# Calculate market inflation
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -i InflationItems/Datas/Markets/Gurmar/gurmar_prices_2026-02-24.csv
```

### Running the Dashboard

```bash
# Terminal 1: Start API server
uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app

# Terminal 2: Start the production Svelte dashboard
cd frontend && npm run dev

# Terminal 2 (alternative): legacy Streamlit dashboard
uv run streamlit run streamlit_app.py
```

---

## Documentation

- `docs/USER_GUIDE.md` — End-user dashboard walkthrough (Svelte frontend) with tabs, filters, and search tips
- `docs/FALCON_API_CONTRACT.md` — **Canonical** Falcon REST API spec with TypeScript interfaces for the Svelte frontend
- `docs/API.md` — Quick Falcon API endpoint reference (paraphrases the canonical contract)
- `docs/GETTING-STARTED.md` — Setup guide for developers
- `docs/ARCHITECTURE.md` — System architecture and data flow
- `docs/DEVELOPMENT.md` — Development conventions and commands
- `docs/TESTING.md` — Verification scripts, frontend checks, and test documentation
- `docs/CONFIGURATION.md` — Environment variables and defaults (incl. `FALCON_CORS_ORIGINS`, `VITE_API_BASE_URL`)
- `docs/APPROACH.md` — **Recommended data-acquisition flow** for the rental scraper
- `docs/TECH-STACK-SEARCH.md` — Tech-stack & skill search registry: tool catalog, install set, integration blueprint
- `docs/RESEARCH-PROMPT.md` + `docs/RESEARCH-REPORT-2026-08-16.md` — Deep-research validation of the scraping approach
- `docs/scraping-wiki/` — Local snapshot of TheWebScrapingClub knowledge base (anti-bot technique truth)

---

## Data Format

### Raw Data (InflationItems/Datas/)
CSV files with timestamps containing product name/ID, price, category (where the source provides one), and collection date:

Example: `Datas/Cosmetics/Watson/watsons_30-05-2026.csv`

> **Note on “Uncategorized”**: some sources (Gurmar, HomeGoods) write CSVs without
> a category column, so the pipeline labels those products `Uncategorized`. The
> Svelte dashboard blanks this meaningless label (`—`) in product tables. Sources
> that provide categories (e.g. Vakko: Kadin/Erkek/Shoes_Bags) display them.

### Processed Data (Inflations/Datas/)
Inflation outputs including basic inflation per product (%), average inflation rate, basket-level price index changes, and TUIK-weighted inflation metrics.

---

## TUIK Integration

The repository includes TUIK-style category mappings and weights used by several inflation calculators:
- **TUIK Codes**: tracked config files define commodity groups including codes 01-13
- **Base Year**: several category config files document 2026 CPI weights with base year 2025 = 100
- **Weight Distribution**: Reflects actual consumer spending patterns

---

## Methodology

1. **Data Collection**: Scraper scripts fetch price data when run manually or by external automation
2. **Data Cleaning**: Remove duplicates, normalize prices, handle missing values
3. **Outlier Detection**: IQR-based filtering for data quality assurance
4. **Aggregation**: Group by category/district/segment
5. **Inflation Calculation**: Compute YoY/MoM changes weighted by TUIK standards
6. **Analysis**: Time-series trends and comparative inflation across categories

---

## Dependencies

All Python dependencies are declared in `pyproject.toml`; the frontend uses npm
(`frontend/package.json`). Key packages:

| Category | Packages |
|---|---|
| **API Backend** | `falcon`, `orjson`, `waitress` |
| **Svelte Frontend** | `svelte` 5, `@sveltejs/kit` (adapter-static), `echarts` |
| **Legacy Dashboard** | `streamlit`, `plotly` |
| **Data Processing** | `pandas`, `numpy` |
| **Machine Learning** | `scikit-learn`, `xgboost`, `lightgbm`, `catboost` |
| **Web Scraping** | `requests`, `beautifulsoup4`, `seleniumbase`, `selenium`, `undetected-chromedriver`, `camoufox`, `cloudscraper`, `curl-cffi` |
| **Notebooks** | `jupyter`, `ipykernel`, `notebook` |

Install with `uv sync` (Python) and `cd frontend && npm install` (frontend).

---

## Contact

For questions, suggestions, or collaborations:

📧 **Email**: vinni@disroot.org

---

## License

This project is a personal research mirror for inflation study purposes.

---

*Last Updated: September 2026*
