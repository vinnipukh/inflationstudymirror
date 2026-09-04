---
last_mapped: 2026-09-03
focus: tech
---

# Tech Stack

## Architecture and Core Frameworks

- **Backend / API**: Falcon REST API (`falcon`), serialized with `orjson`.
- **Production Serving**: **Granian** (Rust Hyper WSGI) and **Gunicorn** (`gthread`).
- **Database & Storage**:
  - **SQLite WAL Database** (`InflationItems/prices.db`): ~2.8 GB database storing 4.09M observations and 68K products, operating with 1 GB memory-mapped I/O (`mmap_size`), 128 MB page cache, and `PRAGMA query_only = 1` for read concurrency.
  - **Partitioned JSON Time Series** (`InflationItems/prices_json/`): Retailer-partitioned clean JSON files storing chronological price histories (all files <37 MB, GitHub safe).
  - **Raw CSV Archive** (`InflationItems/Datas/`): Historical scraper output preserved for auditing.
- **Frontend**:
  - **Svelte 5 / SvelteKit** (`frontend/`, Modern Production UI): client-side static SPA (`adapter-static`, `ssr = false`) with Canvas charting via **Apache ECharts**. Minimalism & Swiss Style design tokens (Fira Sans + Fira Code, light/dark themes). Talks to the Falcon API over HTTP; `VITE_API_BASE_URL` (default `http://localhost:8000`).
  - **Streamlit** (Legacy / Admin UI): `streamlit_app.py` consuming Falcon API over HTTP (frozen; feature development is in `frontend/`).
- **Data Engineering & ML**: `pandas`, `numpy`, `scikit-learn`, `xgboost`, `lightgbm`, `catboost`.
- **Packaging & Tooling**: Python via `uv` / standard virtualenv (`pyproject.toml`, `requirements.txt`); frontend via **npm** (`frontend/package.json`, Node >= 20).

## Scraper & Ingestion Stack

- **HTTP Transports**:
  - `requests` (Gurmar, Vakko, Health)
  - `curl_cffi` (Watsons, TasciYapi — TLS fingerprint impersonation for Cloudflare / Akamai)
  - `aiohttp` (Yapimaks — asynchronous catalog crawler with token-bucket rate limiting)
- **HTML Parsing**:
  - `beautifulsoup4`, `lxml`
- **Browser Automation & Anti-Bot**:
  - `selenium` & `seleniumbase` (Beymen, Emlakjet)
  - `undetected-chromedriver` (Sarı site rental scraper with persistent profiles)
  - `playwright-cli`, `camoufox-cli`, `obscura` (installed on environment for anti-bot exploration and deep research)

## Continuous Integration & Automation

- GitHub Actions (`.github/workflows/`): 8 daily workflows running on `ubuntu-latest`.
- Permissions: `contents: write` for automated CSV and log commits.
- Git Bot: Commits authored by `github-actions[bot]`.
