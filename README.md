# Inflation Study Mirror

A comprehensive data collection and inflation analysis project tracking price changes across Turkish retailers and services over time.

This project includes my personal contributions to https://github.com/urazkagangunes/InflationResearchStudy 

## Overview

This project scrapes product and service price data from various Turkish retailers, markets, and platforms, then processes the data to calculate inflation metrics. The repository focuses on real-time price monitoring and inflation analysis using Turkish Central Bank (TUIK) weighting standards.

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
  - Cosmetics: Watson, Migros, Bauhaus, Rossmann
  - Clothing: Vakko, and other apparel retailers
  - Real Estate: Rental property data from Sarı site
  - Markets: Grocery items from Gurmar and other supermarkets
  - Electronics: Samsung products

### Inflation Analysis
- **TUIK-weighted metrics**: All calculations follow Turkish Central Bank (TUIK) CPI basket methodology
- **Category mapping**: Product categories mapped to TUIK code groups (01-12)
- **Time-series analysis**: Track inflation trends over days/months
- **Statistical validation**: Outlier detection and data quality filtering

### Key Technologies
- **Python 3.x** (88% of codebase)
- **Jupyter Notebooks** (12% of codebase) for analysis and exploration
- **Data Processing**: pandas, numpy
- **Web Scraping**: requests, BeautifulSoup, selenium
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
- `Inflations/Codes/HousesRent/Sarı site_inflation.py` - Rental market inflation
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
python Inflations/Codes/HousesRent/Sarı site_inflation.py --city Kayseri --date 2026-03-15

# Calculate market inflation
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py --date 2026-03-15
```

## Data Format

### Raw Data (Datas/)
CSV files with timestamps containing:
- Product name/ID
- Product price
- Category classification
- Collection date

Example: `Datas/Cosmetics/Watson/watsons_30-03-2026.csv`

### Processed Data (Inflations/Datas/)
Inflation outputs including:
- Basic inflation per product (%)
- Average inflation rate
- Basket-level price index changes
- TUIK-weighted inflation metrics

## TUIK Integration

The project implements Turkish Central Bank's Consumer Price Index (TÜFE) methodology:
- **TUIK Codes**: 12 main commodity groups (01-12)
- **Base Year**: 2025 = 100
- **Weight Distribution**: Reflects actual consumer spending patterns
- **Categories Tracked**:
  - 01: Food & non-alcoholic beverages
  - 03: Clothing & footwear
  - 04: Housing, water, electricity, gas
  - 05: Furniture & home appliances
  - 08: Information & communication
  - And more...

## Methodology

1. **Data Collection**: Automated scrapers fetch price data on scheduled intervals
2. **Data Cleaning**: Remove duplicates, normalize prices, handle missing values
3. **Outlier Detection**: IQR-based filtering for data quality assurance
4. **Aggregation**: Group by category/district/segment
5. **Inflation Calculation**: Compute YoY/MoM changes weighted by TUIK standards
6. **Analysis**: Time-series trends and comparative inflation across categories

## Requirements

- Python 3.8+
- pandas
- requests
- beautifulsoup4
- selenium (for dynamic content)
- python-dotenv (for environment variables)

Install dependencies:
```bash
pip install pandas requests beautifulsoup4 selenium python-dotenv
```

## Output Examples

The project generates detailed inflation reports including:
- Daily price movement summaries
- Category-level inflation breakdown
- Cross-store price comparisons
- Statistical confidence intervals
- Outlier and data quality reports

## Contact

For questions, suggestions, or collaborations:

📧 **Email**: vinni@disroot.org

## License

This project is a personal research mirror for inflation study purposes.

## Installation

The repository is Python-based. The practical dependency list is tracked in `requirements.txt`; `pyproject.toml` is currently skeletal and does not list runtime dependencies.

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
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -i Datas/Markets/Gurmar/gurmar_2026-02-24.csv
```

Use `-h` on calculator scripts to inspect their supported arguments.

## Additional Developer Documentation

- `docs/ARCHITECTURE.md` describes the scraper, CSV, dashboard, and extracted core boundaries.
- `docs/GETTING-STARTED.md` gives a short setup path for new contributors.
- `docs/DEVELOPMENT.md` covers local development conventions.
- `docs/TESTING.md` documents the current ad-hoc verification posture.
- `docs/CONFIGURATION.md` lists environment variables and configuration files discovered in the repository.

## Notes

- Data collection respects website terms of service and robots.txt
- All calculations follow TUIK CPI official methodology
- Time-series data enables trend analysis and forecasting
- Results reflect Turkish market dynamics and consumer behavior

---

*Last Updated: June 30, 2026*
