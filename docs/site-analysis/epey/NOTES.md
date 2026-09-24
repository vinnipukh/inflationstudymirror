# Epey.com — Site Analysis Notes

> Investigated: 2026-09-05 via Camoufox stealth browser (Cloudflare-bypassed).
> Purpose: feature/endpoint map for building an open-source, unbiased minimalist price-comparison platform.
> Legal note: passive observation of public pages & the site's own public AJAX endpoints only. No injection, no attacks.

## 1. Stack / Shell

- **Anti-bot**: Cloudflare "Just a moment..." on plain Chromium (Playwright). Camoufox passes cleanly.
- **Server-side rendering**: pages (home, category, product, compare, search) are server-rendered PHP HTML.
- **JS libs**: jQuery 3.6.2, jquery.cookie, jplist (client-side list filter/sort), CanvasJS (price history chart), circliful (radial score), iziModal, jRating.
- **State-in-URL**: all filter/sort/search state is **PHP-serialized, base64-encoded** in URL path segment `/e/<b64>/`, e.g.:
  - sort: `N;_s:10:"tarih:DESC";` → `TjtfczoxMDoidGFyaWg6REVTQyI7=`
  - search: `a:2:{s:3:"ara";s:6:"iphone";s:7:"arasira";i:1;}_N;` → `YToyOntzOjM6ImFyYSI7czo2OiJpcGhvbmUiO3M6NzoiYXJhc2lyYSI7aToxO31fTjs=`
  - brand filter: `a:1:{s:5:"marka";a:1:{i:0;s:1:"1";}}_N;`
- **Media CDN**: `resim.epey.com` (product images: `/<pid>/k_<slug>.png` card, `s_<slug>.png` small; site logos `resim.epey.com/site/<store>.png`).
- **Analytics**: Google Analytics (GA4 G-MZXRL7TKL9 + UA-5…), Yandex Metrika (102670944), Google Ads/DoubleClick/AdForm/AdMost/DoubleVerify (ads + affiliate tracking).

## 2. Page Types & Their Data Sources

| Page | URL pattern | Data source |
|---|---|---|
| Home | `/` | SSR; carousels (Son Eklenen, Popüler, Fırsat) |
| Category listing | `/akilli-telefonlar/` | SSR + AJAX `/kat/listele/`, `/kat/filtrele/`, `/kat/ustbilgi/` |
| Filtered/sorted category | `/kat/<slug>/e/<b64>/` | SSR + AJAX |
| Product detail | `/akilli-telefonlar/<slug>.html` | SSR; price history via `/kat/fg/` |
| Compare | `/akilli-telefonlar/karsilastir/<id1>-<id2>/<s1>_<s2>/` | SSR (renders both products) |
| Search | `/arama/e/<b64>/` | SSR + AJAX listing |
| Deals | `/firsat-urunler/` | SSR listing (filters: Fırsat, Satışta, Çok Satan, Fiyatı Düşenler) |
| Retailer page | `/site/<store>/` (e.g. `/site/amazon/`) | SSR listing of all products tracked from that store |
| Brand page | `/xiaomi/`, `/samsung/` … | SSR listing by brand |
| Curated lists | `/televizyon/en-ucuz-4k-ultra-hd-led-televizyonlar/` | SSR listing |
| Retailer promo pages | `/amazon-prime/`, `/hepsiburada-premium/` | SSR listing |
| Info/legal | `/info/…html`, `/contact/` | SSR static |
| Member | `/uye/`, `/uye/favori/`, `/uye/filtre/` | account-gated; alert & favorite management |

## 3. AJAX API Endpoints (all POST, form-encoded, same-origin, cookie-authed)

### `/kat/listele/` — product listing fragment (HTML)
Params: `kategori_id`, `cerez` (session token, base64; can be empty), `limit` (31), plus one of:
- `sirala=<field>:<ASC|DESC>`  (sort; validated keys below)
- `sayfa=<n>`  (pagination)
- `filtrele[]=<filter>` (e.g. `marka:1`, `ozel:1`) — array of active filters
Returns: HTML fragment with `<ul id="<pid>" class="metin row">` product rows. Each row: image, name, model code (`.urunkodu`), family (`.aile`), compare checkbox `#urun<pid>`, lowest price + "N site, N fiyat", spec cells `.ozellik<fieldID>`, radial score `#puan<pid>` (circliful), and inline JS (filtre/sirala/kiyas functions).

