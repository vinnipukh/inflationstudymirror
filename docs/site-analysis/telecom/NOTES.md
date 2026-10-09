# Mobile operator tariffs — Turkcell, Vodafone, Türk Telekom, NetGSM

Recon: 2026-10-08. Scraper: `InflationItems/Codes/Telecom/scraper.py`.
TÜİK item: `0832001` Cep telefonu görüşme ücreti (group `0832` Mobil iletişim hizmetleri).

Scope (user decision 2026-10-08): **all** prices shown on the operators' public pages: postpaid
and prepaid tariffs **and** add-on packages. Where a page shows both a commitment (campaign) price
and a no-commitment price, both are stored (`price`, `list_price`).

All four sites answer a `curl_cffi` `chrome124` client with HTTP 200 and full content; no
browser, no cookies, no challenge seen. Homepage is fetched first per operator, requests are
serial with 1.5–3.5 s jitter.

## G0 — robots.txt (fetched 2026-10-08)

| Site | Relevant rules | What we use |
|---|---|---|
| turkcell.com.tr | `User-agent: *` … `Disallow: *packagetype=*`, `*sort=*`, `*card_group=*` | plain listing pages, no query strings |
| vodafone.com.tr | `User-agent: *` `Allow: /` (AI-bot UAs listed separately) | listing pages + `?type=faturasiz` add-on tab |
| bireysel.turktelekom.com.tr | `Disallow: /_layouts/`, `/mobil/*-secimi` pages; `Sitemap: /sitemap.xml` | sitemap + detail pages; `-secimi` URLs skipped |
| netgsm.com.tr | `Disallow: *?`, `*.php$`, `*.html$` | one path, no query |

ToS pages were not reviewed in depth; only public, unauthenticated price listings are read,
no personal data is collected.

## Turkcell

- Pages: `/paket-ve-tarifeler/faturali-hat` (86 packages), `/paket-ve-tarifeler/hazir-kart`
  (108), `/yurt-disinda-kullanim`, `/yurt-disini-arama`. `/faturasiz-hat` is 404.
- Data: `<script id="__NEXT_DATA__">` → `props.pageProps.dehydratedState.queries[].state.data.packages[]`.
- Fields: `id` (uuid, product_id), `title`, `paymentType` (POSTPAID/PREPAID/BOTH),
  `endpoint` (folder = group: ana-paketler, ek-paketler, tumbara-paketler, mobil-wifi-paketleri…),
  `price.amount`/`amountDouble`, `price.priceTimeUnit` (AY/HAFTA/GÜN) + `priceTime`,
  `price.discountPriceDouble` (non-zero → that is `price`, `amountDouble` is `list_price`),
  `benefits[]` (`type` INTERNET/VOICE/SMS, `value`, `unitValue`).
- Add-ons (ek paket, Tumbara free packages at 0 TL, Superbox, Mobil Wifi) are on the same pages.
- No separate no-commitment price is published on listing pages → `list_price` mostly empty.

## Vodafone

- Tariffs: `/numara-tasima-yeni-hat/tarifeler/NEW/postpaid/ALL` (25), `…/NEW/prepaid/ALL` (6).
  Next.js App Router: data lives in the RSC stream (`self.__next_f.push([1,"…"])`); concatenate
  the decoded strings and `raw_decode` every `{"id":<n>,` object that has a `price` dict.
- Fields: `id` (tariffId), `name`, `type` (ONLINE/RED/YALIN/FREEZONE/POME/HOSGELDIN/3AYLIK = group),
  `data.value` (+ `data.extra.value` FreeZone gift GB), `voice.value`, `sms.value`
  (`SINIRSIZ` → `sinirsiz`), `price.value.discounted` (price) / `price.value.base`
  (no-commitment price, e.g. 465 vs 1300), `price.period` (`/ay`, `/3 ay`),
  `price.commitmentText` / `summaryPriceInfo` ("12 ay boyunca …").
