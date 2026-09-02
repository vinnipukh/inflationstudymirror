---
last_mapped: 2026-09-02
focus: tech
---

# Tech Stack

## Architecture and Core Frameworks

- **Backend / API**: Falcon REST API (`falcon`), served by Waitress WSGI (`waitress`).
- **Frontend**: Streamlit (`streamlit`), Plotly Express (`plotly`).
- **Data Engineering & ML**: `pandas`, `numpy`, `scikit-learn`, `xgboost`, `lightgbm`, `catboost`.
- **Packaging & Tooling**: Managed via `uv` / standard virtualenv, documented in `pyproject.toml` and `requirements.txt`.

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
  - `camoufox` / `obscura` (installed on environment for anti-bot exploration)

## Continuous Integration & Automation

- GitHub Actions (`.github/workflows/`): 8 daily workflows running on `ubuntu-latest`.
- Permissions: `contents: write` for automated CSV and log commits.
- Git Bot: Commits authored by `github-actions[bot]`.