### `/kat/filtrele/` — filter sidebar fragment (HTML)
Params: `kategori_id`, `cerez`, `filtrele[]`
Returns: facet groups `filtre1`/`filtre2` with `ozellikliste<featureID>` (spec facets w/ counts: Tarih/year, RAM, storage, battery, 5G, NFC, SAR, AnTuTu…), `markaliste` (brands w/ counts), price-range sliders, special toggles (Fırsat, Satıştakiler, Çok Satanlar, Fiyatı Düşenler). **Feature IDs double as sort IDs.**

### `/kat/ustbilgi/` — page header fragment (HTML)
Params: `kategori_id`, `elink=<b64 state>`
Returns: `<h1>` category title + full sort dropdown. **Sort key registry** (field IDs are global spec IDs):
- meta: `tiklama:DESC` popular, `satis:DESC` smart, `tarih:DESC` newest, `fiyat:ASC/DESC`, `yorumsayi:DESC`, `adi:ASC`
- specs: `1`=Screen size, `21`=Storage, `14`=RAM, `7`=Battery, `9`=Weight, `1870`=Year, `2`=Pixel density, `2033`=CPU tech, `19`/`18`=Main/Front cam MP, `886`=Screen ratio, `8`=Width, `26`=Length, `10`=Thickness, `11`=CPU GHz, `6593`=Fast-charge W, `92`/`91`=SAR, `4591/6064/7541/9550/10504`=AnTuTu v7–v11, `9410/9411`=Geekbench 6 SC/MC, `6101/7241/9229/10437`=DxOMark v3–v6, `10426`=Battery life after charge

### `/kat/kiyasla/` — compare tray (HTML)
Params: `kategori_id`, `cerez`, `kiyasla=<pid>`, `islem=ekle|sil` (or `kiyasla=tumunusil` to clear)
Returns: sticky bottom tray HTML — "Karşılaştır (N)" counter, selected product thumbnails w/ hover tooltips, Temizle button. **State is server-side session**.

### `/kat/kiyaslink/` — per-product compare count (HTML)
Params: `kategori_id`, `cerez`, `urun_id=<pid>`
Returns: tiny fragment `Karşılaştır (N)` for a product row button.

### `/kat/fg/` — **price history (JSON)** ← key data
Params: `id=<pid>` (product ID, = `data-id` of rating widget on product page), `fiyat=<current_lowest_price>`
Returns: JSON array of `[dd.mm.yyyy, "price_TL", range_id]` daily lowest-price series. range_id: 12 = 12 months, 6 = 6 months (36 also exists as 3 Yıl). ~460 points/year. This is the raw inflation/deal data.

### `/kat/yorumpuanla/` — rate review useful/not (POST)
Params include review id + rating.

### `/uye/filtre/` — user price-alert / saved-filter management (account)
POST `filtre_id=<id>&islem=sil` (delete); used by "Fiyatı düşünce haber ver" / custom filter alerts.

### `/uye/favori/`, `/uye/yorumyaz/`, `/uye/yorumislem/`, `/uye/inc_yorum/`, `/uye/inc_yanit/` — account features
Favorites, write review, review moderation (helpful flags), report review/reply. Login required.

### `/ara/` — search entry (GET, redirects to `/arama/e/<b64>/`)
Params: `ara=<q>`, `kat=<category_id>`

## 4. Product Page Anatomy (`/akilli-telefonlar/apple-iphone-17.html`)

- Rating widget `data-id="<pid>"` (4.0 / 67 oy / 435 yorum).
- Header: quick specs (screen, storage, RAM, battery, fast charge, 5G, waterproof, wireless charge) + Epey score (82 puan, circliful gauge).
- **Price list** (SSR, jplist client-side sort/filter): each offer = `<a id="<offer_id>" data-id="…" data-link="<urlencoded retailer product URL>" data-pos="…">` with:
  - site logo (`resim.epey.com/site/<store>.png`) + store name
  - product variant / seller / warranty (Distribütör/İthalatçı) / color
  - price + shipping (+ free-ship badge), hidden `.urun_fiyat_sort`, `.kargodahil`, `.sira` (jplist fields)
  - "Siteye Git ❯" affiliate deep link (target _blank, nofollow) + freshness ("1 saat önce")
  - Header controls: sort (Artan/Azalan Fiyat, Kargo Dahil), filter checkboxes (Distribütör Garantili, Ücretsiz Kargo), client pagination (jplist).
