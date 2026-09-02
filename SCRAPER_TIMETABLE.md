# Scraper Timetable

Daily schedule of all GitHub Actions scraper workflows in `.github/workflows/`.

All times in **Istanbul time (UTC+3)**. Türkiye uses UTC+3 year-round (no daylight saving since 2016).

| Istanbul Time (UTC+3) | UTC  | Scraper        | Workflow File         | Script                                   | Output Data                      |
|-----------------------|------|----------------|-----------------------|------------------------------------------|----------------------------------|
| 03:00                | 00:00 | Gurmar         | `gurmar.yml`          | `InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py` | `InflationItems/Datas/Markets/Gurmar/*.csv`     |
| 05:00                | 02:00 | Yapımaks       | `yapimaks.yml`        | `InflationItems/Codes/ConstructionMarkets/yapimaks/scraper.py` | `InflationItems/Datas/ConstructionSuppliesMarkets/yapimaks/` + `logs/` |
| 07:00                | 04:00 | Vakko          | `vakko_scraper.yml`   | `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` | `InflationItems/Datas/ClothingStores/Vakko/*.csv` |
| 09:00                | 06:00 | Watsons        | `watsons.yml`         | `InflationItems/Codes/Cosmetics/Watson/scraper.py`       | `InflationItems/Datas/` + `logs/`               |
| 11:00                | 08:00 | Chakra         | `chakra_scraper.yml`  | `InflationItems/Codes/HomeGoods/scraper.py`              | `InflationItems/Datas/HomeGoods/*.csv`          |
| 13:00                | 10:00 | Beymen         | `beymen.yml`          | `InflationItems/Codes/Technology/scraper.py`             | `InflationItems/Datas/Technology/`              |
| 17:00                | 14:00 | TasciYapi      | `tasciyapi.yml`       | `InflationItems/Codes/ConstructionMarkets/tasciyapimarket/scraper.py` | `InflationItems/Datas/ConstructionSuppliesMarkets/TasciYapiMarket/*.csv` |
| 19:00                | 16:00 | Emlakjet       | `emlakjet_scraper.yml` | `InflationItems/Codes/HousesRent/Emlakjet/scraper.py` | `InflationItems/Datas/HousesRent/Emlakjet/*.csv` |

## Notes

- All workflows run **daily** (`* * *` in cron) and can also be triggered manually via `workflow_dispatch`.
- Scrapers run in sequence through the day (UTC+3): Gurmar just after midnight, construction markets and clothing before breakfast, cosmetics at 09:00, home goods at 11:00, technology at lunchtime, TasciYapi at 17:00, and Emlakjet at 19:00.
- All workflows use `ubuntu-latest`, commit output CSV/logs via the `github-actions[bot]`, and skip commits when there are no changes.
- TasciYapi has an explicit `timeout-minutes: 60` limit; Emlakjet has a `timeout-minutes: 240` limit because its full geographic crawl is substantially longer (it also runs with `--resume` and commits its checkpoint so interrupted crawls continue on the next run).
- Yapımaks is `timeout-minutes: 360` — the maximum GitHub allows for public-repo jobs (the old `480` could never be reached; the job was killed by the platform's hard 6 h cap). The scraper is now async (aiohttp workers + rate limiter) with a daily refresh budget (`--refresh-budget 2500`, stalest-first) and a wall-clock budget (`--max-duration 240`), so even a full-catalog catch-up (~8,400 products) completes in ≈1 h and can never hit the cap again; unfinished products keep yesterday's row and are re-picked the next day (self-heal). See `docs/TECH-STACK-SEARCH.md` §3.2.