- The JSON-LD ItemList on the same page has names + prices but no ids/base price — not used.
- Add-ons: `/tarifeler/ek-paketler/<tab>` and `?type=faturasiz`; tabs internet, konusma, mesaj,
  sinirsiz, yurt-disi, durma-ozelligi, ucretsiz, butce-dostu-paketler, populer-paketler.
  Server-rendered `.addon--item` cards: `.addon--item__name`, `.addon--item__price`
  (`1.309 ₺`, `74,99 ₺`, `Ücretsiz`), detail link slug = product_id. Tabs overlap; rows are
  deduped by (segment, slug), first tab wins as group. No explicit period on cards — derived from
  the name (`haftalık`, `aylık`) when present.

## Türk Telekom

- Listing pages (e.g. `/mobil/yeni-musteri-tarife-ve-paketleri/faturali-tarifeler`) server-render
  only the first 12 cards; the rest is paged by `POST /_layouts/15/TTWebsite/Personal/Ajax.aspx/CardFilter`,
  which is **robots-disallowed** (`/_layouts/`). Not used.
- Instead: `sitemap.xml` (3,505 URLs, ~840 under `/mobil/`) → keep `/mobil/<a>/<b>/<slug>` detail URLs,
  skip `kampanya`, `musteri-alimina-kapatilan`, `-secimi`, `basvuru` → ~490 pages (~25 min).
  Pages without a JSON-LD `Product` are info pages and are skipped.
- Detail page fields: JSON-LD `Product.name` + `offers.price` (price);
  `[id$=_divPrice] .note` (period: `Aylık`, `28 Günlük`); `[id$=_nonPricingTableDiv] > p`
  ("12 Fatura Dönemi Taahhütlü Fiyat"); `table.properties-table` rows `Tarife Taahhütsüz Fiyat**`
  (list_price, e.g. 465 vs 790) and `Tarife İçeriği` (quotas).
- Detail pages also contain related-tariff cards (`.first-price`) — do not read prices from those.
- product_id = path after `/mobil/`; the same tariff can appear under `yeni-musteri…` and
  `mevcut-musteri…` (kept as separate rows, group tells them apart).

## NetGSM

- One page `/fiyatlar/mobil-hat`, 8 `.paket-card` blocks: `h4` (GB), `small` (DK + SMS),
  `h2` (price, `<span>/Ay</span>`). No names or ids → product_id is the quota slug
  (`4-gb-500-dk-100-sms`). Prices include KDV + ÖİV; monthly telsiz kullanım ücreti excluded.

## Output

`InflationItems/Datas/Telecom/<Turkcell|Vodafone|TurkTelekom|NetGSM>/<operator>_YYYY-MM-DD.csv`,
comma, utf-8-sig:

`date,operator,segment,group,product_id,product_name,price,list_price,period,data_gb,minutes,sms,commitment_months,url`

- `segment`: `faturali` / `faturasiz` (add-ons are identified by `group`).
- `period`: `<n>_<gun|hafta|ay|yil>` (e.g. `1_ay`, `28_gun`, `3_ay`); empty when not stated.
  Turkcell roaming / pay-as-you-go items are priced per unit and keep that unit
  (`1_dakika`, `1_kb`, `1_sms`, `2_gb`, `1_saat`).
- `minutes`/`sms`/`data_gb`: number or `sinirsiz`; empty when not stated.
- The header contains `product_name` + `price`, so `Inflations/Codes/turkey_inflation.py`
  can read it once a `Telecom` sector entry is added (not wired yet: it would only join the
  unweighted group-08 mean; a proper 0832 weight needs a calculator change).

## Known gaps

- Customer-specific / logged-in offers (Vodafone "size özel", Turkcell Hesabım) are not visible.
- Vodafone MNP (numara taşıma) listings are not fetched separately; the NEW listing carries
  `candidateType ["NEW","MNP"]` for the same ids.
- Taxes/fees outside the package price (telsiz kullanım ücreti, ÖİV on new lines) are not recorded.

---

# Ev interneti — Türk Telekom, TurkNet, Kablonet, Superonline, Vodafone, Millenicom

