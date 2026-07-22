# Inflation Study Mirror

<!-- generated-by: gsd-doc-writer -->

A comprehensive data collection and inflation analysis project tracking price changes across Turkish retailers and services over time, **powered by a high-performance Falcon REST API and an interactive Streamlit dashboard with smart search, caching, and ML-ready infrastructure.**

This project includes my personal contributions to https://github.com/urazkagangunes/InflationResearchStudy

---

## Installation

### Prerequisites

- **Python** `>=3.14` (declared in `pyproject.toml`)
- **uv** — fast Python package installer and resolver
- **Git** (to clone the repository)

### Clone and Install

```bash
git clone <repository-url>
cd inflationstudymirror
uv sync
```

This installs everything: the Falcon API server, Streamlit dashboard, Plotly charts, pandas, ML libraries (scikit-learn, xgboost, lightgbm, catboost), and all scraping dependencies.

### Quick Start

Once installed, start the dashboard stack in two terminals:

```bash
# Terminal 1: Start the Falcon API backend
uv run waitress-serve --port=8000 inflation_dashboard.api.falcon_app:create_app

# Terminal 2: Start the Streamlit dashboard frontend
uv run streamlit run streamlit_app.py
```

Open `http://localhost:5000` in your browser.

### Verify the Installation

Run the combined full-stack smoke test to confirm everything is wired correctly:

```bash
uv run python scripts/verify_full_stack.py
```

Expected output includes `PASS` across all checks: API imports, route contracts, endpoint smoke tests, frontend client, and end-to-end integration.

---

## Overview

This project scrapes product and service price data from various Turkish retailers, markets, and platforms, then processes the data to calculate inflation metrics. The repository focuses on real-time price monitoring and inflation analysis using TÜİK-style weighting standards.

The **dashboard stack** consists of a **Falcon REST API** (high-performance WSGI backend) that serves CSV-backed data, and a **Streamlit frontend** with **four interactive tabs**, smart autocorrect search, TTL-based performance caching, and production-quality infrastructure.

---

## Project Structure

```
inflationstudymirror/
├── Codes/                          # Web scrapers for different retailers
│   ├── HomeGoods/                 # HomeGoods product scraper
│   ├── Cosmetics/                 # Cosmetics stores (Watson, etc.)
│   ├── ClothingStores/            # Clothing retailers (Vakko, etc.)
│   ├── HousesRent/                # Rental property data collection
│   └── Markets/                   # Marketplace scrapers (Gurmar, etc.)
├── Datas/                         # Raw collected data (CSV files)
├── Inflations/                    # Inflation calculation outputs
├── inflation_dashboard/           # Dashboard & API package
│   ├── domain/                    # Parsing and normalization
│   ├── adapters/                  # CSV storage adapter
│   ├── application/               # Use cases and chart specs
│   ├── api/                       # Falcon API (resources, filters, serialization)
│   └── frontend/                  # Streamlit API client
├── forecasting/                   # ML-based price trend prediction
├── scripts/                       # Verification scripts
├── docs/                          # Documentation
├── streamlit_app.py               # Dashboard entry point
└── pyproject.toml                 # Project metadata and dependencies
```

---

## Flashy Features 🚀

### Smart Autocorrect Search 🔍

Type partial or misspelled product/retailer names — the dashboard intelligently ranks suggestions using:
- **Unicode normalization** (NFKD) so Turkish characters (İ, ğ, ü, ş, ö, ç) match correctly
- **Starts-with** matches ranked first
- **Contains matches** ranked second
- **Fuzzy close matches** (difflib, cutoff 0.45) for typo-tolerant search
- A caption shows the closest match when it differs from your typed text

### Blazing-Fast TTL Caching ⚡

- **45-second history cache** (32 entries max) — deduplicates CSV reads across all four tabs so only the first request per filter combo hits disk
- **60-second inventory cache** — available retailers and date ranges are cached with TTL expiry
- **Subsequent tab switches with the same filters return in ~5ms**
- First load per filter combo takes ~280ms as CSV data is read from disk

### 6 Production-Ready REST API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service health & metadata |
| `GET /api/inventory` | Available retailers, date range, file count |
| `GET /api/history` | Price history, filterable by product & retailer |
| `GET /api/retailer-averages` | Average/Median price trends per retailer |
| `GET /api/movers` | Biggest price drops and gains |
| `GET /api/coverage` | Dataset coverage summary, trends, category breakdown & diagnostics |

