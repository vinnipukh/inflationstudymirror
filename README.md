# Inflation Study Mirror

<!-- generated-by: gsd-doc-writer -->

A comprehensive data collection and inflation analysis project tracking price changes across Turkish retailers and services over time.

This project includes my personal contributions to https://github.com/urazkagangunes/InflationResearchStudy

## Overview

This project scrapes product and service price data from various Turkish retailers, markets, and platforms, then processes the data to calculate inflation metrics. The repository focuses on real-time price monitoring and inflation analysis using TÜİK-style weighting standards.

## Dashboard Quick Start

The dashboard uses a **two-process architecture**: a Falcon API backend serves data, and a Streamlit frontend displays it.

```bash
# 1. Install dependencies
uv sync

# 2. Start the API server (Terminal 1)
uv run waitress-serve --port=8000 inflation_dashboard.api.falcon_app:create_app

# 3. Start the dashboard (Terminal 2)
uv run streamlit run streamlit_app.py
```

Then open your browser to the Streamlit URL (default `http://localhost:5000`).

## Verification

Run the combined smoke test to verify the stack:

```bash
uv run python scripts/verify_full_stack.py
```

See `docs/TESTING.md` for detailed test documentation.

## Project Structure

```
inflationstudymirror/
├── Codes/                          # Web scrapers for different retailers
│   ├── HomeGoods/                 # HomeGoods product scraper
│   ├── Cosmetics/                 # Cosmetics stores (Watson, etc.)
│   ├── ClothingStores/            # Clothing retailers (Vakko, etc.)
│   ├── HousesRent/                # Rental property data collection
│   └── Markets/                   # Marketplace scrapers (Gurmar, etc.)
├── Datas/                         # Raw collected data
├── Inflations/                    # Inflation calculation outputs
├── inflation_dashboard/           # Dashboard & API package
│   ├── domain/                    # Parsing and normalization
│   ├── adapters/                  # CSV storage adapter
│   ├── application/               # Use cases and chart specs
│   ├── api/                       # Falcon API (filters, resources, serialization)
│   └── frontend/                  # Streamlit API client
├── scripts/                       # Verification scripts
├── docs/                          # Documentation
├── streamlit_app.py               # Dashboard entry point
└── pyproject.toml                 # Project metadata and dependencies
```

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
- **Jupyter Notebooks** for analysis and exploration
- **Web Scraping**: requests, BeautifulSoup, SeleniumBase, Camoufox, cloudscraper, curl-cffi
- **Data Storage**: CSV, JSON formats

## Main Components

### Dashboard
- `streamlit_app.py` — Streamlit frontend consuming the Falcon API
- `inflation_dashboard/frontend/api_client.py` — HTTP API client with envelope validation
- `inflation_dashboard/api/falcon_app.py` — Falcon WSGI app factory
- `inflation_dashboard/api/resources.py` — API endpoint implementations
- `inflation_dashboard/application/use_cases.py` — Dashboard data aggregation functions
- `inflation_dashboard/domain/prices.py` — Price normalization and parsing
- `inflation_dashboard/adapters/csv_price_repository.py` — CSV data loading adapter

### Scrapers
- `Codes/HomeGoods/scraper.py` - HomeGoods category-based scraper with retry logic
- `Codes/Cosmetics/Watson/debugscraper.py` - Watson cosmetics product scraper
- `Codes/ClothingStores/Vakko/vakko_master_scraper.py` - Vakko fashion items
- `Codes/HousesRent/KayseriSivasTokat/main.py` - Rental property data collection
- `Codes/Markets/Gurmar/gurmar_scraper.py` - Gurmar supermarket products

### Inflation Calculators
- `Inflations/Codes/Cosmetics/inflation.py` - Cosmetics inflation metrics
- `Inflations/Codes/Technology/tuik_config.py` - TUIK weights configuration
- `Inflations/Codes/HousesRent/sahibinden_inflation.py` - Rental market inflation
- `Inflations/Codes/Markets/Gurmar/gurmar_inflation.py` - Market basket inflation

### Verification Scripts
- `scripts/verify_falcon_api.py` — API import boundaries, route contracts, endpoint smoke
- `scripts/verify_streamlit_api_frontend.py` — Frontend API client and tab wiring
- `scripts/verify_full_stack.py` — Combined full-stack smoke test (recommended)

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

## Documentation

- `docs/USER_GUIDE.md` — End-user dashboard walkthrough
- `docs/GETTING-STARTED.md` — Setup guide for developers
- `docs/ARCHITECTURE.md` — System architecture and data flow
- `docs/API.md` — Falcon API endpoint reference
- `docs/DEVELOPMENT.md` — Development conventions and commands
- `docs/TESTING.md` — Verification scripts and test documentation
- `docs/CONFIGURATION.md` — Environment variables and defaults

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

## TUIK Integration

The repository includes TUIK-style category mappings and weights used by several inflation calculators:
- **TUIK Codes**: tracked config files define commodity groups including codes 01-13
- **Base Year**: several category config files document 2026 CPI weights with base year 2025 = 100
- **Weight Distribution**: Reflects actual consumer spending patterns

## Methodology

1. **Data Collection**: Scraper scripts fetch price data when run manually or by external automation
2. **Data Cleaning**: Remove duplicates, normalize prices, handle missing values
3. **Outlier Detection**: IQR-based filtering for data quality assurance
4. **Aggregation**: Group by category/district/segment
5. **Inflation Calculation**: Compute YoY/MoM changes weighted by TUIK standards
6. **Analysis**: Time-series trends and comparative inflation across categories

## Requirements

- Python `>=3.14`
- `uv` for dependency management

Install all dependencies:

```bash
uv sync
```

## Output Examples

The project generates inflation and price-analysis outputs including:
- Daily price movement summaries
- Category-level inflation breakdown
- Cross-store price comparisons
- Outlier and data quality reports

## Contact

For questions, suggestions, or collaborations:

📧 **Email**: vinni@disroot.org

## License

This project is a personal research mirror for inflation study purposes.

---

*Last Updated: July 2026*