Recon: 2026-10-08. Scraper: `InflationItems/Codes/Telecom/internet.py` (shares `Fetcher`, `run()` and the
Türk Telekom detail parser `tt_details()` with `scraper.py`). TÜİK item: `0833001` İnternet ücreti.

## Access summary

| Provider | Source | Access |
|---|---|---|
| Superonline | `sitemap-campaigns.xml` → `/ev-interneti/<category>/<campaign>/<speed>`; one page per campaign, `__NEXT_DATA__` query `GetCampaignDetail` → `data.campaign.offers[]` | plain HTTP. robots disallows the `productType=` / `downloadSpeed=` / `addonServices=` filters — not used |
| Vodafone | `/net/ev-internet-paketi-fiyatlari`, `/net/fiber-internet`, `/net/fiber-internet-12-aylik`, `/net/redbox` | plain HTTP |
| Kablonet | `www.turksatkablo.com.tr/internet-Tarifeler` | plain HTTP + AIA-completed CA bundle (below). No robots.txt (404). `kablonet.com.tr` times out on :443 from here |
| Milleni (Millenicom) | `www.milleni.com.tr/eviniz-icin/kampanyalar/internet` | plain HTTP, robots `Allow: /`. `millenicom.com.tr` serves IIS 404 with a certificate for another name; `millenicom.com` is an unrelated US company |
| TurkNet | `www.turk.net/tarifelerimiz` | Cloudflare → cookie factory (below) |
| Türk Telekom | sitemap `/evde-internet/{yeni,mevcut}-musteri-kampanyalari/<slug>` (~340 pages) | plain HTTP, same layout and robots constraint as mobile |

## Superonline
- Hub pages (`/ev-interneti/tum-kampanyalar`) embed only 12 of ~40 campaigns; the rest is paged client-side,
  so campaigns come from the sitemap (42 campaigns / ~108 speed URLs on 2026-10-08).
- `campaign`: `id`, `title`, `networkType.lookupValue` (Fiber / ADSL & VDSL / Kablo / Superbox), `validityDate`
  (expired campaigns stay in the sitemap → skipped when `validityDate < today`).
- `offers[]`: `id`, `download` + `downloadType`, `upload`, `price`, `period` (commitment months, `0` = none),
  `priceType` (`Tek Fiyat`; stepped offers also carry `price1..3` — only `price` is stored), `urlPostFix`, `passive`.
- product_id = `<campaign id>-<offer id>`.

## Vodafone
- `.card-tariff-2` cards: `.card-name`, `.card-rightTag` (Wi-Fi 6 / Wi-Fi 7 modem), `.card-benefit1` (speed),
  `.card-subDescription1` (Fiber İnternet), `.card-description2` ("12 ay sabit fiyat" → commitment 12),
  `.card-price-value`, `.card-price-period`, modal `.card-modal-detailItem` ("Kampanya adı: …").
- product_id = `tarifeId` from the "Adresimi sorgula" link. RedBox (5G home internet) cards have no speed; the
  quota is in the name.

## Kablonet (Türksat Kablo)
- Two static tables: (1) download | upload Kablo İnternet (DOCSIS) | upload Eve Kadar Fiber (GPON) | price,
  (2) download | upload DSL | upload FTTH | price. One row per (speed, infrastructure) whose upload cell is not `-`.
  These are list prices; campaign pages (`/tumkampanyalar-detay.aspx?q=…`) are address-bound and not read.
- **TLS:** the server sends only its leaf certificate (`*.turksatkablo.com.tr`, issuer
  "GlobalSign GCC R46 AlphaSSL CA 2025"). Browsers complete the chain from the AIA URL; OpenSSL/curl do not.
  `aia_bundle()` downloads `http://secure.globalsign.com/cacert/gsgccr46alphasslca2025.crt` and appends it to the
  certifi roots, so verification stays on. Update the URL when GlobalSign rotates the intermediate.
  Changing the User-Agent / TLS profile does not help (tested firefox133 and chrome124).

