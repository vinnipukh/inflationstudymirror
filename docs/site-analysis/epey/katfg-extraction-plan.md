# epey /kat/fg/ — Extraction Plan (what to take, how to keep it)

> Scope: consumer-goods categories ONLY (electronics, white goods, kitchen, home,
> personal care, baby, toys, tools). Cars/listings excluded (no price history exists).

## 1. What the endpoint returns (verified on iPhone SE 2 2020)

POST /kat/fg/  body: id=<productId>&fiyat=<currentLowestPrice>

Response = JSON array of [date "dd.mm.yyyy", price "x.xx" TL, range_id]:
  range 36 -> 3-year window    range 12 -> 1-year window    range 6 -> 6-month window
  Windows are CONTIGUOUS, non-overlapping, and each ends at "now" for its own depth:
    36mo: 2023-09-06 .. 2025-09-05 (719 pts)  12mo: 2025-09-06 .. 2026-03-05 (180 pts)
    6mo:  2026-03-06 .. 2026-09-05 (176 pts)  => concatenated = 1,075 unique days
  No other metadata is returned (no name/brand/specs) - that must come from elsewhere.

## 2. Product-selection gate (do NOT fetch everything)

Before fetching full history, probe each candidate product page (cheap, see
epey_history_probe.py):
  keep   if page has <div id="fiyatgecmisi"> AND inline id=...&fiyat=... params
  skip   if absent (brand-new, out-of-stock-only, or non-retail page)
  prefer products with range 36 present and >= ~250 points total (deep, dense history)

Catalog discovery (product IDs + names): category pages via /kat/listele/ product rows
(checkbox id "urun<pid>"), or akakce category API (prCode + hasGraph flag) as a second index.

## 3. Storage schema (idempotent daily upserts)

products(pk pid, slug, name, category_code, category_name, brand, release_year,
         specs_json, url, first_seen_on, last_seen_on)
price_points(pk pid+date, pid, date, price_tl, range_id, fetched_at)   -- one row per product-day
offers_snapshot(optional; from product page/quickview: pid, date, count_of_sellers,
                count_of_offers, min_price_tl, max_price_tl)          -- supply/competition + spread

Conventions:
  - store price as NUMERIC(12,2) in TL, keep original decimal point (comma->dot)
  - date as ISO yyyy-mm-dd; range_id int (36/12/6)
  - upsert on (pid, date): later fetches never duplicate or corrupt history
  - keep fetched_at to detect stall/regression of the source

## 4. Daily pipeline (low volume = survival)

1. Nightly: for each tracked product, POST /kat/fg/ with CURRENT price (read from the
   product page or your last min price; the endpoint uses it as today anchor).
2. Insert/update price_points; compute derived features (below).
3. Weekly: re-discover category pages for new products (add to gate probe).
4. Monthly: refresh products.specs_json and offers_snapshot (seller counts drift).

Rate shape: 1 POST/product/day. For ~5k tracked products that is 5k requests/day,
indistinguishable from organic traffic - no burst, no parallel fan-out, and never hammer
a single category. Keep VPN OFF (datacenter IPs are what trigger Cloudflare).

## 5. What to derive per product (forecasting features, literature-backed)

From the raw series, compute and store daily:
  log_return = ln(p_t / p_{t-1})                       -> model target
  volatility_7d / 30d  (std of log returns)           -> risk/bandwidth feature
  momentum_7d / 30d / 180d (% change)                 -> trend feature
  distance_to_hmin / hmax (current vs rolling min/max) -> reversion feature
  drop_event (flag when daily change <= -5%, +pct)    -> "biggest sale" event log
  day_of_week, month, campaign proximity (11.11, Black Friday, year-end, Ramadan)

Joined features (from other scrapes you already planned):
  product_age = today - release_year                    -> lifecycle decline (FPD-TV paper)
  seller_count / offer_count (offers_snapshot)          -> competition proxy
  review count & rating (product page)                  -> sentiment feature (Carta 2018)
  USD/TRY + TCMB CPI (external)                         -> detrend nominal TL prices
  Google Trends for the product term (if you add it)    -> demand signal (Carta 2018)

## 6. Pitfalls & honest limits
- The series is the LOWEST price, not average: no spread/volatility across vendors from
  this endpoint alone (get that from akakce quickview or epey offer blocks).
- Nominal TL drifts with inflation: model log-returns or add FX/CPI regressors;
  never treat nominal level as stationary.
- The endpoint answer changes slightly with "now"; ranges shift daily, so FULL history
  is only complete once you have pulled for consecutive days - a single pull gives you
  the backfill (3y) but you must keep pulling to extend it forward.
- fiyat param must be current; if stale it only shifts the anchor point, data is safe.
- Density varies by product (J2 had 50 pts in its 12mo window) - bin products by density
  and only ship forecast features above a minimum N (e.g. >=100 points).

## 7. Deliverables check
- Existing: test-fg-iphone-se-2020.json (raw), iphone-se-2020-price-history.csv (all points),
  iphone-se-2020-price-history-daily.csv (clean daily), test-analyze-iphone-se-2020.json
  (stats), epey_history_probe.py (selection gate).