---
last_mapped: 2026-09-02
focus: structure
---

# Structure

## Top-level layout

- `InflationItems/` — parent container for raw scraper ingestion and data artifacts.
  - `InflationItems/Codes/` — source scrapers grouped by domain and retailer/service.
  - `Inflations/Codes/` — inflation calculation scripts grouped by domain and retailer/service.
- `Inflations/Datas/` — processed inflation detail and summary CSV outputs.
- `logs/` — runtime logs, especially Yapimaks daily logs.
- `.github/workflows/` — GitHub Actions automation for scheduled scrapes.
- `inflation_dashboard/` — domain, adapters (SQLite + CSV repositories), use cases, Falcon REST API.
- `frontend/` — **Svelte 5 / SvelteKit production dashboard** (static SPA, Apache ECharts) consuming the Falcon API over HTTP; see `frontend/README.md` and `docs/FALCON_API_CONTRACT.md`.
- `inflation_dashboard/frontend/` — legacy Python API client used by the Streamlit app.
- `streamlit_app.py` — root-level legacy Streamlit dashboard consuming the Falcon API.
- `InflationItems/prices_json/` — clean partitioned JSON time series per retailer.
- `InflationItems/prices.db` — SQLite WAL database (built from JSON/CSV; gitignored).
- `scripts/` — DB build/migrate, benchmarks, and verification scripts.
- `docs/` — comprehensive technical documentation, architecture, and scraping knowledge base.
- `requirements.txt` and `pyproject.toml` — Python dependency/project metadata (`frontend/package.json` for the Svelte app).

## Scraper examples

- `InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py` writes raw Gurmar market prices.
- `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` writes raw Vakko clothing prices.
- `InflationItems/Codes/ConstructionMarkets/yapimaks/scraper.py` writes raw Yapimaks construction market prices.
- `InflationItems/Codes/HousesRent/KayseriSivasTokat/` contains a more complex async/browser scraper with `main.py`, `scraper.py`, `config.py`, and checkpoints.

## Inflation examples

- `Inflations/Codes/Markets/Gurmar/gurmar_inflation.py` handles flexible Gurmar CSV separators and category mapping.
- `Inflations/Codes/ClothingStores/Vakko/vakko_inflation.py` normalizes Vakko price strings and maps product names to TUIK categories.
- `Inflations/Codes/HousesRent/sahibinden_inflation.py` aggregates rent data by district and room count.
- TUIK category config lives beside calculators, e.g. `Inflations/Codes/Markets/Gurmar/gurmar_tuik_config.py`.

## Data naming patterns

- Gurmar raw: `InflationItems/Datas/Markets/Gurmar/gurmar_prices_YYYY-MM-DD.csv`.
- Vakko raw: `InflationItems/Datas/ClothingStores/Vakko/vakko_YYYY-MM-DD.csv`.
- Yapimaks raw: `InflationItems/Datas/ConstructionSuppliesMarkets/yapimaks/YYYY-MM-DD.csv`.
- HomeGoods raw: `InflationItems/Datas/HomeGoods/chakra_all_categories_YYYY_MM_DD.csv`.
- Inflation summaries: `Inflations/Datas/**/inflation_summary.csv` or city-specific summaries.

## Naming conventions

- Many scripts use Turkish variable names and comments.
- Data columns vary by source: `product-name`, `product-price`, `shown_price`, `Price`, `median_price`, `Stok Kodu`, and source-specific categories.
- Date parsing is filename-driven across both calculators and dashboard code.

## Generated files

- CSV and log files are large and numerous; code should avoid scanning all of them unless necessary.
- The API (and the Svelte/Streamlit clients) cap loaded files by retailer/date to keep app startup manageable.
- The Svelte dashboard blanks the pipeline's `Uncategorized` fill-in label (`—`) in product tables (see root `README.md`).
