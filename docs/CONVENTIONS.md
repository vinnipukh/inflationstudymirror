# Conventions

## Repository organization

- Scraper code lives under `InflationItems/Codes/`, grouped by market domain and source.
- Raw source data lives under `InflationItems/Datas/`.
- Inflation calculators and TÜİK mapping live under `Inflations/Codes/`.
- Generated inflation outputs live under `Inflations/Datas/`.

## Scraper implementation

- Keep source-specific constants and helpers near the scraper.
- Provide a CLI/main entrypoint with bounded-run options where practical.
- Use explicit schema checks and deterministic extraction for known sources.
- Use exponential backoff with jitter for transient 429/5xx failures.
- Do not write empty replacement rows when a refresh fails; preserve the last known observation where source policy allows.
- Use challenge/block signals rather than blind retry loops for anti-bot interstitials.

## Data

- Prefer UTF-8 with BOM (`utf-8-sig`) for CSV interchange with Excel.
- Accept documented delimiter variation rather than silently misparsing it.
- Extract observation dates from filenames where that is the source convention.
- Preserve source-specific column names; normalize only in downstream calculations.
- Do not commit secrets, browser profiles, SQLite databases or transient checkpoints.

## Inflation calculations

- Match product identities consistently across compared dates.
- Make weights/category mappings explicit and versioned beside calculators.
- Document formula changes and output-schema changes.
- Keep incomplete basket/threshold periods explicit rather than imputing silently.

## Testing

- No mock/synthetic tests for scrapers. Verify by bounded live use and real output inspection.
- Use small real-data runs for calculator changes unless the user requests another approach.
