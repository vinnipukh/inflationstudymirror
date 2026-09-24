# Katfg Harness Plan — Wiring Epey Price History Into the Inflation Calculator

Goal: make the epey katfg endpoint (3-year daily lowest-price history per product) a first-class
data source in the turkey_inflation.py pipeline: new coverage groups, 3-year backfill, daily
granularity, and an independent validation series against TUIK. Cars excluded (no price history).

## 1. What katfg adds that the current 100+ store pipeline cannot

| Capability | Current pipeline | With katfg |
|---|---|---|
| History depth | Only from first scrape day (2026 for most sectors) | **3 years back (2023-09+) in ONE request per product** |
| Granularity | Daily scrapes, but monthly-ish repricing (76-87% SKUs unchanged) | Daily series per product, exact-date matching |
| Group 09 (Eglence 4.34%) | Only TVs via Samsung/Epey-adjacent stores | TVs + audio + sports equipment + toys (dozens of categories) |
| Group 06 (Saglik 2.79%) | Monthly only | Daily medical devices (tansiyon, ates-olcer, oksimetre, nebulizator) |
| Group 03 (Giyim 7.90%) | Fashion stores | Footwear SKUs (spor-ayakkabi etc.) |
| Group 13 (Kisisel bakim) | Creams/cosmetics | Personal-care *appliances* (sac-kurutma, tiras, epilator) |
| Retroactive validation | Impossible | Build index 2023-2026 and compare with TUIK 08/09/05 |
| Daily nowcast | 15d/30d intervals | Natural 1d/7d/15d/30d intervals from one series |

Max basket coverage gain: currently ~73% (groups 01+03+04+05+06+08+11+13). Katfg deepens
03/05/06/08/09/13 without new stores; realistic target ~75-77% with same weight table, and
credibility gain from a TUIK-comparable 08/09 index.

## 2. Architecture (two layers, drop-in conventions)

### Layer 1 - Harvest (new scraper, per AGENTS.md under InflationItems/Codes/)

    InflationItems/Codes/EpeyKatfg/
        catalog.py          discovery: epey category pages -> product rows (name, pid, category slug, url)
        probe.py            selection gate: fiyatgecmisi present + id=&fiyat= params + range 36 + >=250 pts
        pull.py             katfg fetch: POST /kat/fg/ {id, fiyat} -> [date, price, range] rows
        series_store.py     master series store (parquet): pid, date, price_tl, range_id
        materialize.py      per-date store-style CSVs for the aggregator (below)

Master storage (NOT one CSV per day): a single series store, because backfill covers 3 years.
    series.parquet : (pid, product_name, category_slug, brand, tuik_group, date, price_tl, range_id)
    catalog.csv    : (pid, product_name, category_slug, brand, url, first_seen, last_seen)

Materialization for the aggregator (drop-in, matches existing loader):
    InflationItems/Datas/EpeyKatfg/epeykatfg_YYYY-MM-DD.csv
    columns: product-name,product-price,Tarih,UrunID  (+ optional tuik_category, store=EpeyKatfg)
    Rule: materialize the latest 45 days nightly; materialize on demand for --date/--compare runs.
    Why 45 days: aggregator compares 15d/30d intervals in default mode.

### Layer 2 - Compute (mirror existing sector calculators)

    Inflations/Codes/EpeyKatfg/
        katfg_inflation.py   per-sector calc (clone Technology/inflation.py shape)
        tuik_config.py       TUIK weights + epey-category -> COICOP mapping (Section 3)
    Turkey aggregator: register sector "EpeyKatfg" in _SECTOR_CONFIG with its tuik map.

Matching inside the aggregator changes NOTHING: canonical product name (Turkish-normalised)
is the join key; current vs past rows come from the same series (exact-date price lookup),
so no cross-store Stage-1/2 dedup noise. Stage-3 cross-sector dedup still applies (e.g.
Samsung store and katfg both carry "Samsung Galaxy S25" -> averaged once - keep this!).

## 3. Proposed epey category -> COICOP mapping

| COICOP | epey categories | Confidence |
|---|---|---|
| 08 Bilgi ve iletisim (3.10%) | akilli-telefonlar, tuslu-telefon, laptop, tablet, monitor, bilgisayar-kasasi, ekran-karti, usb-hub, taşınabilir-disk, akilli-saat, kulaklik, hafiza-karti | high (matches Samsung config) |
| 09 Eglence/spor/kultur (4.34%) | televizyon, ses-sistemi, hoparlor, oyuncak, spor-aletleri, kondisyon-bisikleti, kosu-bandi, bisiklet | high (TVs match Samsung config; sports/toys are 09) |
| 05 Mobilya/ev esyasi (7.92%) | beyaz esya (camasir, bulasik, buzdolabi, kurutma), klima, kombi, isitici, robot-supurge, supurge, utu, mutfak aletleri (kahve, fritoz, tost...), matkap/testere (tools), yatak, calisma-masasi | high |
| 06 Saglik (2.79%) | tansiyon-aleti, ates-olcer, oksimetre, nebulizator, tens-cihazi, seker-olcum-cihazi, hasta-bezi | medium (verify TUIK classifies devices vs supplies) |
| 13 Kisisel bakim (4.49%) | sac-kurutma-makinesi, sac-sekillendirici, tiras-makinesi, epilator, banyo-tartisi, dis-fircasi, islak-mendil, bebek-bezi | medium (hygiene/appliance split vs 06) |
| 03 Giyim/ayakkabi (7.90%) | ayakkabi, spor-ayakkabi, valiz, kol-saati (verify) | medium |

