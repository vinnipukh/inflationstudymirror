# Data Publication

This document defines the artifacts produced by the data repository and consumed by the separate web repository.

## Ownership

| Artifact | Producer | Consumer |
|---|---|---|
| Raw source CSVs/state | Scrapers | Inflation calculators and optional web fallback |
| `InflationItems/prices_json/*.json` | Scraper/ETL output | Web repository SQLite builder |
| Inflation outputs under `Inflations/Datas/` | Inflation calculators | Research, reports and selected web artifact endpoints |
| Logs/checkpoints | Scraper operations | Operational review only |

The web repository owns the generated SQLite serving database. It must not be committed here.

## Partitioned JSON

Each partition is named by logical retailer and contains product entries with:

- stable product ID;
- product name and category;
- latest/min/max values;
- a sparse `prices` map keyed by ISO date.

The current representation stores price changes rather than one row per unchanged day. A consumer reconstructing a daily step series must carry the most recent event forward.

## Inflation artifacts

Generated reports must include or be accompanied by:

- generation date/source commit;
- method and comparison interval;
- matched-product and store counts;
- category mapping/weight coverage;
- output CSV path;
- known limitations.

The web repository may consume `Inflations/Datas/EpeyKatfg/monthly_inflation.csv` through `EPEYKATFG_MONTHLY_CSV`.

## Release hand-off

A practical release contains:

```text
prices_json/
inflation/
  EpeyKatfg/monthly_inflation.csv
manifest.json
```

The manifest should record:

- source repository commit;
- generated-at timestamp;
- artifact paths and sizes;
- schema version;
- checksums;
- coverage/date ranges.

## Compatibility rules

- Preserve existing JSON field names unless a versioned schema change is coordinated.
- Preserve API retailer labels in partition filenames/stems.
- Keep date keys ISO `YYYY-MM-DD`.
- Announce changes to product identity/category semantics.
- Never publish secrets, browser profiles or raw credential-bearing state.
