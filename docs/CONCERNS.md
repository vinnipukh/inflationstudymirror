---
last_mapped: 2026-09-02
focus: concerns
---

# Concerns

## Dependency and environment drift

- Scrapers in GitHub Actions install specific subsets of packages inline on Ubuntu runners (e.g. `curl_cffi==0.15.0` pinned for Python 3.10 compatibility on Watsons).
- Scrapers require distinct browser drivers and network settings (e.g. Chrome headless, Xvfb for Emlakjet, undetected-chromedriver for rental, seleniumbase for Beymen).

## Secret handling

- `InflationItems/Codes/ClothingStores/Vakko/vakko_master_scraper.py` supports automated cookie retrieval via a headless browser, falling back to `VAKKO_COOKIE` and `VAKKO_USER_AGENT` environment variables.
- `.env` files must remain strictly local and gitignored.

## Anti-bot and Fragile Scraper Areas

- **Watsons**: Akamai flags parallel in-flight requests from a single IP; requests must remain strictly serialized (~1 req/s) with adaptive exponential backoff.
- **Yapimaks**: High catalog volume (~8,400 items) requires token-bucket rate limiting (0.8 req/s) and daily refresh budgets (`--refresh-budget 2500`) to fit within GitHub's 6-hour job ceiling.
- **Sarı site rentals**: Complex anti-bot measures require persistent profiles (`SeleniumProfile/`) and manual-solve checkpoints rather than automated bypass attempts.
- **Emlakjet**: Pagination is geometrically capped at 50 pages per scope; deep recursive crawling and watchdog session restarts (`BrowserSession`) are required to prevent memory/session stalls.

## Data volume and performance

- `InflationItems/Datas/` and `Inflations/Datas/` contain over a thousand CSV files and hundreds of megabytes of tracked data.
- The Falcon API (`inflation_dashboard/`) implements bounded loading and an LRU/TTL file cache (`_file_frame_cache`) to prevent redundant disk I/O on dashboard queries.
- Git repository size grows as daily snapshots are committed; git history should be monitored.

## Data quality risks

- Retailer schemas vary (e.g. semicolon vs comma delimiters, differing column headers).
- Inflation calculators rely on product IDs and names remaining consistent across daily snapshots.
