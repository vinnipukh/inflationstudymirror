# Inflation Study Data

Data acquisition and inflation-analysis repository for the Inflation Study project.

This repository tracks retailer/service scrapers, raw price observations, partitioned JSON histories, inflation calculators, TÜİK-style category configuration and generated inflation reports.

The Svelte dashboard, Falcon API and SQLite serving layer have been separated into the sibling web repository:

```text
E:\Projects\
├── inflationstudymirror\       # this repository: scrapers + inflation
└── inflationstudymirror-web\   # Svelte + Falcon API + SQLite runtime
```

## Repository structure

```text
InflationItems/
  Codes/                       # scrapers grouped by market/retailer
  Datas/                       # raw datasets, state and checkpoints
  prices_json/                 # generated partitioned histories (gitignored)
Inflations/
  Codes/                       # inflation and hunger-threshold calculators
  Datas/                       # generated reports and detail stores
.github/workflows/              # eight scheduled scraper jobs
scripts/                        # data consolidation and bounded source checks
logs/                           # operational scraper logs
docs/                           # scraping, site analysis and inflation docs
SCRAPER_TIMETABLE.md             # daily automation schedule
```

## Requirements

- Python 3.10+ (individual GitHub workflows use Python 3.10–3.12)
- Browser/Chrome dependencies for Selenium, SeleniumBase, undetected-chromedriver and Camoufox scrapers
- Git and GitHub CLI only when working with repository history/releases

## Install

Using uv:

```bash
uv sync
```

Or pip:

```bash
python -m pip install -r requirements.txt
```

Some source-specific workflows intentionally install a smaller pinned dependency set; see `.github/workflows/` and each scraper's README.

## Run scrapers

```bash
# Market
python InflationItems/Codes/Markets/Gurmar/gurmar_scraper.py

# Construction market
python InflationItems/Codes/ConstructionMarkets/yapimaks/scraper.py

# Retail browser scraper
python InflationItems/Codes/Technology/scraper.py

# Rental scraper
python -m InflationItems.Codes.HousesRent.Emlakjet.scraper --resume
```

Before running a protected or browser-backed scraper, read:

- `docs/scraping-wiki/README.md`
- `docs/APPROACH.md` for rental acquisition
- the source-specific README/agent instructions

Use bounded options first and inspect the generated CSV/checkpoint/log outputs.

## Run inflation calculations

```bash
# National basket
python Inflations/Codes/turkey_inflation.py

# Examples
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h
python Inflations/Codes/ConstructionSuppliesMarkets/yapimaks/yapimaks_inflation.py -h
python Inflations/Codes/EpeyKatfg/monthly_inflation.py
```

Methodology:

- `Inflations/Codes/turkey_inflation_methodology.md`
- `Inflations/Codes/Hungerthresholds/hunger_threshold_methodology.md`
- calculator-specific READMEs under `Inflations/Codes/`

## Automation

Eight GitHub Actions workflows collect data daily. See `SCRAPER_TIMETABLE.md` for UTC/Istanbul times, scripts and outputs.

Workflows run on `ubuntu-latest`, commit only their data/log paths and use `[skip ci]` on automated data commits.

## Publish data to the web application

The web repository consumes data through external paths:

- `INFLATION_DATA_ROOT` → raw CSV root
- partitioned JSON directory → SQLite build input
- `EPEYKATFG_MONTHLY_CSV` → generated monthly inflation artifact

The data repository does not own the runtime SQLite database. The web repository builds and deploys it from published artifacts. See `docs/DATA_PUBLICATION.md` and the web repository's `docs/DATA_CONTRACT.md`.

## Documentation

- `docs/README.md` — documentation index
- `docs/ARCHITECTURE.md` — scraper → raw data → inflation → publication flow
- `docs/GETTING-STARTED.md` — installation and first run
- `docs/DEVELOPMENT.md` — development workflow
- `docs/CONFIGURATION.md` — secrets and source configuration
- `docs/INTEGRATIONS.md` — retailer/service sources
- `docs/APPROACH.md` — rental acquisition strategy
- `docs/TECH-STACK-SEARCH.md` — scraper technology registry
- `docs/DATA_PUBLICATION.md` — artifacts consumed by the web repository
- `docs/scraping-wiki/` — local anti-bot/scraping knowledge base
- `docs/site-analysis/` — source reconnaissance and captured evidence

## Testing policy

Scrapers are verified by bounded live use and inspection of their real outputs. Do not add mock/synthetic scraper tests. Calculator changes should use small real-data runs and output inspection.

## License

Personal research mirror for inflation-study purposes.
