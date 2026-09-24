# Site Analysis: Epey.com & Akakce.com — Master Index

Prepared: 2026-09-05. Detail per site: `epey/NOTES.md`, `akakce/NOTES.md` (this folder).
Raw captures: `epey/endpoint-*.html`, `epey/endpoint-fg-*.json`, `akakce/api-*.json`,
`screenshots/` (page snapshots), `*-text.txt` (full page text dumps), `home-links.json`.

## What both sites do
Turkish price-comparison aggregators. They crawl **retailer product pages** (Trendyol,
Hepsiburada, n11, PTT AVM, Amazon.com.tr, MediaMarkt, Teknosa, Vatan, Pazarama…), normalize
product variants (color/size/GB), and show:
- cheapest price + all offers per product ("N satıcı, N fiyat")
- price history (daily lowest price)
- price-drop detection & ranked deal lists (% drop, gaps, 6-month cheapest)
- product specs tables, compare wizards, store + brand + brochure pages, reviews
- price alarms ("Alarm Kur"), favorites (account-gated)

## Architecture comparison
| | epey.com | akakce.com |
|---|---|---|
| Anti-bot | Cloudflare; Camoufox passes | Cloudflare; **residential IP required** (VPN IP hard-blocked) |
| Rendering | PHP SSR + jQuery AJAX fragments | PHP SSR + React islands + SPA |
| State in URL | base64 PHP-serialized `/e/<b64>` | numeric path segments `,<cat>,<sort>` |
| AJAX API | jQuery `.load()` POST endpoints | **public JSON REST API** `api6.akakce.com` |
| Price history | JSON POST `/kat/fg/` (open!) | image/JSONP `akakce-g.akamaized.net` (no JSON) |
| Sort keys | global spec IDs (screen=1, RAM=14…) | numeric sort codes (1 popular, 2 price…) |
| Facets | filter IDs per group (marka/ozel/ozellik) | numeric filter IDs per group (Apple=134091…) |
| Ads | sponsored rows in feed ("Reklam", promos) | ribbons/banners in API + `hasSpotCampaign` flag |

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

### akakce (all GET, JSON)
- `/category/ctQueryWithFilterAndHpl?ctCode&page&sort&filterIds&isFilterRequest` — category catalog
- `/quickview/get?prCode` — live store prices per product
- `/dl/dlquery/?PrSetId&Sort&Page` — deal lists (PrSetId per list: 180245 droppers, 116343 gaps, 54312 6mo, 25407 bulk, 126546 used)
- `/autocomplete?q` — search suggest
- `/user/...` — account alarms/favorites (login)
- `/store/...`, `/product/compare/more`, `/category/filter`, `/make/productlist` (env-declared)
- `/j/l/f/?c&f&ct` — lightweight client filter
- graph: image/JSONP `akakce-g.akamaized.net/<prCode>:<variant>:<v>`

## Can the same data be sourced independently? — YES (both sites are just aggregators)
1. **Retailer offers**: crawl each retailer's own site (sitemaps/product pages). Akakce/epey deep links and quickview URLs expose the exact retailer product URLs (popular models only).
2. **Price history**: none exports bulk history (epey JSON is per-product; akakce graph is image-only). A daily snapshot crawler over retailer pages rebuilds the history legally.
3. **Specs**: manufacturer official pages; compare tables confirm normalization (e.g. "6.3 İnç", "256 GB").
4. **Flyers/brochures**: retailers publish own PDFs (A101, BİM, Şok, CarrefourSA…).
5. **Forecast/drop %**: derive from your own series (max/min/median over window).
6. **Inflation context**: TCMB public API.

## Honest assessment for the user's open-source clone
- **Both designs are replicable** from the endpoint maps; akakce's JSON API is the most clone-able model (clean REST, structured data, facet ids — a great blueprint for a public API of your own platform).
- **The real moat is data acquisition**, not design: both sites win by crawling thousands of products daily. Your platform needs an equivalent crawler + scheduler + normalization pipeline (this repo already has scraper infrastructure under `InflationItems/Codes/`).
- **Bias sources to design against**: sponsored ribbons/campaigns, `hasSpotCampaign` products, "Reklam" feed cards, paid "Satıcıya Git" placements, promoted store rows. Your minimalist platform can simply never render them.

## Files
- `epey/NOTES.md`, `akakce/NOTES.md` — full per-site detail
- `epey/endpoint-*.html` — captured AJAX responses (listele, filtrele, ustbilgi, kiyasla, kiyaslink, fg JSON)
- `akakce/api-*.json` — captured API JSON (category, filtered, dlquery, autocomplete)
- `epey/screenshots/`, page text dumps, link JSONs

## Katfg harness (price-history harvesting for the inflation calculator)
- Plan + execution log: `docs/site-analysis/katfg-harness-plan.md`
- Harvest data: `InflationItems/Datas/EpeyKatfg/` (catalog.csv, series.csv, epeykatfg_*.csv, README.md)
- Scripts: `InflationItems/Codes/EpeyKatfg/{catalog,pull,materialize}.py`
- Epey sitemap shards (robots-declared): `docs/site-analysis/epey/sitemaps/urun_*.xml` (526,142 URLs)
- Extraction spec: `docs/site-analysis/epey/katfg-extraction-plan.md`; probe tool:
  `docs/site-analysis/epey/epey_history_probe.py`
- Literature guide (price forecasting / what to scrape): `docs/site-analysis/price-forecasting-literature.md`
