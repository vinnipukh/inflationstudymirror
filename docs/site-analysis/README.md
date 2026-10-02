# Site Analysis: Epey.com — Master Index

Prepared: 2026-09-05. Detail: `epey/NOTES.md` (this folder).
Raw captures: `epey/endpoint-*.html`, `epey/endpoint-fg-*.json`, `epey/screenshots/`, page text dumps.

> The akakce.com analysis and the akakce crawler were moved on 2026-10-02 to the separate
> technology-archive repository (`docs/akakce_crawler/`, `src/acquire/akakce_crawler/`).

## What the site does
A Turkish price-comparison aggregator. They crawl **retailer product pages** (Trendyol,
Hepsiburada, n11, PTT AVM, Amazon.com.tr, MediaMarkt, Teknosa, Vatan, Pazarama…), normalize
product variants (color/size/GB), and show:
- cheapest price + all offers per product ("N satıcı, N fiyat")
- price history (daily lowest price)
- price-drop detection & ranked deal lists (% drop, gaps, 6-month cheapest)
- product specs tables, compare wizards, store + brand + brochure pages, reviews
- price alarms ("Alarm Kur"), favorites (account-gated)

## Architecture
- Anti-bot: Cloudflare; Camoufox passes
- Rendering: PHP SSR + jQuery AJAX fragments
- State in URL: base64 PHP-serialized `/e/<b64>`
- AJAX API: jQuery `.load()` POST endpoints
- Price history: JSON POST `/kat/fg/` (open!)
- Sort keys: global spec IDs (screen=1, RAM=14…)
- Facets: filter IDs per group (marka/ozel/ozellik)
- Ads: sponsored rows in feed ("Reklam", promos)

## Endpoint map
### epey (all POST, form-encoded)
- `/kat/listele/` — product list fragment (kategori_id, cerez, limit, sirala|sayfa|filtrele[])
- `/kat/filtrele/` — facet sidebar fragment (kategori_id, cerez, filtrele[])
- `/kat/ustbilgi/` — h1 + sort dropdown (kategori_id, elink=<b64>)
- `/kat/kiyasla/` — compare tray add/remove (kategori_id, cerez, kiyasla=<pid>, islem)
- `/kat/kiyaslink/` — per-row compare count (kategori_id, cerez, urun_id)
- `/kat/fg/` — **price history JSON**: `id=<pid>&fiyat=<price>` → `[["dd.mm.yyyy","price",range],…]`
- `/kat/yorumpuanla/` — review vote; `/uye/*` — account (reviews, favorites, filters/alerts)
- `/ara/` — search redirect

## Can the same data be sourced independently? — YES (the site is just an aggregator)
1. **Retailer offers**: crawl each retailer's own site (sitemaps/product pages). Epey deep links expose the exact retailer product URLs (popular models only).
2. **Price history**: epey does not export bulk history (its JSON is per-product). A daily snapshot crawler over retailer pages rebuilds the history legally.
3. **Specs**: manufacturer official pages; compare tables confirm normalization (e.g. "6.3 İnç", "256 GB").
4. **Flyers/brochures**: retailers publish own PDFs (A101, BİM, Şok, CarrefourSA…).
5. **Forecast/drop %**: derive from your own series (max/min/median over window).
6. **Inflation context**: TCMB public API.

## Honest assessment for the user's open-source clone
- **The design is replicable** from the endpoint map.
- **The real moat is data acquisition**, not design: the site wins by crawling thousands of products daily. Your platform needs an equivalent crawler + scheduler + normalization pipeline (this repo already has scraper infrastructure under `InflationItems/Codes/`).
- **Bias sources to design against**: sponsored ribbons/campaigns, `hasSpotCampaign` products, "Reklam" feed cards, paid "Satıcıya Git" placements, promoted store rows. Your minimalist platform can simply never render them.

## Files
- `epey/NOTES.md` — full detail
- `epey/endpoint-*.html` — captured AJAX responses (listele, filtrele, ustbilgi, kiyasla, kiyaslink, fg JSON)
- `epey/screenshots/`, page text dumps, link JSONs

## Katfg harness (price-history harvesting for the inflation calculator)
- Plan + execution log: `docs/site-analysis/katfg-harness-plan.md`
- Harvest data: `InflationItems/Datas/EpeyKatfg/` (catalog.csv, series.csv, epeykatfg_*.csv, README.md)
- Scripts: `InflationItems/Codes/EpeyKatfg/{catalog,pull,materialize}.py`
- Epey sitemap shards (robots-declared): `docs/site-analysis/epey/sitemaps/urun_*.xml` (526,142 URLs)
- Extraction spec: `docs/site-analysis/epey/katfg-extraction-plan.md`; probe tool:
  `docs/site-analysis/epey/epey_history_probe.py`
- Literature guide (price forecasting / what to scrape): `docs/site-analysis/price-forecasting-literature.md`