- **Fiyat Geçmişi** (price history): CanvasJS chart fed by `/kat/fg/`; range selector 6 Ay / 1 Yıl / 3 Yıl.
- **Ürün Ailesi** (family variants, e.g. 256 GB / 512 GB → sibling product links).
- **Özellikler** (specs): sectioned tables (EKRAN, BATARYA, …) — server-rendered, each spec has field IDs.
- **Yorumlar** (reviews): SSR, sortable; variant tabs (256GB/512GB); actions: Faydalı (helpful) → `/kat/yorumpuanla/`, Yanıtla (reply), reports → `/uye/*`.
- Shortcut to other "Karşılaştır" pairs (iPhone vs alternatives) — nice discovery pattern.

## 5. Compare Page Anatomy (`/karsilastir/<id1>-<id2>/<s1>_<s2>/`)

- Both products: score gauges, lowest price, first N offers w/ "Siteye Git" links, then "FİYATLARI KARŞILAŞTIR (N site, N fiyat)" → links to product page `#fiyatlar`.
- **TEMEL ÖZELLİKLER** table (key specs side-by-side).
- **TÜM ÖZELLİKLER** table grouped by spec section (EKRAN, BATARYA…). Difference highlighting not visible in text dump; check HTML classes.
- Also loads `/kat/fg/` for both products (charts).

## 6. Feature → Data-Source Map

| Feature | Endpoint / source |
|---|---|
| Category browse + cards | SSR `/kat/<slug>/` + `/kat/listele/` |
| Filters (brand/spec/price/toggles) | `/kat/filtrele/` (server-side state in URL `/e/<b64>`) |
| Sort | `/kat/ustbilgi/` + `/kat/listele/` (`sirala=`) |
| Pagination | `/kat/listele/` (`sayfa=`) |
| Compare tray | `/kat/kiyasla/`, `/kat/kiyaslink/` (server session) |
| Full compare table | SSR `/karsilastir/…` |
| Price history chart | `/kat/fg/` (JSON daily series) |
| Retailer offers per product | SSR product page (jplist client filtering) |
| Search | `/ara/` → SSR `/arama/e/<b64>/` |
| Deals ("Fırsat Ürünler") | SSR `/firsat-urunler/` + filters (Fiyatı Düşenler) |
| Store-level browse | SSR `/site/<store>/` |
| Brand-level browse | SSR `/xiaomi/` etc. |
| Reviews | SSR product page; actions `/kat/yorumpuanla/`, `/uye/*` |
| Favorites / price alerts | `/uye/favori/`, `/uye/filtre/` (account) |
| Sponsor blocks | AdForm/AdMost/DoubleClick server-side ad slots + "Reklam" cards in `/kat/listele/` (sponsored product = `#sponsor<id>` element) |

## 7. Open-data observations (for the open-source clone)

- **Epey's core data is fully retrievable without Epey**: price history is daily lowest-price per product (they aggregate; you can re-aggregate from retailer pages), spec tables come from manufacturer press material, scores are their own formula (opaque, could be reimplemented).
- The retailer deep links (`data-link`) point at the actual retailer product URLs — that's the affiliate layer Epey monetizes. An unbiased platform can collect the same offers from retailer public pages directly.
- **Recommended independent sources**: retailer sitemaps/product pages (Hepsiburada, Trendyol, Amazon.com.tr, PTT AVM, n11, Teknosa, Vatan, MediaMarkt…), official brand press pages for specs, TCMB for ₺ inflation context, and public retailer price feeds.
- **Watch out**: Epey sorts "Akıllı Sıralama" (`satis:DESC`) and features sponsored products ("Reklam" in feed) + "Okula Dönüş Heyecanı Teknosa'da!" promos — direct evidence of paid placement the user wants to avoid.
- No pagination beyond page 15 seen; listing caps at 31 products/page.
- Session cookie `cerez` guards compare state; the AJAX endpoints work with `cerez=` empty for read-mostly ops (listele/filtrele worked empty).

## 8. Clock
- ~15 min spent across: home, category, filters, sort, compare tray, product page, price history, search, deals, retailer page, brand page, compare page, reviews.
- Designs seen: 8 distinct page layouts → exhausted major page types.
