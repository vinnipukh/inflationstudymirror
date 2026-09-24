# Repository Separation

The former monorepo has been split into two local repositories.

## Data repository

`E:\Projects\inflationstudymirror`

Contains:

- `InflationItems/`
- `Inflations/`
- scraper workflows/logs
- data-only scripts
- scraper/site-analysis/inflation documentation

## Web repository

`E:\Projects\inflationstudymirror-web`

Contains:

- `frontend/`
- `inflation_dashboard/`
- Falcon server/database/benchmark scripts
- web API/database/deployment documentation
- ignored runtime `data/` mount

## Boundary

The web repository consumes external data paths:

- `INFLATION_DATA_ROOT`
- `PRICES_DB_PATH` after the web repository builds its database
- `EPEYKATFG_MONTHLY_CSV`

No web code, API dependency, frontend package or committed SQLite database should return to the data repository.

## Git history

The original repository history remains in the data repository. The sibling web repository is a clean extracted snapshot and should receive its own remote/history after review. Historical monorepo and Streamlit planning documents are archived in the web repository under `docs/archive/`.
