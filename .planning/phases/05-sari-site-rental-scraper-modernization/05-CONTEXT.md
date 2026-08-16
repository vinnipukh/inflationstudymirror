# Phase 5: Sarı Site Rental Scraper Modernization — Context

**Gathered:** 2026-08-16 (recon 2026-08-15 + research validation + quick task 260816-fx3)
**Status:** Ready for planning (one wave already executed as quick task; remaining work planned here)

<domain>
## Phase Boundary

Phase 5 replaces the legacy rayobrowse/Playwright rental scraper for the sarı
site (sahibinden.com) with the proven friend-tactics selenium engine, verifies
it live, productionizes daily runs, and adds snapshot-aware storage. Scope:
Kayseri, Sivas, Tokat rental listings — fields **District, Rooms, Price, ilanId**
ONLY (law-faculty-confirmed compliance scope; docs/APPROACH.md B0). Detail
pages, contact info, advertiser names, and photos are permanently OUT of scope.

Phase 5 does NOT: touch the Falcon API/Streamlit dashboard phases (1–3), add
captcha-solving services, or change the research-validated browser-only default.
</domain>

<decisions>
## Implementation Decisions

### Driver & session strategy (D-01 … D-04)
- **D-01:** Primary driver = **undetected-chromedriver** (Chrome 147) with a
  **persistent `--user-data-dir=SeleniumProfile`**. The profile IS the trust:
  cf_clearance/_px3 cookies survive across daily runs. Rayobrowse/Playwright
  path deleted (scraper.py, run_scraper.py); wreq stays demoted/experimental.
- **D-02:** CAPTCHA strategy = **manual solve-retry loop** (pause → human solves
  in visible Chrome window → ENTER → verify listings visible). No paid
  auto-solve. A challenge on the index page = stop/degrade signal, not auto-retry.
- **D-03:** Adaptive pacing: 2.5s base page delay ±50% jitter; adaptive 1.5–8s
  (shrink on success streaks, grow on errors). Query cap 1,000 listings →
  adaptive price-bracket splitting (min width 50, max depth 6).
- **D-04:** Checkpoint/resume per day: resolved brackets + done markers cached
  atomically; a crashed run resumes with `--resume`; cleared only on full success.

### Validation gates (D-05 … D-07)
- **D-05:** G0 gate (was failed by CloakBrowser on 2026-08-15) must pass with the
  selenium engine: cold session completes the day-1 manual-solve ritual and a
  warm session collects listings with zero challenges.
- **D-06:** IP-vs-browser cause of the Turnstile failures is unresolved; a
  vanilla-Playwright control test is optional and low priority (profile-warm
  sessions may make it moot).
- **D-07:** Live site testing paused until the IP cooldown passes (repeated
  Turnstile failures on 2026-08-15 flagged the IP). Offline-only verification
  until then.

### Storage & scheduling (D-08 … D-10)
- **D-08:** Interim source of truth = per-day CSVs under `Datas/HousesRent/<City>/`
  (schema `District,Rooms,Price,ilanId`, ilanId LAST). Existing calculators and
  dashboard phases already consume this shape.
- **D-09:** Snapshot-aware MongoDB model (research report B10): `listings_current`
  + `listing_observations` + `crawl_runs`, replacing raw CSVs as the durable
  store. Engine stays CSV-writing; an adapter syncs CSVs → Mongo.
- **D-10:** Daily-run scheduler = simple OS-level (GitHub Actions cron or Windows
  Task Scheduler) wrapper around `main.py --resume`; monitor via crawl_runs.
</domain>

<context>
## Accumulated Context

### Recon facts (2026-08-15, docs/APPROACH.md §7)
- Anti-bot stack: Cloudflare (`cf_clearance`, `__cf_bm` 30-min inactivity,
  `__cflb`) + PerimeterX (`_px3` re-issued/session, `_pxhd`, `_pxvid`) +
  Turnstile (login-only, `render=explicit`, sitekey read live from
  `#cloudflareTurnStileSiteKey`).
- Listing DOM: `#searchResultsTable tbody tr[data-id]` = ilanId; price
  `17.900 TL`; dates `10 Ağustos 2026`; pagination `pagingOffset=(page-1)*50`,
  `#currentPageValue`, `.pageNavigator` "Toplam N sayfa".
- Chrome selector quirk: always quote attribute values (unquoted values with
  digits/dots get rejected by Chrome's parser).
- Volume math: Kayseri ~2,020 / Sivas ~1,020 / Tokat ~960 → ~82 pages at 50/page,
  ≈13–22 min at paced delays. No bulk layer needed.

### Friend's proven pattern (IstanbulAvrupa, 3 months daily, 24,583 rows)
- uc.Chrome + persistent SeleniumProfile; manual CAPTCHA solve-retry; adaptive
  pacing; adaptive bracket splitting at 1,000-listing cap; lxml XPath (BS4
  chosen here — volumes are small); per-day checkpoints; daily CSV rows.

### Already executed (quick task 260816-fx3, commits 2a84926…7d2edb4)
- Recon + tech-stack search logged (`docs/TECH-STACK-SEARCH.md`); deep-research
  report processed; docs merged/renamed to sarı site naming; APPROACH.md gates
  G0–G4 amended; CloakBrowser tested and REJECTED (G0 fail, free binary v146);
  engine_selenium.py written + alignment rewrite (scraper.py deleted);
  offline checks green (parse/filter/CSV-header/checkpoint/adaptive-delay).
- Skills installed: playwright, webapp-testing, modern-python,
  mongodb-schema-design, mongodb-connection, playwright-skill, and others.
  cookie-sync rejected (Browserbase API key required); browser-act scrapped.
</context>
