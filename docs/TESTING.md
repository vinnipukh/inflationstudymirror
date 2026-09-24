# Testing and Verification

## Scraper policy

There are no unit tests, mock tests, synthetic HTML fixtures or one-off smoke tests for code under `InflationItems/Codes/`.

Verify a scraper by using it:

1. Inspect `--help` and source configuration.
2. Run the smallest practical live scope (`--limit`, `--start-url`, one city/district/category, reduced page budget).
3. Check exit status and logs.
4. Inspect the generated CSV headers, row counts, dates, identifiers, prices and duplicate behavior.
5. Check checkpoint/state behavior if the scraper supports resume.
6. Run a larger/scheduled scope only after the bounded run is correct.

Do not commit a verification script merely to avoid running the scraper.

## Inflation policy

For calculator changes:

- use a small real date range first;
- run the relevant calculator;
- inspect detail and summary schemas;
- compare counts, coverage and headline metrics;
- update methodology when formulas/mappings change.

No repository-wide coverage threshold is claimed.

## Static checks

For non-behavioral Python edits, syntax compilation is useful:

```bash
python -m py_compile path/to/file.py
```

Syntax compilation is not a substitute for running a scraper.

## Scheduled verification

GitHub Actions schedule success only proves that the job completed. Inspect changed data/log artifacts and source-specific integrity output before trusting a snapshot.
