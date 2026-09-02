---
last_mapped: 2026-07-16
focus: architecture
---

# Architecture

## High-level pattern

The repository is a data collection and analysis mirror with three main layers:

1. Scrapers under `InflationItems/Codes/` collect raw retailer/service prices.
2. Inflation calculators under `Inflations/Codes/` normalize raw CSVs and compute per-product and summary inflation metrics.
3. Data artifacts under `InflationItems/Datas/` and `Inflations/Datas/` store raw and processed time-series CSV files.

A newer presentation layer exists in `streamlit_app.py`, which reads raw `InflationItems/Datas/` CSV files and builds an interactive dashboard.

## Data flow

- Source websites/APIs are scraped by scripts such as `InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py` and `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py`.
- Raw daily CSVs are stored with date-bearing filenames, for example `InflationItems/Datas/Markets/Gurmar/gurmar_prices_2026-07-16.csv`.
- Inflation calculators derive date from filenames and compare current files with previous intervals; see `Inflations/Codes/Markets/Gurmar/gurmar_inflation.py`.
- Detailed inflation CSVs and `inflation_summary.csv` files are written under `Inflations/Datas/...`.
- `streamlit_app.py` scans `InflationItems/Datas/**/*.csv`, detects retailer names from paths, parses dates from filenames, normalizes prices, and displays charts.

## Entry points

- Dashboard: `streamlit_app.py` with `streamlit run streamlit_app.py`.
- Gurmar scraper: `InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py`.
- Gurmar inflation: `Inflations/Codes/Markets/Gurmar/gurmar_inflation.py`.
- Vakko scraper: `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py`.
- Vakko inflation: `Inflations/Codes/ClothingStores/Vakko/vakko_inflation.py`.
- Houses rent scraper: `InflationItems/Codes/HousesRent/KayseriSivasTokat/main.py` and `InflationItems/Codes/HousesRent/KayseriSivasTokat/scraper.py`.
- Yapimaks scraper: `InflationItems/Codes/ConstructionMarkets/yapimaks/scraper.py`.

## Boundaries

- `InflationItems/Codes/` scripts are source-specific ingestion jobs.
- `Inflations/Codes/` scripts are source-specific transformation and metric jobs.
- `InflationItems/Datas/` and `Inflations/Datas/` are data stores, not application code.
- `streamlit_app.py` is currently a monolithic dashboard module containing loading, normalization, search helpers, and UI rendering.

## State and persistence

- Persistence is file-based CSV storage.
- There is no database layer.
- There is no API/backend service layer.
- Long-lived operational state appears in checkpoint files under `InflationItems/Codes/HousesRent/KayseriSivasTokat/checkpoints/` and in generated CSV/log files.
