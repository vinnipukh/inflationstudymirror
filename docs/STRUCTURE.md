# Repository Structure

## Top level

- `InflationItems/` — raw data acquisition and source datasets.
- `Inflations/` — inflation/hunger-threshold calculation code and outputs.
- `.github/workflows/` — scheduled scraper automation.
- `scripts/` — data-only utilities.
- `logs/` — operational scraper logs.
- `docs/` — data pipeline and scraper knowledge base.
- `SCRAPER_TIMETABLE.md` — workflow schedule.

## Scraper tree

`InflationItems/Codes/<Domain>/<Source>/`

Source directories own their scraper, parser/browser helpers, configuration, state handling and source-specific README where present.

Examples:

- `InflationItems/Codes/Markets/Gurmar/`
- `InflationItems/Codes/ClothingStores/Vakko/`
- `InflationItems/Codes/Technology/`
- `InflationItems/Codes/ConstructionMarkets/yapimaks/`
- `InflationItems/Codes/HousesRent/Emlakjet/`

## Data tree

`InflationItems/Datas/<Domain>/<Source>/`

- dated source snapshots;
- source checkpoints/state;
- catalog/series files for long-lived sources;
- source-specific README/methodology.

`InflationItems/prices_json/` is a generated publication layer and is ignored by Git by default.

## Inflation tree

`Inflations/Codes/<Domain>/<Calculator>/`

- calculator entrypoint;
- source/category mapping;
- calculator-specific configuration and README.

`Inflations/Datas/` contains generated summary/detail CSV outputs and methodology notes.

## Naming examples

- Gurmar raw: `InflationItems/Datas/Markets/Gurmar/gurmar_prices_YYYY-MM-DD.csv`
- Vakko raw: `InflationItems/Datas/ClothingStores/Vakko/vakko_YYYY-MM-DD.csv`
- Yapımaks raw: `InflationItems/Datas/ConstructionSuppliesMarkets/yapimaks/YYYY-MM-DD.csv`
- HomeGoods raw: `InflationItems/Datas/HomeGoods/chakra_all_categories_YYYY_MM_DD.csv`
- Emlakjet raw: `InflationItems/Datas/HousesRent/Emlakjet/YYYY-MM-DD.csv`

## Repository boundary

No `frontend/`, `inflation_dashboard/`, Falcon API, Svelte package or committed SQLite database belongs here. Those are maintained in `../inflationstudymirror-web`.