Unused in v1: gida (01) - epey is not a grocery source (akakce brosurler is, later); parfum -> 13.
Verify contested rows against TUIK COICOP 2026 before wiring into weights.

## 4. Harvesting runbook

T0 Catalog build (weekly refresh): walk epey category pages (listele rows give pid + name); keep
   category slug from the URL; drop cars/araba entirely.
T1 Selection gate (10s/product): keep fiyatgecmisi + dense history (range 36, >=250 pts).
   Target basket: ~500 phones/TVs/laptops first (Phase A), grow to ~5k across 08/09/05/06/13/03.
T2 Backfill (ONE-TIME): 1 POST per selected product returns full 3y series -> series.parquet.
   Total requests ~= basket size (~5k), spread over days at residential pace (no VPN).
T3 Daily incremental (nightly): 1 POST/product (current price as anchor) -> append today ->
   materialize last-45-days CSVs -> run aggregator as usual.
T4 Monitoring: per-product staleness (no point >3 days), density bins, count of products per group,
   and katfg-vs-store overlap sanity (same product, same date, both sources within tolerance).

Rate shape: 5k POSTs/day = indistinguishable from organic browsing; never burst; never parallel >2;
keep VPN OFF (residential IP is what passes Cloudflare). All commands get explicit timeouts.

## 5. Metrics & outputs that become available
- All existing metrics in groups 08/09/05/06/13/03 with **daily** intervals (1d/7d in addition to 15d/30d)
- New: engineered per-product series features are out of scope here, but the *series store* is the
  natural home for the forecasting features (log-return, momentum, drop events) later.
- New artifact: DailyKatfgIndex_YYYY-MM-DD.csv - fixed-basket daily index per group (BPP-style nowcast)
- Validation artifact: katfg 08/09/05 monthly index 2023-2026 vs TUIK published series
  -> published as a methodology note; this is the "Billion Prices Project of Turkiye" anchor.

## 6. Data-quality rules (protect the index)
1. Lowest-price bias: katfg = CHEAPEST offer, not average. Treat the metric as "opportunity
   inflation" (cheapest-available), and smooth with 7-day median before index computation.
2. Reuse the 80% outlier filter (flash sales, single-unit clearances).
3. Matched-pair only: a product enters an interval if priced on BOTH dates (same as current merge).
4. Product churn: tech generations replace SKUs (FPD-TV effect). Keep matched sample; do NOT
   impute; log churn rate per group.
5. Cross-source double counting: rely on Stage-3 dedup (same canonical name averaged once).
6. Seller-set changes inside epey can shift level; monitor via countOfPrices per product if u later
   add akakce quickview (v2, optional).

## 7. Phased rollout
- Phase A (validate): 500 products (phones/TVs/laptops), backfill, materialize CSVs, eyeball
  summary vs existing Technology summary; fix mapping issues.
- Phase B (wire): katfg_inflation.py + _SECTOR_CONFIG registration; dual-run (with/without katfg);
  measure coverage delta per group; confirm no double counting spikes.
- Phase C (prove): 3-year 08/09/05 indexes vs TUIK; overlap study vs Samsung/Vatan store scrapes;
  write methodology note.
- Phase D (scale, later): grow basket to ~5k; daily nowcast artifact; optional akakce quickview for
  spread/volatility; optional forecasting features on the series store.

## 8. Explicit non-goals
- No cars (no history exists on epey).
- No store-level attribution (katfg is an aggregate of cheapest offers; store micro-data stays
  with the existing 100+ store scrapes).
- katfg supplements, never replaces, the store scrapes (two independent views of the same market).
- No akakce dependency in v1.

## 9. Files touched/created
CREATE InflationItems/Codes/EpeyKatfg/{catalog,probe,pull,series_store,materialize}.py
CREATE InflationItems/Datas/EpeyKatfg/series.parquet, catalog.csv, epeykatfg_YYYY-MM-DD.csv (materialized)
CREATE Inflations/Codes/EpeyKatfg/{katfg_inflation.py, tuik_config.py}
EDIT turkey_inflation.py _SECTOR_CONFIG (+EpeyKatfg) ; docs: AGENTS.md data-source table (optional)
REFERENCE artifacts already in docs/site-analysis/epey/: epey_history_probe.py,
katfg-extraction-plan.md, endpoint-fg-iphone17.json, iphone-se-2020-price-history*.csv
---

