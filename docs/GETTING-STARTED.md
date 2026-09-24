# Getting Started

## Prerequisites

- Python 3.10+
- Git
- Chrome/Chromium for Selenium, SeleniumBase and undetected-chromedriver scrapers
- Source-specific credentials only where explicitly required

Scheduled workflows currently use Python 3.10–3.12 depending on the source.

## Install

With uv:

```bash
uv sync
```

With pip:

```bash
python -m pip install -r requirements.txt
```

Browser-backed scrapers may require platform-specific Chrome/driver setup. Follow the source README and `docs/scraping-wiki/` before changing them.

## Choose a workflow

### Inspect a scraper without running it

```bash
python InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py --help
python InflationItems/Codes/HousesRent/Emlakjet/scraper.py --help
```

### Run a bounded live sample first

Prefer source flags such as `--limit`, `--start-url`, small city/district scopes, or reduced page/refresh budgets. Then inspect:

- the dated CSV under `InflationItems/Datas/`;
- checkpoint/state files;
- the scraper log;
- row counts, schema and obvious price anomalies.

### Run a scheduled source

See `SCRAPER_TIMETABLE.md` and `.github/workflows/` for exact scripts and schedules.

## Run inflation calculations

```bash
python Inflations/Codes/turkey_inflation.py --help
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py --help
python Inflations/Codes/EpeyKatfg/monthly_inflation.py --help
```

Use repository-relative paths and small date windows first. Verify generated files under `Inflations/Datas/` and compare summary values with the documented methodology.

## Required reading

Before modifying a scraper:

1. `docs/scraping-wiki/README.md`
2. Relevant concept/entity pages
3. `docs/APPROACH.md` for rental work
4. `InflationItems/Codes/AGENTS.md`
5. Source-specific README/config

## Supply data to the web application

The separate `../inflationstudymirror-web` repository consumes raw CSV, `prices_json/` and generated inflation artifacts. See `docs/DATA_PUBLICATION.md`.
