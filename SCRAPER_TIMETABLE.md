# Scraper Timetable

Daily schedule of all GitHub Actions scraper workflows in `.github/workflows/`.

All times in **Istanbul time (UTC+3)**. Türkiye uses UTC+3 year-round (no daylight saving since 2016).

| Istanbul Time (UTC+3) | UTC  | Scraper        | Workflow File         | Script                                   | Output Data                      |
|-----------------------|------|----------------|-----------------------|------------------------------------------|----------------------------------|
| 03:00                | 00:00 | Gurmar         | `gurmar.yml`          | `Codes/Markets/Gurmar/gurmar_scraper.py` | `Datas/Markets/Gurmar/*.csv`     |
| 05:00                | 02:00 | Yapımaks       | `yapimaks.yml`        | `Codes/ConstructionMarkets/yapimaks/scraper.py` | `Datas/ConstructionSuppliesMarkets/yapimaks/` + `logs/` |
| 07:00                | 04:00 | Vakko          | `vakko_scraper.yml`   | `Codes/ClothingStores/Vakko/vakko_master_scraper.py` | `Datas/ClothingStores/Vakko/*.csv` |
| 09:00                | 06:00 | Watsons        | `watsons.yml`         | `Codes/Cosmetics/Watson/scraper.py`       | `Datas/` + `logs/`               |
| 11:00                | 08:00 | Chakra         | `chakra_scraper.yml`  | `Codes/HomeGoods/scraper.py`              | `Datas/HomeGoods/*.csv`          |
| 13:00                | 10:00 | Beymen         | `beymen.yml`          | `Codes/Technology/scraper.py`             | `Datas/Technology/`              |
| 17:00                | 14:00 | TasciYapi      | `tasciyapi.yml`       | `Codes/ConstructionMarkets/tasciyapimarket/tasciyapi_scraper.py` | `Datas/ConstructionSuppliesMarkets/TasciYapiMarket/*.csv` |

## Notes

- All workflows run **daily** (`* * *` in cron) and can also be triggered manually via `workflow_dispatch`.
- Scrapers run in sequence through the day (UTC+3): Gurmar just after midnight, construction markets and clothing before breakfast, cosmetics at 09:00, home goods at 11:00, technology at lunchtime, and the last construction supplier run at 17:00.
- All workflows use `ubuntu-latest`, commit output CSV/logs via the `github-actions[bot]`, and skip commits when there are no changes.
- TasciYapi is the only one with an explicit `timeout-minutes: 60` limit.