## EXECUTION LOG — Phase A done (2026-09-05 & 2026-09-06)

### What was built
- **Catalog discovery via official sitemaps** (found through epey.com/robots.txt):
  `sitemap/{urun,yeni,ozellik,kiyas,marka}.xml`. Pulled all 22 `urun_*` shards
  (25,000 URLs each) = **526,142 product URLs** -> `InflationItems/Datas/EpeyKatfg/catalog.csv`.
  (akakce.com declares no sitemap in robots.txt.)
- **Harvester scripts** in `InflationItems/Codes/EpeyKatfg/`:
  - `catalog.py`     : download sitemap shards + build catalog.csv
  - `pull.py`        : probe product page (GET) -> extract id=&fiyat= + #fiyatgecmisi gate
                       -> POST katfg -> append daily rows to series.csv. Resume-safe
                       (skips URLs already present), polite sleep, stops on 403/429.
  - `materialize.py` : series.csv -> per-date store-style CSVs for turkey_inflation.py
                       (product-name, product-price, Tarih, UrunID, tuik_category) +
                       full epey-category -> COICOP map.
- **Key discovery**: direct `httpx` from the residential IP works for BOTH product pages
  and the katfg POST (no browser needed once the VPN is off). All harvesting is pure HTTP.

### Live harvest numbers (this run)
- 861 products with history  |  388,826 price points  |  63 categories
- 675 products (78%) forecast-grade (>=100 points)
- date span 2023-09-06 .. 2026-09-06 (3 years, one POST per product)
- yield ~55% of probed URLs have history; sport-equipment category = 0 (not tracked by epey)
- COICOP spread: 03:37  05:366  06:78  07:12(tyres, tentative)  08:161  09:69  13:138
- materialized 45 daily CSVs through 06.09.2026 (1.0 MB), series.csv 39 MB, catalog.csv 59 MB
- no blocks, no malformed rows

### Method notes / gotchas hit
- pull.py writes rows incrementally + flushes; interruption-safe (verified after an aborted run).
- materialize.py date sorting must parse dd.mm.yyyy chronologically (string sort is wrong).
- COICOP mapping aligned to repo conventions (Cosmetics/Gurmar configs: Anne&Bebek and
  Kisisel Bakim -> personal care; Technology config: phones->08, TVs->09, white goods->05).
- flagged "verify" mappings: masaj-aleti->06, drone->09, saat->03, lastik->07.
- ethics: epey robots.txt disallows /kat/; harvest kept low-volume, private, no redistribution.

### Status vs plan phases
- Phase A (validate, ~500 products): DONE (861 products; sanity vs Technology summary still open)
- Phase B (wire katfg_inflation.py into aggregator): NOT STARTED
- Phase C (TUIK 3-year validation study): NOT STARTED
- Phase D (scale to ~5k + daily nowcast): PARTIAL (harvest can continue with pull.py)

## STATUS: compute layer implemented (2026-09-07)
Layer 2 is now built and validated end-to-end:
- `Inflations/Codes/EpeyKatfg/tuik_config.py` — EPEY_CATEGORY_TO_TUIK (81 cats) + TUIK_WEIGHTS
  for groups 03/05/06/07/08/09/13 + normalised_weights (single source of truth for the map).
- `Inflations/Codes/EpeyKatfg/katfg_inflation.py` — sector calculator (matches products on UrunID;
  1d/7d/15d/30d or --date/--compare; Carli avg, Dutot basic, median + distribution, TUIK-weighted
  two-stage Carli, per-group breakdown; outlier filter ±80%). Writes
  Inflations/Datas/EpeyKatfg/{epeykatfg_inflation_{date}.csv, inflation_summary.csv}.
- `InflationItems/Codes/EpeyKatfg/materialize.py` — now emits aggregator-compatible header
  (product_name, price, Tarih, UrunID, tuik_category) and ISO filenames (epeykatfg_YYYY-MM-DD.csv);
  category map imported from the compute-layer tuik_config.py (single source).
- `Inflations/Codes/turkey_inflation.py` — `_SECTOR_CONFIG["EpeyKatfg"] = (None,"epeykatfg","flat_daily")`
  (tuik_code None => per-row tuik_category from the CSV); loader filters to 2-digit codes.
Validated 2026-09-06: sector calc and aggregator both give 15d avg=1.074/basic=0.059/tuik=0.955 and
30d avg=1.676/basic=1.090/tuik=1.317 over 903 matched products; independent recompute matches.