All endpoints return a stable `{data, meta, errors}` JSON envelope with proper pandas/numpy/date serialization.

### 4 Interactive Dashboard Tabs

| Tab | What It Shows |
|---|---|
| **Product Explorer** | Price chart, latest price, cheapest price+date, % change since first observation |
| **Retailer Averages** | Compare mean or median prices across selected retailers over time |
| **Price Movers** | Biggest drops vs. peak price & biggest gains since first observation |
| **Coverage Overview** | Total products/observations, tracked products per day, category breakdown, skipped file diagnostics |

### Flexible Filtering System

- **Multi-retailer selection** — pick any subset of available stores
- **Date range picker** — defaults to last 60 days
- **Max CSV files per retailer** — slider from 10–160 files (default 25)
- **Load all files** — checkbox to bypass the file cap when you need the full picture
- All filters sync across tabs via the API

### ML-Ready Infrastructure 🧠

- **Forecasting module** (`forecasting/`) — Jupyter notebook for ML-based price trend prediction
- Pre-installed ML stack: **scikit-learn, xgboost, lightgbm, catboost**
- In-dashboard price prediction toggle (sidebar) — ready for ML model integration
- Sits alongside scrape-and-analyze pipeline for AI-powered inflation forecasting

### Robust API Envelope Pattern

Every endpoint returns:
```json
{
  "data": { ... },           // Payload (JSON-safe, no NaN/NaT)
  "meta": { ... },           // Metadata (filters, warnings, file counts)
  "errors": []               // Errors array (empty on success)
}
```

With comprehensive error handling — invalid filters return HTTP 400 with descriptive error codes and metadata.

### Full-Stack Smoke Tests ✅

```bash
uv run python scripts/verify_full_stack.py
```

Validates every layer in a single command: import boundaries, route contracts, endpoint responses, frontend API client, and end-to-end integration with Falcon's TestClient.

---

## Dashboard Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. Start the API server (Terminal 1)
uv run waitress-serve --port=8000 inflation_dashboard.api.falcon_app:create_app

# 3. Start the dashboard (Terminal 2)
uv run streamlit run streamlit_app.py
```

Then open your browser to the Streamlit URL (default `http://localhost:5000`).

---

## Key Features

### Data Collection
- **Multi-store scraping**: Automated data collection from diverse Turkish retailers including:
  - Cosmetics: Watson
  - Clothing: Vakko
  - Real Estate: Rental property data from Sarı site
  - Markets: Grocery items from Gurmar
  - Electronics: Beymen Tech products

### Dashboard (3-Phase Architecture)
- **Phase 1 ✓**: Hexagonal core extraction — framework-independent domain and application modules
- **Phase 2 ✓**: Falcon API backend — six REST endpoints with JSON envelopes and bounded CSV loading
- **Phase 3 ✓**: Streamlit API frontend — all four dashboard tabs read from Falcon API
- **Phase 4 ✓**: Deployment documentation, combined smoke tests, and dependency management

### Inflation Analysis
- **TUIK-style metrics**: Several inflation calculators use tracked TUIK-style category mappings and weights
- **Category mapping**: Product categories mapped to tracked TUIK-style code groups
- **Time-series analysis**: Track inflation trends over days/months
- **Statistical validation**: Outlier detection and data quality filtering

### Key Technologies
- **Python 3.x** for scrapers, calculators, and dashboard
- **Falcon** — high-performance Python web framework for the API backend
- **Streamlit** — dashboard frontend framework
- **Plotly** — interactive charts
- **waitress** — production-quality WSGI server
- **Jupyter Notebooks** for analysis and exploration
- **Web Scraping**: requests, BeautifulSoup, SeleniumBase, Camoufox, cloudscraper, curl-cffi
- **Data Storage**: CSV, JSON formats
- **ML Stack**: scikit-learn, xgboost, lightgbm, catboost

---

## Main Components

