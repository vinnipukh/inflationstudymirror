# Data Source Integrations

## Retail and service sources

- **Gurmar** — `InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py` uses the Gurmar initialization/category API, dynamically discovers categories, writes dated CSVs under `InflationItems/Datas/Markets/Gurmar/`, and reports coverage/integrity regressions.
- **Vakko** — `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` reads the live category sitemap, queries the Vakko product API, optionally creates a browser session/cookie factory, and writes under `InflationItems/Datas/ClothingStores/Vakko/`.
- **Yapımaks** — `InflationItems/Codes/ConstructionMarkets/yapimaks/scraper.py` parses the product sitemap and asynchronously refreshes products through the Yapımaks JSON API. It carries forward the previous complete snapshot, refreshes stale/empty rows and writes `InflationItems/Datas/ConstructionSuppliesMarkets/yapimaks/`.
- **Taşçı Yapı Market** — `InflationItems/Codes/ConstructionMarkets/tasciyapimarket/scraper.py` uses BeautifulSoup with `curl_cffi` TLS impersonation and a `requests` fallback, writing under `InflationItems/Datas/ConstructionSuppliesMarkets/TasciYapiMarket/`.
- **Watsons** — `InflationItems/Codes/Cosmetics/Watson/scraper.py` uses a serialized `curl_cffi` session against the Watsons search API and writes under `InflationItems/Datas/Cosmetics/Watson/`.
- **Chakra** — `InflationItems/Codes/HomeGoods/scraper.py` collects category data and extracts analytics payload fields, writing under `InflationItems/Datas/HomeGoods/`.
- **Beymen Tech** — `InflationItems/Codes/Technology/scraper.py` uses SeleniumBase/cookies and dynamic pagination against the Beymen product-list API, writing under `InflationItems/Datas/Technology/`.
- **Emlakjet rentals** — `InflationItems/Codes/HousesRent/Emlakjet/` uses a visible browser-backed collection flow, serial pacing, deduplication and tracked checkpoint state. Output lives under `InflationItems/Datas/HousesRent/Emlakjet/`.
- **Rental listing source (Kayseri/Sivas/Tokat)** — `InflationItems/Codes/HousesRent/KayseriSivasTokat/` uses a persistent undetected-chromedriver profile and writes `District, Rooms, Price, ilanId` snapshots under `InflationItems/Datas/HousesRent/<City>/`.
- **EpeyKatfg** — `InflationItems/Codes/EpeyKatfg/` builds a catalog from official sitemaps, pulls price-history series and materializes/updates the canonical history store under `InflationItems/Datas/EpeyKatfg/` and `InflationItems/prices_json/`.
- **Health services** — `InflationItems/Codes/Health/` contains service-price collection paths and monthly source data.

## Credentials and sessions

- Vakko supports `VAKKO_COOKIE` and `VAKKO_USER_AGENT` as optional authenticated fallbacks. The scheduled workflow supplies the cookie secret and `USER_AGENT`; keep source/workflow variable names aligned when changing them.
- Browser-backed scrapers may use local Chrome, SeleniumBase or persistent profiles.
- Never commit cookies, user-agent bindings tied to secrets, browser profiles, `.env` files or challenge tokens.

## Outputs

- Raw source data: `InflationItems/Datas/<Domain>/<Source>/`.
- Source state/checkpoints: beside the relevant source data, gitignored where transient.
- Partitioned price histories: `InflationItems/prices_json/`.
- Inflation reports: `Inflations/Datas/`.
- Operational logs: `logs/`.

## Automation

Eight primary GitHub Actions workflows run daily. See `SCRAPER_TIMETABLE.md` for UTC/Istanbul times, scripts and output paths. Workflows are operational collection jobs, not a substitute for source-specific verification.
