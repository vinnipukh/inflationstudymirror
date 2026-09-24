# Tech Stack

## Language and packaging

- Python 3.10+ for scrapers and calculators.
- `uv` for local environment/lock management.
- `requirements.txt` as an alternative pip workflow.
- GitHub Actions for scheduled collection.

## HTTP and parsing

- `requests` — common HTTP APIs and session/retry handling.
- `aiohttp` — asynchronous Yapımaks collection.
- `httpx` — EpeyKatfg catalog/history requests.
- `curl_cffi` — TLS impersonation for Watsons/TasciYapi and fallback paths.
- `cloudscraper` — retained for legacy source paths.
- `beautifulsoup4` / `lxml` — HTML parsing.

## Browser automation

- `selenium` — Emlakjet and Vakko browser sessions.
- `seleniumbase` — Beymen browser-backed collection.
- `undetected-chromedriver` — persistent rental scraper profile.
- `camoufox` — evaluated/optional Firefox automation stack.
- `DrissionPage` — retained by several legacy calculator/source scripts.

## Data processing

- `pandas` / `numpy` — normalization, matching and aggregation.
- `openpyxl` — optional TÜİK/source spreadsheet import.
- `matplotlib` / `seaborn` — legacy analysis visualizations.
- `regex` — Unicode-aware normalization in selected calculators.
- `tqdm` — bounded progress output.

## Storage and publication

- CSV — auditable raw and generated data.
- Partitioned JSON — generated price histories handed to the web repository.
- Logs/checkpoints — operational state; secrets and browser profiles are excluded.

The SQLite serving database and web-serving frameworks are not part of this repository's stack.
