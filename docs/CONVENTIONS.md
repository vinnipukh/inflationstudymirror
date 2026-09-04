---
last_mapped: 2026-09-02
focus: conventions
---

# Conventions

## Repository Organization

- Ingestion scripts live under `InflationItems/Codes/` organized by market domain.
- Raw scraped CSV data lands under `InflationItems/Datas/` organized by market domain.
- Inflation calculation scripts and weighting configuration live under `Inflations/Codes/`.
- Processed inflation output CSVs land under `Inflations/Datas/`.
- Hexagonal core, domain models, and Falcon REST API backend live under `inflation_dashboard/`.
- Production frontend lives in `frontend/` (Svelte 5 / SvelteKit static SPA) and consumes the Falcon API over HTTP (see `docs/FALCON_API_CONTRACT.md`).
- Legacy Streamlit dashboard lives in `streamlit_app.py` and is kept for administrative/prototype use.
- The Svelte dashboard (`frontend/`) blanks the pipeline's `Uncategorized` fill-in label (`—`) in product tables; it is not a real category (sources like Gurmar/HomeGoods write no category column). Coverage diagnostics keep the raw label.
- Documentation, architecture, and scraping knowledge base live under `docs/`.

## General Style

- Source-specific scrapers keep constants at the module level, helper functions next, and a `main()` / CLI entrypoint at the bottom.
- Turkish comments, log messages, and domain terms are standard across scraper and inflation scripts.
- Modern scripts use `pathlib.Path` with explicit traversal depths (e.g. `Path(__file__).resolve().parents[3]`).

## Testing Principle

- **No unit tests or smoke tests for scrapers**: Per `AGENTS.md`, scraper code under `InflationItems/Codes/` carries no unit tests, mocks, or synthetic HTML fixtures. Verification is performed by bounded live runs (e.g. `--limit`, `--start-url`), scheduled runs, and checking generated CSVs/logs.
- **Backend & Dashboard**: Hexagonal domain models, Falcon API routes, and cache boundaries are verified using dedicated verification scripts in `scripts/`.

## CSV Handling

- CSV encodings standardise on `utf-8-sig` for UTF-8 compatibility with Excel.
- Separators vary by retailer (comma or semicolon). Robust parsers check both or use `sep=None`.
- Historical dates are extracted from filenames using date regexes rather than row timestamps.

## Price Normalization

- Prices in raw sources appear in various formats (`1.250,00 TL`, `1250.00`, `1.250,00 ₺`).
- Domain normalization is unified in `inflation_dashboard.domain.prices.normalize_price`.
- Calculated inflation metrics ensure product identities match across snapshots before computing percentage changes.

## Error Handling & Signal Flow

- Network retries use exponential backoff with jitter on 429/5xx status codes.
- Scrapers avoid writing empty rows when requests fail; previous snapshot values are carried forward with stale timestamps.
- Rental scrapers use explicit signals (`SkipCitySignal`, `SkipBracketSignal`, `ChallengeDetected`) rather than blind retries on bot walls.
