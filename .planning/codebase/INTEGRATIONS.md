---
last_mapped: 2026-07-16
focus: integrations
---

# Integrations

## Retailer and service sources

- Gurmar API: `Codes/Markets/Gurmar/gurmar_scraper.py` calls `https://api.gurmar.com.tr/api/home/slug/{slug}?page={page}` and writes daily CSVs to `Datas/Markets/Gurmar/`.
- Vakko API: `Codes/ClothingStores/Vakko/vakko_master_scraper.py` calls `https://api.vakko.com/occ/v2/vsite/products/search` using category IDs extracted from `Codes/ClothingStores/Vakko/vakko_categories.xml`.
- Yapimaks API: `Codes/ConstructionMarkets/yapimaks/scraper.py` reads `https://yapimaks.com/sitemap/products1.xml`, derives product IDs, then calls `https://yapimaks.com/api/tr/v1/layouts/b2c/products/{product_id}.json`.
- Sahibinden rental pages: `Codes/HousesRent/KayseriSivasTokat/scraper.py` uses browser automation and anti-bot handling to collect rental listings.
- Additional categories exist under `Codes/Cosmetics/Watson/`, `Codes/HomeGoods/`, `Codes/Technology/`, and `Codes/Health/Diagnostic&Surgical Services/`.

## Secrets and credentials

- `Codes/ClothingStores/Vakko/vakko_master_scraper.py` reads `VAKKO_COOKIE` and `VAKKO_USER_AGENT` from environment variables via `python-dotenv`.
- `.github/workflows/vakko_scraper.yml` passes `secrets.VAKKO_COOKIE` and `secrets.VAKKO_USER_AGENT` to the scraper job.
- `Codes/ConstructionMarkets/yapimaks/scraper.py` contains a hardcoded session cookie string in `make_session()`; do not copy the value into docs or logs.
- `.env` and `.env.*` are ignored in `.gitignore`.

## Outputs

- Raw scraped data is written under `Datas/...` by domain and retailer.
- Inflation outputs are written under `Inflations/Datas/...` by domain and retailer.
- Yapimaks logs are written under `logs/yapimaks_YYYY-MM-DD.log`.
- Dashboard reads root `Datas/` in `streamlit_app.py`, not `Inflations/Datas/`.

## External automation behavior

- GitHub Actions commits scraped data after Vakko runs.
- Most other scrapers appear to be manually run or externally scheduled outside this repo.
- Generated data files are versioned in the repo, which makes dashboard deployment simple but increases checkout size and app startup cost.