### Dashboard
- `streamlit_app.py` — Streamlit frontend consuming the Falcon API
- `inflation_dashboard/frontend/api_client.py` — HTTP API client with envelope validation
- `inflation_dashboard/api/falcon_app.py` — Falcon WSGI app factory
- `inflation_dashboard/api/resources.py` — API endpoint implementations
- `inflation_dashboard/api/filters.py` — TTL-cached filter parsing and CSV loading
- `inflation_dashboard/api/serialization.py` — JSON-safe envelope serialization
- `inflation_dashboard/application/use_cases.py` — Dashboard data aggregation functions
- `inflation_dashboard/application/chart_specs.py` — Declarative chart configuration
- `inflation_dashboard/domain/prices.py` — Price normalization and parsing
- `inflation_dashboard/adapters/csv_price_repository.py` — CSV data loading adapter

### Scrapers
- `Codes/HomeGoods/scraper.py` - HomeGoods category-based scraper with retry logic
- `Codes/Cosmetics/Watson/debugscraper.py` - Watson cosmetics product scraper
- `Codes/ClothingStores/Vakko/vakko_master_scraper.py` - Vakko fashion items
- `Codes/HousesRent/KayseriSivasTokat/main.py` - Rental property data collection
- `Codes/Markets/Gurmar/gurmar_scraper.py` - Gurmar supermarket products

### Forecasting
- `forecasting/forecastingtest.ipynb` — ML-based price trend prediction notebook

### Verification Scripts
- `scripts/verify_falcon_api.py` — API import boundaries, route contracts, endpoint smoke
- `scripts/verify_streamlit_api_frontend.py` — Frontend API client and tab wiring
- `scripts/verify_full_stack.py` — Combined full-stack smoke test (recommended)

---

## Usage

### Collecting Data

```bash
# Scrape cosmetics data
python Codes/Cosmetics/Watson/debugscraper.py

# Scrape rental properties (Kayseri, Sivas, Tokat)
python Codes/HousesRent/KayseriSivasTokat/main.py

# Scrape market products
python Codes/Markets/Gurmar/gurmar_scraper.py
```

### Calculating Inflation

```bash
# Calculate cosmetics inflation
python Inflations/Codes/Cosmetics/inflation.py --date 2026-03-15

# Calculate housing rental inflation
python Inflations/Codes/HousesRent/sahibinden_inflation.py --date 2026-03-15

# Calculate market inflation
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -i Datas/Markets/Gurmar/gurmar_prices_2026-02-24.csv
```

### Running the Dashboard

```bash
# Terminal 1: Start API server
uv run waitress-serve --port=8000 inflation_dashboard.api.falcon_app:create_app

# Terminal 2: Start dashboard frontend
uv run streamlit run streamlit_app.py
```

---

## Documentation

- `docs/USER_GUIDE.md` — End-user dashboard walkthrough with tabs, filters, and search tips
- `docs/GETTING-STARTED.md` — Setup guide for developers
- `docs/ARCHITECTURE.md` — System architecture and data flow
- `docs/API.md` — Falcon API endpoint reference
- `docs/DEVELOPMENT.md` — Development conventions and commands
- `docs/TESTING.md` — Verification scripts and test documentation
- `docs/CONFIGURATION.md` — Environment variables and defaults

---

## Data Format

### Raw Data (Datas/)
CSV files with timestamps containing:
- Product name/ID
- Product price
- Category classification
- Collection date

Example: `Datas/Cosmetics/Watson/watsons_30-05-2026.csv`

### Processed Data (Inflations/Datas/)
Inflation outputs including:
- Basic inflation per product (%)
- Average inflation rate
- Basket-level price index changes
- TUIK-weighted inflation metrics

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

## Output Examples

The project generates inflation and price-analysis outputs including:
- Daily price movement summaries
- Category-level inflation breakdown
- Cross-store price comparisons
- Outlier and data quality reports

---

## Dependencies

All dependencies are declared in `pyproject.toml`. Key packages:

| Category | Packages |
|---|---|
| **API Backend** | `falcon`, `waitress` |
| **Dashboard Frontend** | `streamlit`, `plotly` |
| **Data Processing** | `pandas`, `numpy` |
| **Machine Learning** | `scikit-learn`, `xgboost`, `lightgbm`, `catboost` |
| **Web Scraping** | `requests`, `beautifulsoup4`, `seleniumbase`, `camoufox`, `cloudscraper`, `curl-cffi` |
| **Notebooks** | `jupyter`, `ipykernel`, `notebook` |

Install all at once:
```bash
uv sync
```

---

## Contact

For questions, suggestions, or collaborations:

📧 **Email**: vinni@disroot.org

---

## License

This project is a personal research mirror for inflation study purposes.

---

*Last Updated: July 2026*
