# Akakce.com — Site Analysis Notes

> Investigated: 2026-09-05 via Camoufox stealth browser.
> VPN datacenter IP was Cloudflare-challenged ("Performing security verification"); residential IP passes cleanly.
> Passive observation of public pages + the site's own public JSON API only. No attacks.

## 1. Stack / Shell

- **Anti-bot**: Cloudflare managed challenge. VPN/data-center IPs get hard-stuck; residential IPs pass instantly. Camoufox with residential IP works.
- **Architecture**: server-rendered PHP-style HTML with React "islands" (`st.akakce.com/build/...`), plus a **public JSON API on api6.akakce.com** used by the SPA parts (sort, filter, quickview, autocomplete, deal lists).
- **Media**: `cdn.akakce.com` (product images `/<mk>/<slug>.jpg`, icons `/im/...svg`), `iis-akakce.akamaized.net/p.x?<urlencoded remote image>` (retailer image proxy — note: it proxies OTHER sites' images, useful), `st.akakce.com` (JS/CSS), `akakce-g.akamaized.net` (price graph images/JSONP).
- **Analytics pixels**: Google, Yandex (yango), TikTok, Pinterest, Efilli consent SDK, CreativeCDN tags.
- **State in URL**: sort/filters via path numbers: `/cep-telefonu,<catCode>,<sortCode>.html` (sort: 1=Popular, 2=Lowest, 4=Highest, 7=Score, 3=Newest), brand slug `/cep-telefonu/apple.html`, filter via `/?filterIds=` style in API only (URL uses slug paths).
- **Counts**: ~2.37M products tracked ("2.368.948 farklı ürün"), phone category alone = 3,389 products.

## 2. Public JSON API (api6.akakce.com) — all GET, same-origin cookies; works anonymous

| Endpoint | Purpose |
|---|---|
| `/category/ctQueryWithFilterAndHpl?ctCode=<catCode>&page=<n>&sort=<s>&filterIds=<ids>&isFilterRequest=<bool>` | **Category browse**: components = metadata, quickFilters (popular makes+top facets), productList, filters (facet groups + price histogram), miniHpl/hpl (deal/homepage lists embedded) |
| `/quickview/get?prCode=<productCode>` | Product quickview: live per-vendor prices (`price, shipPrice, vdName, vdCode, badge ("Kargo dahil en ucuz"), lastUpdateText, showOldPriceNotice`) |
| `/dl/dlquery/?PrSetId=<setId>&Sort=<s>&Page=<n>` | **Deal lists** (server-powered lists): products with `dropRatio` (price-drop %), unit, countOfPrices, banners/ribbons (sponsored!) |
| `/autocomplete?q=<text>` | Search suggestions: groups Ürünler / Arama Önerileri / Kategoriler |
| `/user/v2/pricechangedlastvisiteditems` | Price-changed products from last visit (homepage, personalizes) |
| `/user` (family) | account-gated: price alarms ("Alarm Kur"), favorites; requires login |
| `/store` (family) | store vendor data; page also embeds `routes/magaza...` JSON with `pgSetId` (store's product-set id → feed to dlquery) |
| `/product/compare/more` | compare page "more" data |
| `/j/l/f/?c=<filterId>&f=<filterId>&ct=<catCode>` | lightweight client filter helper (mobile/legacy) |
| `https://api.akakce.com/app-redirect/?r=<url>` | app deep-link redirect |

**Category API product object fields**: `code, mkName, name, price, imageUrl, rating, countOfPrices, url, hasGraph, colorVariants, followCount (alarm count!), dropRatio (%), countOfProducts, hasSpotCampaign (sponsored!), brochureImages, unit`.
**Filter groups**: `selectedFilterIds, categoryInfo (currentCategory: name/code/parentCode/countOfPrice), priceFilterText ("0-20000,20000-50000,..."), filterGroups[{name:"Markası", filters:[{name,id}]}], histogram {minPrice, items:[{price,count}]}` — facets carry stable numeric filter IDs (e.g. Apple=134091, Samsung=139593…).
**Deal-list PrSetIds** (discovered): fiyati-dusen=180245, fark-atan=116343, son-6-ay-en-ucuz=54312, adetli-al-az-ode=25407, ikinci-el=126546 (isPg=true), store pgSetId (e.g. Trendyol=8368).
**userAction objects** everywhere: `{enabledActions:["fav","alert"]}` — the UI hooks for favorites & price alarms.

## 3. Price History (graph)

- **Not a JSON endpoint**: server-rendered **image/JSONP** at `https://akakce-g.akamaized.net/<productCode>:<variantId>:<v>` (loaded as CSS background + `:s` JSONP script).
- Product page embeds `initGraph(url, 'PG_C', '{mfom:1,cp:46550,...}')` where cp = current price, m = graph mode.
- Modal ("Fiyat analizini detaylı gör") provides: ranges 1 Yıl/6 Ay/1 Ay/1 Hafta/**Gelecek 15 Gün (forecast!)**, Grafik/Tablo toggle, period stats (max/min/current), and **Tablo** = daily rows: Tarih | En Ucuz Fiyat | Fiyat Değişimi (TL) | Değişim Yüzdesi (%). Data extracted from table DOM (52 rows/6 months).
- Price alerts: "Dün %8,1 fiyat düşüşü için bildirim gönderildi" — drop-detection notifications at the core.

## 4. Page Types

| Page | URL | Source |
|---|---|---|
| Home | `/` | SSR + `/user/v2/pricechangedlastvisiteditems` |
| Category | `/cep-telefonu.html` (also `<slug>.html`, brand `<slug>/<mk>.html`, sort `,<cat>,<sort>.html`) | SSR + category API |
| Product | `/cep-telefonu/en-ucuz-<slug>-fiyati,<code>.html` | SSR + quickview + graph image + `/product/compare/more` |
| Price-droppers | `/fiyati-dusen-urunler/` | dlquery PrSetId=180245 |
| Price-gaps | `/fark-atan-fiyatlar/` | dlquery PrSetId=116343 |
| 6-month cheapest | `/son-alti-ayin-en-ucuz-fiyatli-urunleri/` | dlquery PrSetId=54312 |
| Bulk per-unit | `/adetli-al-az-ode/` | dlquery PrSetId=25407 |
| Used deals | `/ikinci-el-firsatlar/` (+ `/bu-urunler-yalnizca-ikinci-elde/`) | dlquery PrSetId=126546 |
| Compare wizard | `/telefon-karsilastirma/…`; pair page `/telefon-karsilastirma/<s1>_<s2>,<c1>,<c2>.html` | SSR |
| Store page | `/magaza/<vendor>.html` (e.g. trendyol) | SSR + embedded JSON (pgSetId) + dlquery |
| Brochures | `/brosurler/`, `/brosurler/<store>`, `/brosurler/<store>-<date>-katalogu-<type>-<id>` | SSR pages, 100+ stores |
| Search | `/arama/?q=` (smart-redirects to category/brand) | SSR + autocomplete API |
| Campaigns | `/black-friday-indirimleri/`, `/11-11-indirimi/`, `/okul-alisverisi/`, `/vergisiz-telefonlar/`, … | SSR lists |
| Guides | `Hangi Cep Telefonu Bana Göre?` (on category page) | inline widget (filter-based) |
| Account | `/hesabim/`, `/hesabim/alarmlarim/`, `/hesabim/favori-listem/` | login-gated; user API |

## 5. Product Page Anatomy (Samsung Galaxy S25 128 GB example)

- Variant matrix: size (128/256 GB) + color chips → each combo = its own product code (e.g. 2095843206 base, 917789027 lacivert…).
- Header: "N satıcı içinde kargo dahil en ucuz" (cheapest incl. shipping calc), price, seller w/ guarantees, "Satıcıya Git" affiliate deep link `#/111/...?f=<base64 param>`.
- **Fiyat Değişimi** chart (ranges + forecast), Alarm Kur, follow count, price-change notification history.
- Full seller list: variant name, card-perk banners ("1.000 TL WorldPuan"), stock qty, ship days, seller name — jplist-style client sort/filter ("Sırala: En Ucuz", Filtrele).
- Yenilenmiş/İkinci El (refurbished/used) section.
- "En Popüler <Marka> Ürünleri" HPL block (hplType 22) — cross-sell listing.
- Reviews w/ helpful votes; "Bu yorumu faydalı buldunuz mu?".

## 6. Compare Page Anatomy (Redmi Note 13 Pro vs 14)

- Both products: En Ucuz Fiyat + N satıcı, **Piyasa Fiyatları** (all market prices), **Broşürlerden Fiyatlar** (store, month, price), Alarm Sayısı, Ortalama Puan, Markası.
- Spec matrix with toggle **Tümü / Aynıları Göster / Farklıları Göster**.
- All SSR; the "Karşılaştır" buttons on wizard page carry selector `data-u="/telefon-karsilastirma/<s1>_<s2>,<c1>,<c2>.html"`.

## 7. Feature → Data-Source Map (for clone)

| Feature | Akakce endpoint/source |
|---|---|
| Category browse + facets | category API `ctQueryWithFilterAndHpl` (histogram + filterIds) |
| Sort | URL `,<cat>,<sort>` + category API `&sort=` |
| Live per-store prices | `quickview/get?prCode=` |
| Price history + forecast | graph image `akakce-g…` + modal table (no public JSON) |
| Price-drop ranking | `dl/dlquery/?PrSetId=180245` (+ others) |
| Cheapest-6-months / gaps / bulk / used | same endpoint different PrSetIds |
| Search suggest | `/autocomplete?q=` |
| Store catalog | SSR + `dlquery` w/ pgSetId |
| Brochures | SSR pages (scrapable: `/brosurler/<store>` lists) |
| Alarms / favorites | `/user` (login-gated) |
| Compare | SSR + `/product/compare/more` |
| Ad placements | ribbons/banners embedded in dlquery JSON + `hasSpotCampaign` flag on products + "Reklam" in epey-style feeds |

## 8. Alternative data sources (independent of akakce/epey)

- **Prices/offers**: retailer public product pages + sitemaps (Trendyol, Hepsiburada, n11, PTT AVM, Amazon.com.tr, MediaMarkt, Teknosa, Vatan, Pazarama, Dr, Decathlon…). Both sites only aggregate these; the affiliate deep links point back to retailer URLs (visible in quickview `url`, %>`data-link` on epey).
- **Store flyers**: retailer-owned brochure pages (A101, BİM, Şok, Migros, CarrefourSA publish their own PDFs/images weekly).
- **Specs**: manufacturer press-kit pages; Akakce mirrors these in compare tables.
- **Refurbished/used**: retailers' own outlet sections.
- **Price history**: build your own daily snapshots (both sites' APIs have no bulk export; the graph is image-only). A daily crawler of retailer pages reproduces the data legally at low volume.
- **Currency/inflation context**: TCMB (Turkish central bank) public data.
- Note: both sites' derived metrics (epey "puan", akakce "dropRatio %" from own history) can be re-derived from your own time series.

## 9. Design-fidelity notes (for the minimalist rebuild)

- Akakce homepage = stacked deal rails (Fiyatı Değişenler %, Fark Atan TL, Son 6 Ay, İkinci El, Adetli Al w/ TL/kg, Broşürler, Broşürden Ucuz) + brochure cards + brand grid. The "value" is data-first: % badge, price, seller count, alert button.
- Core UX patterns: "En Ucuz %N" badge, "+N FİYAT" count, "Alarm Kur" CTA, "Kargo dahil en ucuz" label, per-unit price (TL/kg, TL/adet) for groceries.
- Clear sponsorship signals to strip: ribbons (mediamarkt/amazon campaigns), "Okula Dönüş Heyecanı Teknosa'da!" promos, `hasSpotCampaign` products, newsletter-style banners.

## 10. Clock
- ~20 min across: home, category (filters, sort, guide), product (graph, forecast, seller list, used), quickview, deal lists ×5, compare wizard + pair page, brochures, store page, search, autocomplete. Page designs exhausted.

### Bonus endpoints (confirmed live)
- `/category/filter?ctCode=<cat>&filterIds=<ids>` — filter component JSON alone (facets + histogram)
- `/make/productlist?MkName=<make>` — ALL products of a brand across categories (e.g. MkName=apple → 2,218 products; fields incl. rating decimal, quickViewCount)
- category API pagination: `&page=2` works (page size ~30, sort preserved)
