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

- `InflationItems/Codes/01_Food/Gurmar/`
- `InflationItems/Codes/03_Clothing/Vakko/`
- `InflationItems/Codes/08_Communication/BeymenTech/`
- `InflationItems/Codes/05_Furnishings/ConstructionSuppliesMarkets/yapimaks/`
- `InflationItems/Codes/04_Housing/Emlakjet/`
- `InflationItems/Codes/08_Communication/<Retailer>/` tech retailer scrapers (Beymen, DR, Huawei, Koctas, PozitifTeknoloji, Samsung, VatanComputer)
- `InflationItems/Codes/08_Communication/Telecom/` (`scraper.py` mobile tariffs: Turkcell, Vodafone, Türk Telekom, NetGSM; `internet.py` home internet: Superonline, Vodafone, Kablonet, Milleni, TurkNet, Türk Telekom; `streaming.py` streaming subscriptions; `repair.py` ICT equipment repair prices)

## Data tree

`InflationItems/Datas/<NN_TÜİK group>/[<sector>/]<Source>/` (upstream 01-13 layout; e.g. `01_Food/Gurmar`, `05_Furnishings/HomeGoods/Chakra`)

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

- Gurmar raw: `InflationItems/Datas/01_Food/Gurmar/gurmar_prices_YYYY-MM-DD.csv`
- Vakko raw: `InflationItems/Datas/03_Clothing/Vakko/vakko_YYYY-MM-DD.csv`
- Yapımaks raw: `InflationItems/Datas/05_Furnishings/ConstructionSuppliesMarkets/yapimaks/YYYY-MM-DD.csv`
- HomeGoods raw: `InflationItems/Datas/05_Furnishings/HomeGoods/Chakra/chakra_all_categories_YYYY_MM_DD.csv`
- Emlakjet raw: `InflationItems/Datas/04_Housing/Emlakjet/YYYY-MM-DD.csv`
- 08_Communication raw (TÜİK group 08, upstream layout: one folder per retailer, no sub-folders): tech `InflationItems/Datas/08_Communication/<Retailer>/<retailer>_YYYY-MM-DD.csv`
- Telecom raw: `InflationItems/Datas/08_Communication/<Operator>/<operator>_YYYY-MM-DD.csv`; home internet `InflationItems/Datas/08_Communication/<Provider>/<provider>_internet_YYYY-MM-DD.csv`, streaming `InflationItems/Datas/08_Communication/<Service>/<service>_YYYY-MM-DD.csv`, repair `InflationItems/Datas/08_Communication/<Source>/<source>_repair_YYYY-MM-DD.csv`

## Repository boundary

No `frontend/`, `inflation_dashboard/`, Falcon API, Svelte package or committed SQLite database belongs here. Those are maintained in `../inflationstudymirror-web`.