## Milleni
- `[data-campaign-card]` elements carry everything as attributes: `data-pkg-id`, `data-pkg-name`, `data-speed`,
  `data-commitment` (`true` → 12 months), `data-provider` (Türk Telekom / Superonline infrastructure),
  `data-infra`, `data-type` (internet / internet-tv), `data-price`.
- The strike-through list price exists only on the spotlight `article[data-pkg-id]` (`[class*=price-old]`).

## TurkNet
- `/tarifelerimiz` is the regulatory tariff list. First table = "Abone alımına açık tarifeler"
  (Segment, Kampanya No, Altyapı, Tarife Adı, Satışa Açılış Tarihi, Aylık Fiyatı). Later tables are
  closed / withdrawn tariffs and are ignored. Speed = the number before the dash in the tariff name.
- **Cloudflare (tested 2026-10-08):**
  - curl_cffi 0.15.0 (CI pin): 403 "Just a moment…" for every Chrome profile (chrome, chrome136, chrome131, chrome124).
  - curl_cffi 0.16.3 newest `chrome` profile: 200 without cookies; `chrome124`: 403 → the TLS fingerprint decides.
  - **Cookie factory (used):** one headless undetected-Chrome visit to the homepage ("HeadlessChrome" removed
    from the UA) passes without an interactive challenge and receives `__cf_bm`; curl_cffi with those cookies +
    the browser UA → 200. No `cf_clearance` is issued. Chrome is closed before the request.
  - The sales API (`sales-gateway.turk.net/api/sales/products|tariffs`) answers 401; its token comes from
    `www.turk.net/api/auth/fetch-access-token` (behind Cloudflare + reCAPTCHA) → not used.
  - Cookie reuse did not help on Kablonet / millenicom.com.tr (TLS / dead-host problems, not bot detection).
- Risk: GitHub runner IPs may be challenged harder than a residential IP; TurkNet then fails alone
  (the other providers still commit).

## Türk Telekom
- Same `tt_details()` as mobile, section `evde-internet`, depth ≥ 1.
- Old campaign pages stay in the sitemap with a JSON-LD price; they contain
  "Bu teklif müşteri alımına kapatılmıştır." and are skipped (applies to mobile too).
- Speed from name / pricing table / slug (`…-100-mbps-10`).

## Output

`InflationItems/Datas/Telecom/Internet/<Superonline|Vodafone|Kablonet|Milleni|TurkNet|TurkTelekom>/<provider>_YYYY-MM-DD.csv`,
comma, utf-8-sig:

`date,operator,group,product_id,product_name,price,list_price,period,speed_mbps,upload_mbps,infrastructure,commitment_months,url`

All four scrapers: a bounded run (`--limit N`) writes `<name>_YYYY-MM-DD_limit.csv` so it never overwrites the
day's full snapshot; the server's `cleanup.sh` deletes `*_limit.csv` older than a day.

---

# Dijital içerik / streaming platform abonelikleri

Recon: 2026-10-09. Scraper: `InflationItems/Codes/Telecom/streaming.py`. One public page per service, plain
HTTP (`curl_cffi` chrome124 + `Accept-Language: tr-TR`). Prices are the regular prices; first-month / trial
promotions are skipped (noted in the product name where relevant).

