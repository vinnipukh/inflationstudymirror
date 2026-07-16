---
last_mapped: 2026-07-16
focus: concerns
---

# Concerns

## Dependency and environment drift

- `pyproject.toml` declares `requires-python = ">=3.14"` with no dependencies, while `.github/workflows/vakko_scraper.yml` uses Python 3.12 and the local runtime observed is Python 3.11.
- Dashboard dependencies `streamlit`, `plotly`, and `pandas` are not all represented in `requirements.txt`.
- GitHub Actions installs dependencies inline instead of using the repo manifest, so local and CI environments can diverge.

## Secret handling

- `Codes/ConstructionMarkets/yapimaks/scraper.py` contains a hardcoded session cookie in `make_session()`; this should be moved to environment variables before sharing or committing further automation around it.
- `Codes/ClothingStores/Vakko/vakko_master_scraper.py` correctly expects `VAKKO_COOKIE` and `VAKKO_USER_AGENT`, but the workflow uses `USER_AGENT` as the environment variable name while the script reads `VAKKO_USER_AGENT`; this mismatch can break scheduled scraping.

## Fragile scraping areas

- Websites may change API schemas, pagination, anti-bot behavior, and cookie/session requirements.
- `Codes/HousesRent/KayseriSivasTokat/scraper.py` is complex and contains manual solve, Turnstile, browser-block, and checkpoint logic; it should be treated as fragile.
- Several scripts print/log Turkish status with emoji symbols; fine for manual runs, but logs may be noisy in automation.

## Data volume and performance

- `Datas/` and `Inflations/Datas/` contain hundreds of CSV files and hundreds of MB of data.
- Naively loading all CSVs made `streamlit_app.py` slow; the dashboard now uses retailer/date/file caps, but new features should preserve that constraint.
- Generated logs under `logs/` are numerous and may grow indefinitely.

## Data quality risks

- CSV delimiter and column names vary across sources and historical files.
- Some data rows include scraped timestamps far earlier than the filename date, especially in Yapimaks CSVs, which may confuse analyses that trust row-level timestamps.
- Inflation calculators rely on product IDs/names remaining stable across dates.

## Architecture concerns

- Scripts are mostly standalone, with duplicated loader/normalizer logic across sources.
- There is no shared package for path resolution, price parsing, schema normalization, or TUIK mapping.
- There is no test harness to detect parser breakage before generated data is committed.
