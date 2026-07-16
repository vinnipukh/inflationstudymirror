# Inflation Study Mirror

A comprehensive data collection and inflation analysis project tracking price changes across Turkish retailers and services over time.

This project includes my personal contributions to https://github.com/urazkagangunes/InflationResearchStudy 

## Overview

This project scrapes product and service price data from various Turkish retailers, markets, and platforms, then processes the data to calculate inflation metrics. The repository focuses on real-time price monitoring and inflation analysis using TÜİK-style weighting standards.

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
│   ├── Cosmetics/
│   ├── ClothingStores/
│   ├── HousesRent/
│   └── Markets/
└── Inflations/                    # Inflation calculation outputs
    ├── Codes/                     # Inflation computation scripts
    └── Datas/                     # Processed inflation results
```

## Key Features

### Data Collection
- **Multi-store scraping**: Automated data collection from diverse Turkish retailers including:
  - Cosmetics: Watson
  - Clothing: Vakko
  - Real Estate: Rental property data from Sarı site
  - Markets: Grocery items from Gurmar
  - Electronics: Beymen Tech products

### Inflation Analysis
- **TUIK-style metrics**: Several inflation calculators use tracked TUIK-style category mappings and weights
- **Category mapping**: Product categories mapped to tracked TUIK-style code groups
- **Time-series analysis**: Track inflation trends over days/months
- **Statistical validation**: Outlier detection and data quality filtering

### Key Technologies
- **Python 3.x** for scrapers, calculators, dashboard logic, and the Falcon API
- **Jupyter Notebooks** for analysis and exploration
- **Data Processing**: pandas-based CSV processing in dashboard/API paths
- **Web Scraping**: requests, BeautifulSoup, SeleniumBase, Camoufox, cloudscraper, curl-cffi
- **Data Storage**: CSV, JSON formats

## Main Components

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

### Data Processing
- CSV consolidation scripts with date-based file handling
- Outlier detection and filtering using IQR methodology
- Price normalization and quality validation
- Temporal data aggregation and analysis

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
- **Categories Tracked**:
  - 01: Food & non-alcoholic beverages
  - 03: Clothing & footwear
  - 04: Housing, water, electricity, gas
  - 05: Furniture & home appliances
  - 08: Information & communication
  - And more...

## Methodology

1. **Data Collection**: Scraper scripts fetch price data when run manually or by external automation
2. **Data Cleaning**: Remove duplicates, normalize prices, handle missing values
3. **Outlier Detection**: IQR-based filtering for data quality assurance
4. **Aggregation**: Group by category/district/segment
5. **Inflation Calculation**: Compute YoY/MoM changes weighted by TUIK standards
6. **Analysis**: Time-series trends and comparative inflation across categories

## Requirements

- Python `>=3.14` for the minimal `pyproject.toml` / `uv` workflow
- `falcon` for the API backend
- `requests`, `beautifulsoup4`, SeleniumBase, Camoufox, cloudscraper, curl-cffi, and python-dotenv for scraper workflows listed in `requirements.txt`
- pandas, Streamlit, and Plotly for the current dashboard path

Install dependencies:
```bash
uv sync
python -m pip install -r requirements.txt
python -m pip install pandas streamlit plotly
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

## Installation

The repository is Python-based. The minimal `uv` project metadata in `pyproject.toml` declares Falcon for the API backend, while `requirements.txt` tracks the broader scraper-oriented dependency list.

```bash
python -m pip install -r requirements.txt
python -m pip install pandas streamlit plotly
```

`Codes/ClothingStores/Vakko/vakko_master_scraper.py` also reads `VAKKO_COOKIE` and `VAKKO_USER_AGENT` from the environment through `python-dotenv`.

## Quick Start

1. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   python -m pip install pandas streamlit plotly
   ```

2. Run a bounded dashboard locally:

   ```bash
   streamlit run streamlit_app.py
   ```

3. Run an individual scraper or inflation calculator when you want to refresh a specific dataset:

   ```bash
   python Codes/Markets/Gurmar/gurmar_scraper.py
   python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h
   ```

## Usage Examples

### Launch the current dashboard

```bash
streamlit run streamlit_app.py
```

The dashboard reads tracked CSV files from `Datas/`, builds a lazy inventory, and exposes product history, retailer averages, price movers, and coverage views.

### Scrape Gurmar prices

```bash
python Codes/Markets/Gurmar/gurmar_scraper.py
```

This writes daily Gurmar CSV files under `Datas/Markets/Gurmar/`.

### Calculate Gurmar inflation

```bash
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -i Datas/Markets/Gurmar/gurmar_prices_2026-02-24.csv
```

Use `-h` on calculator scripts to inspect their supported arguments.

<!-- generated-by: gsd-doc-writer -->
## Falcon API Backend

The repository also includes a Falcon WSGI API over the same CSV-backed dashboard core. The app factory is `inflation_dashboard.api.falcon_app:create_app`, and all responses use a stable JSON envelope:

```json
{"data": {}, "meta": {}, "errors": []}
```

Registered endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Lightweight service health check; does not load CSV history. |
| `GET /api/inventory` | Lists available retailers plus minimum and maximum discovered data dates. |
| `GET /api/history` | Returns normalized price history, or a single product history when `product_name` is provided. |
| `GET /api/retailer-averages` | Returns average or median price trends by date and retailer. |
| `GET /api/movers` | Returns biggest price drops and gains for repeated product observations. |
| `GET /api/coverage` | Returns dataset coverage summary, coverage-over-time rows, category coverage, and skipped-file diagnostics. |

Common query parameters for data endpoints:

- `retailer`: repeatable retailer filter, for example `retailer=Markets%20/%20Gurmar`.
- `start_date` / `end_date`: ISO dates (`YYYY-MM-DD`). Defaults to the latest 60-day window discovered in `Datas/`.
- `max_files`: maximum CSV files per retailer to load. Use `0` only when you intentionally want uncapped history.
- `all_history`: boolean shortcut for uncapped history; may be slow on large tracked datasets.

Endpoint-specific parameters:

- `/api/history`: `product_name` and, when multiple retailers are selected, `product_retailer`.
- `/api/retailer-averages`: `aggregation=Average` or `aggregation=Median`.
- `/api/movers`: `scope_retailer=All retailers` or a selected retailer, plus `limit` from 5 to 30.
- `/api/coverage`: `category_limit` for category coverage rows.

A bounded in-process smoke check is available and does not bind a port:

```bash
uv run python scripts/verify_falcon_api.py
```

For local serving, install Falcon plus the dashboard data dependencies (`pandas` and any WSGI server you choose), then point the server at `inflation_dashboard.api.falcon_app:create_app`.

## Additional Developer Documentation

- `docs/ARCHITECTURE.md` describes the scraper, CSV, dashboard, extracted core, and API boundaries.
- `docs/GETTING-STARTED.md` gives a short setup path for new contributors.
- `docs/DEVELOPMENT.md` covers local development conventions.
- `docs/TESTING.md` documents the current ad-hoc verification posture, including Falcon API smoke checks.
- `docs/CONFIGURATION.md` lists environment variables and configuration files discovered in the repository.

## Notes

- Review each target website's terms of service before running scraper scripts
- Several calculators use TUIK-style category mappings and weights
- Time-series data enables trend analysis
- Results reflect Turkish market dynamics and consumer behavior

---

*Last Updated: June 30, 2026*
