---
last_mapped: 2026-09-02
focus: integrations
---

# Integrations

## Retailer and service sources

- **Gurmar API**: `InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py` calls `https://api.gurmar.com.tr/api/home/initialize-v2` for dynamic category discovery and `https://api.gurmar.com.tr/api/home/slug/{slug}?page={page}` for products, writing daily CSVs to `InflationItems/Datas/Markets/Gurmar/`.
- **Vakko API**: `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` reads live sitemaps from `https://www.vakko.com/sitemap.xml` and queries `https://api.vakko.com/occ/v2/vsite/products/search`, writing daily CSVs to `InflationItems/Datas/ClothingStores/Vakko/`.
- **Yapimaks API**: `InflationItems/Codes/ConstructionMarkets/yapimaks/scraper.py` reads `https://yapimaks.com/sitemap/products1.xml`, parses `<lastmod>`, and queries `https://yapimaks.com/api/tr/v1/layouts/b2c/products/{product_id}.json` using an async `aiohttp` rate-limited pool, writing daily CSVs to `InflationItems/Datas/ConstructionSuppliesMarkets/yapimaks/`.
- **TasciYapi**: `InflationItems/Codes/ConstructionMarkets/tasciyapimarket/scraper.py` scrapes `https://tasciyapimarket.com/` with `curl_cffi` TLS impersonation and writes to `InflationItems/Datas/ConstructionSuppliesMarkets/TasciYapiMarket/`.
- **Watsons**: `InflationItems/Codes/Cosmetics/Watson/scraper.py` queries `https://api.watsons.com.tr/api/v2/wtctr-spa/search` using serialised `curl_cffi` sessions and writes to `InflationItems/Datas/Cosmetics/Watson/`.
- **Chakra**: `InflationItems/Codes/HomeGoods/scraper.py` scrapes Chakra categories and extracts JSON analytics payloads, writing to `InflationItems/Datas/HomeGoods/`.
- **Beymen Tech**: `InflationItems/Codes/Technology/scraper.py` queries `https://www.beymen.com/api/product/list` with SeleniumBase stealth cookies and writes to `InflationItems/Datas/Technology/`.
- **Emlakjet**: `InflationItems/Codes/HousesRent/Emlakjet/scraper.py` crawls residential rental listings via browser automation and checkpoints state under `InflationItems/Datas/HousesRent/Emlakjet/state/`.
- **Sarı site rentals**: `InflationItems/Codes/HousesRent/KayseriSivasTokat/main.py` uses persistent Selenium profiles to collect `District, Rooms, Price, ilanId` rental listings.

## Secrets and credentials

- `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` reads `VAKKO_COOKIE` and `VAKKO_USER_AGENT` from environment variables, or automatically fetches them via an automated headless browser session.
- `.github/workflows/vakko_scraper.yml` passes `secrets.VAKKO_COOKIE` and `secrets.VAKKO_USER_AGENT`.
- `.env` and `.env.*` are ignored in `.gitignore`.

## Outputs

- Raw scraped data is written under `InflationItems/Datas/...` by domain and retailer.
- Inflation outputs are written under `Inflations/Datas/...` by domain and retailer.
- Scraper logs are written to `logs/` (e.g. `logs/yapimaks_YYYY-MM-DD.log`).
- The Falcon API backend (`inflation_dashboard/`) serves data from `InflationItems/Datas/`.

## Automation Schedule

All 8 main scrapers are automated via GitHub Actions in `.github/workflows/`:
- `00:00 UTC` — Gurmar (`gurmar.yml`)
- `02:00 UTC` — Yapımaks (`yapimaks.yml`)
- `04:00 UTC` — Vakko (`vakko_scraper.yml`)
- `06:00 UTC` — Watsons (`watsons.yml`)
- `08:00 UTC` — Chakra (`chakra_scraper.yml`)
- `10:00 UTC` — Beymen (`beymen.yml`)
- `14:00 UTC` — TasciYapi (`tasciyapi.yml`)
- `16:00 UTC` — Emlakjet (`emlakjet_scraper.yml`)