| Service | Page | How the price is read |
|---|---|---|
| Netflix | `help.netflix.com/tr/node/24926` | help-article text "Temel plan: Ayda 259,99 TL" (Temel / Standart / Premium) |
| Disney+ | `disneyplus.com/tr-tr` | plan cards "DISNEY+ REKLAMLI / REKLAMSIZ", "249,90 TL / ay", "2.499,00 TL / yıl" |
| HBO Max | `hbomax.com/tr/tr` | plan cards "Standart ₺229,90 / ay", "Özel ₺299,90 / ay" (yearly tab is not in the HTML) |
| Amazon Prime | `amazon.com.tr/prime` (fetched directly; the homepage answers a 202 bot interstitial) | "Prime sadece 69,90₺/ay" — Prime membership incl. Prime Video |
| Apple TV+ | `apple.com/tr/apple-tv-plus/` | footnote "aylık 89,99 TL üyelik ücreti" |
| YouTube Premium | `youtube.com/premium` | ytInitialData `optionSectionRenderer` (Premium Lite / Premium) + `optionItemRenderer` subtitle runs ("₺119,99/ay", U+2060 word joiners stripped); plans repeat across sections and are de-duplicated |
| Spotify | `spotify.com/tr-tr/premium/` | "Premium Bireysel … Sonra ayda ₺115", Öğrenci, "Premium Duo ₺159 / ay", Aile |
| MUBI | `mubi.com/tr/tr` | `__NEXT_DATA__` `subscriptionPlans` (`month`, `year`, `month_student`; `price_in_cents`) |
| TV+ (Turkcell) | `tvplus.com.tr/paketler` | RSC payload `stickyBarData.packages.guestInfo.priceMonthly / priceYearly` (yearly = monthly equivalent) and `gaoPackages[]` (Turkcell × HBO Max, "sonrasında 200.00₺"). The full package list needs login |
| Tivibu | `tivibu.com.tr/paketler` | `.item-container[package-id]` → `.priceSelect` (`.title` Aylık/Yıllık, `.price`, `.oldprice` = list price, `redirectUrl` ProductId) |
| TOD (beIN) | `todtv.com.tr/satinal`, opened directly (`tod.tv` is the MENA site; the homepage redirects to a small `/mac-basliyor/` splash on match days) | `.package-card[data-item-name]` (data-item-id, data-item-category) → `.subscribe-accordion-collapse-pricing` pairs: "/Ayda N TAKSİTLE" (yearly/seasonal plan in instalments) and "/Aylık" (cancel-anytime monthly) |
| GAİN | `destek.gain.tv/sss.html` | FAQ text "Aylık abonelik 149 TL, yıllık abonelik ise 1.490 TL" (the homepage only shows the "ilk 3 ay ₺129" promo) |
| tabii (TRT) | `tabii.com/tr` via one headless Chrome visit (`internet.browser_visit`) | rendered card "PREMIUM 99,00₺ / ay" (the free tier is skipped) |

tabii note: the public products API (`eu1.tabii.com/apigateway/subscriptions/v1/public/products/`, also with
`Accept-Language: tr`) returns only the free tier; the call that fills the Premium card could not be isolated
(fetch/XHR hooks and the register flow show nothing), so the rendered page is read instead.

Not collected:
- **Exxen** — `exxen.com` asks for name + e-mail before showing packages; the TR App Store page no longer
  embeds in-app purchase prices.
- **Hepsiburada Premium** — `/premium` only shows the "ilk ay 1 TL" campaign; the regular fee (press: 69,90 TL/ay)
  is not on a public page.
- **Paramount+** — not sold in Türkiye (`paramountplus.com/tr/` → `/intl/`, no app in the TR App Store);
  its catalogue is part of TOD / TV+ packages.

Output: `InflationItems/Datas/Telecom/Streaming/<Service>/<service>_YYYY-MM-DD.csv`, comma, utf-8-sig:
`date,operator,group,product_id,product_name,price,list_price,period,url` (`period` = `1_ay` / `1_yil`).

---

# Bilgi ve iletişim ekipmanı bakım / onarım ücreti

Recon: 2026-10-09. Scraper: `InflationItems/Codes/Telecom/repair.py`. The basket (which devices / brands /
services) is not decided yet, so every price each source publishes is collected. All plain HTTP.

