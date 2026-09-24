# EpeyKatfg — scraped epey price-history dataset

Source: epey.com katfg endpoint (POST /kat/fg/, robots-disallowed path - personal research use,
low volume). Catalog from official sitemaps (sitemap/urun_*.xml, 526,142 product URLs).

## Files
- catalog.csv        full product catalog: category, slug, url (from sitemaps)
- series.csv         master series: url, category, pid, date(dd.mm.yyyy), price_tl, range_id
- README.md          this file

The old per-date snapshots (epeykatfg_YYYY-MM-DD.csv) were retired on 2026-09-07:
all 1,084 files are archived in /epeykatfg_daily_csvs.zip (gitignored).  Nothing
reads them anymore — the calculators read series.csv directly via
Inflations/Codes/Epeykatfg/katfg_reader.py (same min-price-per-pid/date collapse that
materialize.py used), and the JSON store below is the long-term storage.

## Canonical price store (partitioned JSON, replaces per-day snapshots for long-term storage)
- InflationItems/prices_json/EpeyKatfg.json  single file, one entry per product (keyed by pid):
                     name, category (epey slug), latest/min/max price, and a SPARSE
                     change-only "prices" map {YYYY-MM-DD: price}. A date is written only
                     when the price differs from the previously recorded value; the price on
                     any day is the most recent key <= that day (lossless step series).
- Built/updated by InflationItems/Codes/EpeyKatfg/build_prices_json.py from series.csv
  (min price per pid/date); materialize.py calls it after every pull, so nightly pulls
  append only new change events. Legacy per-date CSVs are opt-in via materialize.py --csv.
- Sizes: old per-day CSVs 962,441 rows / 50.4 MB across 1,084 files vs 168,778 change
  points / 4.7 MB single file (5.7x fewer rows). Verified lossless on all points.
- Consumed by scripts/build_sqlite_from_json.py (retailer "EpeyKatfg") like every other
  retailer partition (dashboard/product browsing). The inflation calculators read the
  dense master (series.csv via katfg_reader.py) instead, because sparse change-only
  points cannot express which days a product was actually observed.

## Harvest stats (updated 2026-09-07)
- products with history: 2,134  (Phase-1 list: 1,273 pulled of 1,920 candidates, 66% yield;
  647 candidates skipped - no price history on epey)
- forecast-grade (>=100 pts): 1,680 (79%)
- total price points:     983,574
- date span:              2023-09-06 .. 2026-09-06
- categories:             74
- COICOP spread:          {'03': 74, '05': 767, '06': 206, '07': 22, '08': 608, '09': 159, '13': 298}
- candidate list:         urls_phase1.txt (1,920 urls, fully processed; re-usable for nightly pulls)

## Notes
- Price = epey's daily LOWEST offer ("opportunity" price), nominal TL.
- range_id: 36/12/6 = contiguous 3yr/1yr/6mo windows; concatenate to rebuild full series.
- Density varies per product; filter >=100 points for forecasting/index work.
- Continue harvesting: python InflationItems/Codes/EpeyKatfg/pull.py urls.txt series.csv
- Materialize for aggregator: python InflationItems/Codes/EpeyKatfg/materialize.py
- Ethics: epey robots.txt disallows /kat/; keep volume low, private research only, no wholesale
  redistribution. Derived/aggregated outputs only.
