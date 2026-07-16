---
last_mapped: 2026-07-16
focus: tech
---

# Stack

## Runtime and language

- Python repository for scraping Turkish retailer/service price data and calculating inflation-style price changes.
- Main runtime observed in automation is Python 3.12 via `.github/workflows/vakko_scraper.yml`.
- Local project metadata exists in `pyproject.toml`, but it currently declares `requires-python = ">=3.14"` and no dependencies; this conflicts with observed scripts and workflow usage.
- Root `requirements.txt` is the practical dependency list for scrapers.
- A Streamlit dashboard entrypoint exists at `streamlit_app.py` and imports `pandas`, `plotly.express`, and `streamlit`; those dashboard dependencies are not listed in `requirements.txt`.

## Core dependencies

- HTTP/API scraping: `requests`, `urllib3`, `cloudscraper`, `curl-cffi` in `requirements.txt`.
- HTML parsing: `beautifulsoup4`, used by `Codes/HousesRent/KayseriSivasTokat/scraper.py`.
- Browser automation / anti-bot workflows: `seleniumbase`, `camoufox`, and Playwright-style code in `Codes/HousesRent/KayseriSivasTokat/scraper.py`.
- Data analysis: `pandas` is used across inflation calculators such as `Inflations/Codes/Markets/Gurmar/gurmar_inflation.py` and dashboard code in `streamlit_app.py`.
- Dashboard visualization: `plotly` and `streamlit` in `streamlit_app.py`.
- Environment loading: `python-dotenv`, used by `Codes/ClothingStores/Vakko/vakko_master_scraper.py`.

## Automation

- `.github/workflows/vakko_scraper.yml` runs the Vakko scraper daily at 04:00 UTC and commits new `Datas/ClothingStores/Vakko/*.csv` files.
- Workflow installs `requests pandas beautifulsoup4 python-dotenv` directly rather than using `requirements.txt`.
- There are many generated CSV and log artifacts under `Datas/`, `Inflations/Datas/`, and `logs/`.

## Configuration files

- `requirements.txt` is the only complete dependency manifest currently tracked for scraper dependencies.
- `pyproject.toml` exists but is skeletal and likely not authoritative yet.
- `.gitignore` excludes virtualenvs, caches, secrets, and IDE files, but not generated logs or CSV datasets.

## Notes for future planning

- Treat `requirements.txt` as source of truth for scraper installs until `pyproject.toml` is reconciled.
- Add dashboard dependencies explicitly if Streamlit deployment becomes a committed feature.
- Avoid relying on one Python version until `pyproject.toml`, GitHub Actions, and local usage agree.