| Source | Kind | Where | Count (2026-10-09) |
|---|---|---|---|
| Apple | official out-of-warranty estimate | `support.apple.com/ols/api/pricing/products/services/pricing-estimate?locale=tr-tr&pricing_type=OOW&parent_tag_id=<tag>` | 533 (iPhone 180, iPad 100, Watch 186, AirPods 69) |
| Samsung | official "tavsiye edilen onarım ücretleri" | `samsung.com/tr/support/ekran-degisimi-fiyat-bilgisi/` tables | 171 |
| Huawei | official spare-part price (parts + labour) | `ccpce-de.consumer.huawei.com/.../queryNewCommodityList` + `cspm/queryMaterialPrice` | 603 (145 models; ~20 min) |
| Egemek | Apple authorised service provider | `egemek.com.tr/iphone-servis-ucretleri` table | 87 |
| GSM İletişim | independent repair shop, all brands | `gsmiletisim.com/urun-kategori-sitemap.xml` → 112 category pages (+ `/page/N/`) | 4,475 (921 models) |

## Apple
- The parent tag of each device family is set by JS on `/tr-tr/<device>/repair` (not in the HTML):
  iPhone `TAG_1754518739895`, iPad `TAG_1750382034263`, Watch `TAG_1755238435489`, AirPods `TAG_1749056323568`.
  `/tr-tr/mac/repair` redirects to the generic product list — no Mac estimate is published in Türkiye.
- Response: `products[]` → `childrenProducts[]` (recursive) → `services[]` (`serviceLabel`, `price` "21.519 TL").
  product_id = `<product_tag_id>-<service slug>`.
- If a family returns 0 prices, re-capture its tag from the browser network tab (`pricing-estimate` request).
- Since 2026-10-09 the API answers `400 {"message":"Provide valid header's: Referer and Host"}` without a
  `Referer`; the scraper sends `https://support.apple.com/tr-tr/<device>/repair`.

## Samsung
- Tables with header `Model Kodu | Model Adı | <service columns>` (Ekran - Modül Onarımı, Ekran - Eko Onarım,
  Dış Ekran Onarımı, Çerçeve Onarımı; Galaxy Ring: Yüzük, Şarj Kutusu); `-` = not offered.
- `Seri | Ücret` table = battery replacement per series. Its second row is a malformed duplicate and is skipped.
- product_id = model code (`SM-G991`) + service.

## Huawei
- Product tree: `queryNewCommodityList/1000?productLevel=lv2&productId=CMCG10000001` (categories: Telefon,
  Bilgisayar, Tablet, Monitor, Desktop, Akıllı ev cihazları, Akıllı Cihaz, Giyilebilir) → lv3 series → lv4 models
  (`hasPriceFlag`) → lv5 configuration → lv6 colour SKU (`productId`, e.g. `51098CYD`). Responses are JSONP-like
  `( {...} )`.
- Price: `POST cspm/queryMaterialPrice/1000` with
  `{"countryCode":"TR","languageCode":"tr","timeZone":"GMT+03:00","skuCode":"<lv6 productId>","siteCode":"tr_TR"}`.
  Any other `timeZone` format or a model-level id returns `responseData: null`.
  `serviceMaClassifyList[].itemTypeInfoList[]` (`sparePartTypeLocalDesc` = part, e.g. "Pil") →
  `serviceItemPrice[]` (`price` = part, `labourCost`, `totalPrice` = stored price).
- Colour variants share the price; only the first SKU per model is queried.

## Egemek
- One table `iPhone Modeli | Ekran Değişimi | Pil Değişimi | Cihaz Değişimi`. No iPad / Mac pages (404).

## GSM İletişim
- WordPress (custom `urun` post type; the WooCommerce Store API is not exposed). `urun-kategori-sitemap.xml`
  lists 112 category pages (brand × service); each page lists all its cards (`li.product`,
  `h2.product-title a`, `[itemprop=price]` `content`). A page shows 99 cards; the rest are on `<cat>/page/N/`
  (infinite scroll, no next link) — pages are read until one has no cards or fewer than 99. Cards without a
  price ("fiyat sorunuz") are skipped.
- Model and service are split at the first service keyword (ekran, batarya, pil, ön cam, kamera, ...).

Output: `InflationItems/Datas/Telecom/Repair/<Source>/<source>_YYYY-MM-DD.csv`, comma, utf-8-sig:
`date,operator,group,product_id,product_name,service,price,list_price,url`.
