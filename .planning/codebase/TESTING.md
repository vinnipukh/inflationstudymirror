---
last_mapped: 2026-07-16
focus: testing
---

# Testing

## Current test posture

- No dedicated test directory or test framework configuration was found.
- No canonical `pytest`, lint, or build command is defined in `pyproject.toml` or `requirements.txt`.
- Verification so far is mostly ad-hoc: syntax checks, focused helper scripts, manual scraper runs, and generated CSV inspection.

## Existing verification patterns

- Python syntax can be checked with `python -m py_compile <file>`; this was used for `streamlit_app.py`.
- Focused helper behavior can be checked with temporary scripts under `C:/Users/arhan/AppData/Local/Temp/hermes-verify-*.py`.
- Scraper outputs are verified by row counts and CSV presence in `Datas/...` directories.
- Inflation calculators can be verified by generated detail CSVs and `inflation_summary.csv` updates under `Inflations/Datas/...`.

## CI coverage

- `.github/workflows/vakko_scraper.yml` runs the Vakko scraper on a schedule and commits data, but it is operational automation rather than a test suite.
- The workflow does not run tests or linters.

## Suggested future test targets

- Unit tests for price normalization in `streamlit_app.py::coerce_price` and fuzzy search ranking in `streamlit_app.py::rank_search_options`.
- Unit tests for CSV loaders in inflation scripts, especially delimiter fallback and missing-column behavior.
- Golden-file smoke tests for a few small sample CSVs per retailer.
- A lightweight dashboard data-loading test that caps files per retailer and confirms columns, date bounds, and numeric prices.

## Manual checks that remain important

- Scraper behavior against live websites/APIs because anti-bot and schema changes are common.
- Streamlit layout/interaction checks in browser because visual state is not covered by syntax/helper tests.
- Secret scans before committing generated docs, logs, or workflow changes.

## Risk in current state

- Without a canonical suite, regressions in scraper parsing or inflation math may only surface after bad CSVs are generated.
- Generated datasets are large, so broad tests should use small fixtures rather than scanning all tracked CSVs.
