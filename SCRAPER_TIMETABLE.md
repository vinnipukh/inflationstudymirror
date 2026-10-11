# Scraper Timetable

Daily schedule of all GitHub Actions scraper workflows in `.github/workflows/`.

All times in **Istanbul time (UTC+3)**. Türkiye uses UTC+3 year-round (no daylight saving since 2016).

| Istanbul Time (UTC+3) | UTC  | Scraper        | Workflow File         | Script                                   | Output Data                      |
|-----------------------|------|----------------|-----------------------|------------------------------------------|----------------------------------|
| 03:00                | 00:00 | Gurmar         | `gurmar.yml`          | `InflationItems/Codes/01_Food/Gurmar/gurmar_scraper.py` | `InflationItems/Datas/01_Food/Gurmar/*.csv`     |
| 05:00                | 02:00 | Yapımaks       | `yapimaks.yml`        | `InflationItems/Codes/05_Furnishings/ConstructionSuppliesMarkets/yapimaks/scraper.py` | `InflationItems/Datas/05_Furnishings/ConstructionSuppliesMarkets/yapimaks/` + `logs/` |
| 07:00                | 04:00 | Vakko          | `vakko_scraper.yml`   | `InflationItems/Codes/03_Clothing/Vakko/vakko_master_scraper.py` | `InflationItems/Datas/03_Clothing/Vakko/*.csv` |
| 09:00                | 06:00 | Watsons        | `watsons.yml`         | `InflationItems/Codes/13_Personal_Care/Cosmetics/Watson/scraper.py`       | `InflationItems/Datas/` + `logs/`               |
| 11:00                | 08:00 | Chakra         | `chakra_scraper.yml`  | `InflationItems/Codes/05_Furnishings/HomeGoods/Chakra/scraper.py`              | `InflationItems/Datas/05_Furnishings/HomeGoods/Chakra/*.csv`          |
| 13:00                | 10:00 | Beymen         | `beymen.yml`          | `InflationItems/Codes/08_Communication/BeymenTech/scraper.py`             | `InflationItems/Datas/08_Communication/Beymen/ (beymen_tech_*)`              |
| 17:00                | 14:00 | TasciYapi      | `tasciyapi.yml`       | `InflationItems/Codes/05_Furnishings/ConstructionSuppliesMarkets/tasciyapimarket/scraper.py` | `InflationItems/Datas/05_Furnishings/ConstructionSuppliesMarkets/TasciYapiMarket/*.csv` |
| 19:00                | 16:00 | Emlakjet       | `emlakjet_scraper.yml` | `InflationItems/Codes/04_Housing/Emlakjet/scraper.py` | `InflationItems/Datas/04_Housing/Emlakjet/*.csv` |

## Notes

- All workflows run **daily** (`* * *` in cron) and can also be triggered manually via `workflow_dispatch`.
- Scrapers run in sequence through the day (UTC+3): Gurmar just after midnight, construction markets and clothing before breakfast, cosmetics at 09:00, home goods at 11:00, technology at lunchtime, TasciYapi at 17:00, and Emlakjet at 19:00.
- All workflows use `ubuntu-latest`, commit output CSV/logs via the `github-actions[bot]`, and skip commits when there are no changes.
- TasciYapi has an explicit `timeout-minutes: 60` limit; Emlakjet has a `timeout-minutes: 240` limit because its full geographic crawl is substantially longer (it also runs with `--resume` and commits its checkpoint so interrupted crawls continue on the next run).
- Yapımaks is `timeout-minutes: 360` — the maximum GitHub allows for public-repo jobs (the old `480` could never be reached; the job was killed by the platform's hard 6 h cap). The scraper is now async (aiohttp workers + rate limiter) with a daily refresh budget (`--refresh-budget 2500`, stalest-first) and a wall-clock budget (`--max-duration 240`), so even a full-catalog catch-up (~8,400 products) completes in ≈1 h and can never hit the cap again; unfinished products keep yesterday's row and are re-picked the next day (self-heal). See `docs/TECH-STACK-SEARCH.md` §3.2.
## Self-hosted cron server (08_Communication: tech + telecom)

Seven technology-retail scrapers and the four Telecom scrapers run on a separate low-RAM Ubuntu server via cron,
not GitHub Actions. Setup, measured durations and operations:
`deploy/scraper-server/README.md`. Jobs share one lock, so they never overlap.

| Istanbul Time (UTC+3) | Scraper | Script | Output Data |
|---|---|---|---|
| 01:00 | Samsung | `InflationItems/Codes/08_Communication/Samsung/scripts/main.py` | `InflationItems/Datas/08_Communication/Samsung/*.csv` |
| 01:10 | Huawei | `InflationItems/Codes/08_Communication/Huawei/huawei_scraper.py` | `InflationItems/Datas/08_Communication/Huawei/*.csv` |
| 01:20 | Pozitif Teknoloji | `InflationItems/Codes/08_Communication/PozitifTeknoloji/pozitifTeknoloji_scraper.py` | `InflationItems/Datas/08_Communication/PozitifTeknoloji/*.csv` |
| 01:30 | D&R | `InflationItems/Codes/08_Communication/DR/dr_scraper.py` | `InflationItems/Datas/08_Communication/DR/*.csv` |
| 02:00 | Beymen | `InflationItems/Codes/08_Communication/Beymen/scraper.py` | `InflationItems/Datas/08_Communication/Beymen/*.csv` |
| 03:00 | Koçtaş | `InflationItems/Codes/08_Communication/Koctas/koctas_scraper.py` | `InflationItems/Datas/08_Communication/Koctas/*.csv` |
| 04:00 | Vatan | `InflationItems/Codes/08_Communication/VatanComputer/vatan_comp.py` | `InflationItems/Datas/08_Communication/VatanComputer/*.csv` |
| 06:00 | Telecom — mobile tariffs (Turkcell, Vodafone, Türk Telekom, NetGSM) | `InflationItems/Codes/08_Communication/Telecom/scraper.py` | `InflationItems/Datas/08_Communication/<Operator>/*.csv` |
| 07:30 | Telecom — home internet (Superonline, Vodafone, Kablonet, Milleni, TurkNet, Türk Telekom) | `InflationItems/Codes/08_Communication/Telecom/internet.py` | `InflationItems/Datas/08_Communication/<Provider>/*_internet_*.csv` |
| 08:45 | Telecom — streaming subscriptions (12 services) | `InflationItems/Codes/08_Communication/Telecom/streaming.py` | `InflationItems/Datas/08_Communication/<Service>/*.csv` |
| 09:00 | Telecom — ICT equipment repair prices (Apple, Samsung, Huawei, Egemek, GSM İletişim) | `InflationItems/Codes/08_Communication/Telecom/repair.py` | `InflationItems/Datas/08_Communication/<Source>/*_repair_*.csv` |

Beymen is also scraped by the `beymen.yml` workflow (`InflationItems/Codes/08_Communication/BeymenTech/scraper.py`,
same technology category) into `InflationItems/Datas/08_Communication/Beymen/ (beymen_tech_*)`; the server copy writes a
separate dataset.
