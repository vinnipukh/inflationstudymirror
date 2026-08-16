# Sarı Site Data Acquisition — Approach & Recon

**Date:** 2026-08-15 · **Revised:** 2026-08-16 (per deep-research validation — see `docs/RESEARCH-REPORT-2026-08-16.md`)
**Status:** recommended flow (pending benchmark gates)
**Sources:** live site reconnaissance (section 7, 2026-08-15), deep-research validation report (2026-08-16), `docs/TECH-STACK-SEARCH.md` (tool catalog + blueprint), `docs/scraping-wiki/` (tested technique truth), `Codes/HousesRent/KayseriSivasTokat/` (current scraper).

> ⚠️ **Naming note:** per project convention the target site is referred to as **"sarı site"**. The literal domain remains only where functionally required (code URLs, login-detection patterns, runtime cookie filenames).
> ⚠️ **Compliance note:** a 16 Aug 2026 review found the site's published usage conditions contain AI-agent provisions (UA identification, no human-interaction simulation, respect for CAPTCHA/firewall/rate/robots controls). **Gate G0 now starts with an authorisation/terms decision** before any anti-detection engineering (blocker B0).

---

## 1. Problem statement

Collect daily rental listings for Kayseri (~2,020), Sivas (~1,020), Tokat (~960) from sarı site: `ilanId`, link, district, rooms, price, date. Data is public (no login required for listing pages) but sits behind a layered anti-bot stack. Current scraper works but is fragile: detectable mouse motion, stale Turnstile sitekey, dropped ilanId, no tests, CSV-only output.

**Volume math (recon-verified, corrected by research report):** ~4,000 listings total; at `pagingSize=50` that is **~82 index pages across all three cities** (Kayseri ~41, Sivas ~21, Tokat ~20). At the proposed 8–12 s pacing + 30–90 s pause per 20 pages, the deliberate delay budget is **~13–22 minutes** — NOT hours. **A second network stack (wreq bulk layer) is therefore NOT justified at this volume**; it becomes an optional escalation only if a runtime SLO is violated (see G2).

## 2. Threat model — blocker by blocker (revised 2026-08-16)

| # | Blocker | What triggers it | Counter (primary) | Fallback chain |
|---|---|---|---|---|
| **B0** | **Access-policy / contractual controls** ⭐ NEW | Site terms contain AI-agent provisions: agent UA identification, no human-interaction mimicry, respect CAPTCHA/firewall/rate/robots controls; programmatic access may be blocked on breach/suspicion | **✅ AUTHORISATION MODEL CONFIRMED 2026-08-16 (university law faculty review):** permitted to collect **District, Rooms, Price + ilanId** from public search-table rows. **HARD EXCLUSIONS (never collect):** telephone numbers, name/surname of advertisers, photos, and no mirror-site reproduction. Detail pages (where contacts/photos live) are therefore permanently out of scope — B5 becomes a compliance rule, not just a technical choice. Dated copy of terms/robots policy retained | Ask the site for an approved research/feed/data route (P2) |
| **B1** | **Cloudflare edge** — `cf_clearance` (visitor/device-bound, challenge + precursor clearance, **continuously updated**), `__cf_bm` (30-min **inactivity** expiry), `__cflb` | Fresh/unwarmed session, datacenter IP, TLS mismatch, clearance reuse | **Persistent real browser** (existing rayobrowse — warm profile proved in recon) + homepage-first warmup; session kept behaviourally alive. ⚠️ **G0 2026-08-16**: CloakBrowser FAILED (cold → enterprise Turnstile, human click → "Doğrulama Başarısız" even on vanilla flow) — driver stays rayobrowse; next candidate Scrapling StealthyFetcher | Retry warmup → rotate profile → IP change (one variable at a time) |
| **B2** | **PerimeterX/HUMAN behavioral** — `_px3` (re-issued per session), `_pxhd`, `window.PX.setChallenge`, obfuscated `init.js`, telemetry beacons | Behavioral score, fingerprint inconsistency, **telemetry discontinuity** (non-JS client stops beaconing), IP reputation | **Pass silently in one continuous browser session**: per-profile persistent context, `humanize=True` (only under B0 authorisation), consistent fingerprint (PX field map checklist) | Harvest fresh `_px3` per session → if `setChallenge`: **stop segment + preserve diagnostics** → NopeCHA only if authorised & required → ghostwire in lab only |
| **B3** | **Cloudflare Turnstile** — login only (`render=explicit`, sitekey read live from `#cloudflareTurnStileSiteKey`) | Login attempt only | **Avoid login entirely** — mission fields are in public search rows. On an index page, Turnstile = **"unexpected defence-state transition" → stop/degrade segment**, do not auto-solve | If authorised login ever needed: 2captcha (`2captcha-python`, US$1.45/1k) or NopeCHA; tokens single-use/300 s; manual solve remains |
| **B4** | **Rate limiting** — actual thresholds unknown (no credible public figure) | Request bursts | **Serial crawl, one city at a time**; existing cooldown schedule; **measure** request rate, session age, challenge rate, block recovery — drive policy from own logs | Adaptive backoff; spread across day based on own 2–4-week log correlation |
| **B5** | **Detail-page login walls** | Detail-page bursts | **Demoted** — all mission fields are in the index table; detail pages out of the normal daily path | Keep `is_login_page` detection; stop detail fetching for the day |
| **B6** | **Selector/parser quirks** — `init.js` DOM wrapper; Chrome rejects unquoted attribute values with digits/dots | — | **Quote attribute selectors**; prefer `getElementById`/class; **add schema assertions** (row-count range, link/ID agreement, price/date parse validation, city/district sanity) | — |
| **B7** | **IP reputation** | Low-rep IP | Start residential (passes silently — recon-verified); **stable identity + stable egress**; don't equate rotation with improvement | Residential proxies + `geoip=True`; profile↔IP rotation policy established experimentally |
| **B8** | **Mutable-pagination drift** ⭐ NEW | Offset pagination over a live inventory — records move between pages → duplicates/omissions | **Reconciliation is mandatory**: expected/observed counts, unique-ID count, duplicate rate, first/last-page checks, second lightweight pass on anomalous deltas | Bracket boundaries tested for inclusivity; still dedup on ID |
| **B9** | **Cross-stack network identity mismatch** ⭐ NEW | A non-browser HTTP client (wreq) diverges in TLS/H2/client-hints/headers/request-mode/connections; wreq predefined profiles stop at Chrome149 (note: CloakBrowser free binary is v146 — the one exact wreq match — but CloakBrowser is no longer a candidate) | **Not in default path.** If ever tested: G2b one-request identity experiment, same egress, full fingerprint capture, cookie-mutation comparison | Same-browser "middle layer" (same-origin fetch inside the trusted browser) before any external client |
| **B10** | **Persistence/history corruption** ⭐ NEW | Plain upsert destroys daily history; partial-run persistence; stale "active" status | **Snapshot-aware storage**: `listings_current` + `listing_observations` (unique `(run, ilanId)`) + `crawl_runs`; first_seen/last_seen/active flags | Crash recovery transactionally coupled to persistence (fetch→parse→validate→commit→manifest→checkpoint) |
| **B11** | **Tool/driver lifecycle** ⭐ NEW | Proprietary binary revocation/version drift, experimental CDP methods, profile corruption, closed-source maintenance | Pin installed driver version in benchmark artefacts; Windows forced-kill soak fixture; single-process run lock | Prefer OSS driver (Scrapling/Camoufox) as exit ramp |
| **B12** | **Agent/skill integrity** ⭐ NEW | Prompt injection from crawled content; unreviewed SKILL.md/tool updates | Deterministic extraction only — never send arbitrary listing HTML through an LLM; pin skills to reviewed versions; `--ai-targeted`-style guards for CLI scraping | — |

**Not elevated:** DataDome/Akamai/Kasada — no evidence on this site; keep in a generic "unknown vendor detection" signature table (Antibot-Detector in a diagnostic profile can watch for them).

## 3. Recommended architecture (revised 2026-08-16 — browser-only default)

```
        ┌───────────────────────────────────────────────────────────────┐
        │  GATE 0: access-policy decision (B0) + dated terms record     │
        └──────────────────────────┬────────────────────────────────────┘
                                   ▼
        ┌────────────────────────────────────────────────────────────────┐
        │  ONE PERSISTENT REAL-BROWSER SESSION (existing warm driver     │
        │  first; Scrapling only if G0 shows value)          │
        │  per-jar persistent profile · homepage-first warmup            │
        │  humanise ONLY under B0 authorisation                          │
        │  serial cities: Kayseri → Sivas → Tokat                        │
        │  index pages only: /kiralik/{city}?pagingSize=50&pagingOffset  │
        │  (+ price brackets ONLY if max-offset/cap demands it)          │
        └───────────────┬────────────────────────────────────────────────┘
                        ▼
        ┌───────────────────────────┐   ┌───────────────────────────────┐
        │  PARSE + ASSERT (B6)      │   │  GUARD RAIL (every page)      │
        │  tr[data-id] → ilanId     │   │  selector table + success     │
        │  quoted selectors only    │   │  selectors · PX setChallenge  │
        │  schema assertions        │   │  watch · is_login_page ·      │
        │  price-parser + dateparser│   │  tiny-body check              │
        │  (Turkish fixtures)       │   │  CHALLENGE = stop segment,    │
        └───────────┬───────────────┘   │  preserve diagnostics         │
                    ▼                   └───────────────┬───────────────┘
        ┌───────────────────────────────────────────────────────────────┐
        │  STORAGE — MongoDB (snapshot-aware, B10)                      │
        │  listings_current {ilanId, fields, first_seen, last_seen,     │
        │    active} + listing_observations {(run, ilanId) unique}      │
        │  + crawl_runs {segments, counts, status, errors}              │
        │  checkpoint: per-page idempotent transitions                  │
        └───────────────────────────────────────────────────────────────┘
                    ▲
        ┌───────────────────────────────────────────────────────────────┐
        │  RECONCILIATION (B8) — per-run: expected vs observed counts,  │
        │  unique-ID count, duplicate rate, bracket boundaries,         │
        │  anomaly-triggered second pass                                │
        └───────────────────────────────────────────────────────────────┘
```

**Demoted out of the default path (optional escalations, evidence-gated):**
- **wreq bulk layer** — only if browser-only misses a runtime SLO (G2); then G2b one-request identity experiment (B9) before any volume.
- **Same-browser middle layer** — same-origin fetch inside the trusted browser context; benchmark before any external client.
- **Automated CAPTCHA solving** — a challenge on an index page is a stop/degrade signal; solving is optional, permission-dependent, and chosen then.
- **ghostwire** — lab/diagnostic tool only (experimental CDP method).
- **Antibot-Detector / creepjs** — diagnostic profile only; never in the production path (B12, observer effects).

### 3.1 Layer-to-tool assignment (final, corrected)

| Layer | Tool | Why |
|---|---|---|
| Driver | **engine_selenium.py (NEW — friend-tactics, proven 3-month pattern)**: undetected-chromedriver + **persistent SeleniumProfile** (cookie-saving trust strategy; solve Turnstile once on day 1 → warm sessions after) + manual solve-retry loop + adaptive 2.5s pacing. rayobrowse/Playwright kept as legacy path. CloakBrowser FAILED G0 (2026-08-16: "Doğrulama Başarısız" cold+vanilla; free binary v146 not v150) | The friend's IstanbulAvrupa scraper ran daily for 3 months (24.5k rows/day) with this exact pattern — strongest evidence in the stack |
| Humanisation | `humanize=True`-class behavior **only under B0 authorisation** (ToS clause conflict otherwise) | Compliance gate |
| Extraction | Recon selectors (`tr[data-id]`, quoted attrs) + **schema assertions**; adaptive selectors as emergency recovery only | Deterministic contract > similarity |
| Normalization | **price-parser** + **dateparser** (`languages=["tr"]`) with exact Turkish fixtures in unit tests | Drift fix |
| Storage | **MongoDB snapshot-aware model** (current + observations + runs) | B10 |
| Captcha (login-only, optional) | **2captcha-python** (official vendor — NOT solvecaptcha-python) or NopeCHA; tokens single-use/300 s | Corrected vendor registry |
| QA | Antibot-Detector + creepjs in a **separate diagnostic profile**; fingerprint coherence, not "pass" | Observer-safe |
| Deep RE | ghostwire — lab only | Experimental CDP |
| Skills to install | playwright, webapp-testing, modern-python, mongodb-schema-design/connection, pytest, playwright-skill, scrapling-official (v0.4.8) + **author internally: scraper-operations, inventory/data-quality, observability** | §2.6 install set |

## 4. Decision gates (amended 2026-08-16)

1. **G0 — Authorisation + browser baseline, then driver shootout.** Record applicable terms/robots/access permission (B0) FIRST. Benchmark the **existing working driver first**; Scrapling StealthyFetcher only if switching has value (⚠️ CloakBrowser already FAILED this gate 2026-08-16 — removed from contention). Warm AND clean profiles. Metrics: HTTP outcome, unexpected login/challenge rate, `_px3` issuance/mutation, extraction correctness, startup time, median latency, profile recovery, total runtime. **No third-party CAPTCHA solving in this gate.**
2. **G1 — Identity coherence, not "fingerprint test passed".** Record fingerprint surface (UA/UA-CH, OS, screen/window, timezone, locale, memory, WebGL); verify intended stability within a profile and separation between profiles. Antibot-Detector on a **cloned diagnostic profile**. Final metric = silent normal browsing.
3. **G2 — Browser-only capacity first.** Complete three-city index crawl at production pacing in one browser. Passes if inside the runtime SLO (e.g., "all three cities within 45 min") with acceptable block/challenge rate → **wreq is not introduced**. Only on SLO miss: G2b same-browser fetch path, then wreq.
4. **G2b — Hybrid identity experiment (only if authorised and necessary).** ONE browser-cleared request to wreq under the same egress — not 100 pages. Capture full fingerprint (ClientHello, ALPN, H2 settings/order, headers/Client Hints, request mode, negotiated H3/H2); compare status/body and CF/PX cookie mutation. Expand only if equivalence observed. ⚠️ wreq predefined profiles stop at Chrome149; rayobrowse pins Chromium 146 (exact wreq match).
5. **G3 — Completeness + crash recovery.** Calculated final-page reachability per city, category-scope check, bracket-boundary inclusivity test, duplicate-ID ratio, expected-vs-observed counts, repeated-crawl reconciliation sample. Kill tests at three points (after fetch/before commit, during write, after commit/before checkpoint): no missing committed observations, no duplicate logical observations.
6. **G4 — Production soak (data correctness, not HTTP success).** ≥99.5% successful planned page ops after retry; zero unexplained segment gaps; 100% unique `(run, ilanId)`; duplicate-ID rate tracked; run count deltas explained or flagged; no unplanned login/CAPTCHA solves; p50/p95 latency; session age at failure; scheduler heartbeat. **A run with 100% HTTP 200s but a 7% ID deficit is a failed run.**

## 5. Risk register (revised)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **B0: ToS AI-agent provisions apply** | Medium-high | **High** | Resolve authorisation model before any stealth engineering; dated terms copy; approved data route (P2) |
| Identity discontinuity in any cookie handoff (B9) | Medium | High | Browser-only default; G2b one-request experiment before any bulk |
| PX starts challenging (B2) | Medium | High | Stop segment + diagnostics; NopeCHA only if authorised; IP/proxy change one variable at a time |
| Offset-pagination drift (B8) | Medium (frequency unknown) | Medium | Reconciliation + anomaly-triggered second pass |
| Driver replacement risk (rayobrowse closed-source beta; CloakBrowser FAILED G0) | Medium | Medium | OSS exit ramp: Scrapling StealthyFetcher (Camoufox) — benchmark at G0 before relying |
| wreq profile mismatch (B9) | High if hybrid attempted | High | Not in default path; G2b proves equivalence first |
| CF session lifetimes mis-assumed (B1) | Medium | Medium | Measure own session; `__cf_bm` = 30-min inactivity |
| Tool claims unverified (rayobrowse v0.2.1 stability, NopeCHA PX) | Medium | Medium | G0/G2b benchmarks; treat vendor claims as marketing until proven |
| Rate limiting (B4) | Medium | Medium | Serial crawl; empirical thresholds from own logs |

## 6. Milestones (revised)

1. **M0 (compliance + recon refresh)**: B0 access-policy decision + dated terms/robots record; one authorised warm-browser homepage + listing page (re-verify stack, sitekey, max offset, bracket inclusivity); capture HAR/cookie names.
2. **M1 (benchmarks)**: G0–G2 — authorisation recorded, existing-driver baseline, fingerprint coherence (diagnostic profile), browser-only three-city run vs SLO.
3. **M2 (core rewrite)**: modular scraper (browser / anti-bot / parsers / storage / checkpoint / cli), recon selectors, per-jar profiles, **snapshot-aware Mongo model**, price/date fixtures, schema assertions, unit tests (parse_page, normalize_price, is_login_page, pagination math).
4. **M3 (reconciliation + ops)**: run manifests, expected/observed counts, duplicate/omission checks, alerting, scraper-operations + inventory/data-quality + observability skills.
5. **M4 (soak)**: G3 crash tests, then G4 seven-day soak.
6. **M5 (measured escalations only)**: only if evidence demands — G2b hybrid experiment (wreq or same-browser fetch), optional authorised captcha solve, ghostwire lab work.

**Exit criteria:** 3 cities scraped daily within SLO; ≥99.5% page success AND zero unexplained ID deficits over 7 days; zero manual interventions in last 3 days; snapshot-aware inventory in Mongo; compliance decision documented.

**Data scope (locked 2026-08-16, law-faculty confirmed):** output fields are exactly **`District, Rooms, Price, ilanId`** (+ run date via filename/run metadata). The `ilanId` comes from `tr[data-id]` in the public search table — it is a listing identifier, not personal data. No detail-page crawling ever (contact info, advertiser names, photos live there). Existing CSVs (`District,Rooms,Price`) remain valid; the modernization adds the ID column.

---

## 7. Site reconnaissance (2026-08-15)

Live browser-session findings (browser-use CDP on a warm Chrome profile with existing `cf_clearance`). ~17 navigations (homepage, Kayseri/Sivas/Tokat listing pages, price-bracketed pages, pagination pages, one detail page, login page). **Zero captchas, zero blocks** in a warm session. Homepage-first navigation was naturally satisfied (valid Cloudflare cookies from prior human browsing).

### 7.1 Access model

| Path | Works? | Notes |
|---|---|---|
| `https://www.<site>/` | ✅ | No challenge |
| `https://www.<site>/kiralik/{city}` | ✅ | Listing page; default 20/page |
| `...?pagingSize=50&price_min=X&price_max=Y` | ✅ | Bracket filtering works, 50/page |
| `...&pagingOffset=N` | ✅ | Offset = (page-1) × pageSize |
| `/ilan/emlak-konut-kiralik-...-{ilanId}/detay` | ✅ | Detail page, NO login wall on warm session |
| `https://secure.<site>/giris/` | ✅ | Login page, Turnstile present |

### 7.2 Anti-bot stack (current, 2026-08-15)

1. **Cloudflare edge**: `cf_clearance` (valid → ~2027 in this profile — **do not generalise**: Challenge Passage default 30 min, zone-configurable, per research report), `__cf_bm` (30-min inactivity expiry), `__cflb`. No Turnstile on browse pages.
2. **PerimeterX (Human Security)**: cookies `_px3` (re-issued per session), `_pxhd`, `_pxvid`; `window.PX = {Events, ClientUuid, setChallenge}`; SDK bundled in obfuscated `init.js`; telemetry to `ift.px-cloud.net`. No challenge triggered in-session.
3. **Turnstile on login only**: `render=explicit`; sitekey `0x4AAAAAAADCdLU7KqusGUET` at recon time — **always read live** from `#cloudflareTurnStileSiteKey`.
4. **Other**: GTM, OneTrust, `analytics:1.js`, prebid. Not anti-bot.

### 7.3 Site structure (verified 2026-08-15)

**Listing counts:** Kayseri 101 pages @20 (~2,020) · Sivas 51 (~1,020) · Tokat 48 (~960). At `pagingSize=50`: ~41 + ~21 + ~20 ≈ **82 pages total**. Kayseri sidebar: Daire 1,896 · Villa 68 · Müstakil Ev 35 · Rezidans 12 (category scope decision needed — see B6/G3).

**Search results table:** `#searchResultsTable` → `tbody tr` with **`data-id` = ilanId**; link format without city slug (`/ilan/emlak-konut-kiralik-...-{ilanId}/detay`); cells `[advert-type, title, area m², rooms, price, date, district]`; price `17.900 TL` (dot thousands); date `10 Ağustos\n2026`.

**Pagination:** `.pageNavigator` / `ul.pageNaviButtons` / `#currentPageValue` / `a.prevNextBut`; `pagingOffset=(page-1)*pageSize`; `pagingSize=50` verified; pager text `Toplam 8 sayfa içerisinde 2. sayfayı görmektesiniz.` Max usable offset **not yet verified** (G3).

### 7.4 Gotchas (verified)

1. **Quote attribute selectors** — Chrome's native parser rejects unquoted attribute values with digits/dots (reproduced on `about:blank`); the site's `init.js` also shadows `querySelector` with a passthrough `EQ` wrapper (toString-spoofed).
2. **`_px3` refreshes each session** — cookie pools must refresh PX tokens.
3. **Turnstile explicit-render only** — widget absent until the login flow triggers it.
4. **No login wall on detail pages** in a warm session (first page tested) — but detail pages are now out of the normal path anyway (B5).

### 7.5 Implications for the scraper

- Warm persistent browser + homepage-first is sufficient; keep the warmup.
- Read Turnstile sitekey live; parse `tr[data-id]`; quote attribute selectors; schema-assert everything.
- PX `setChallenge` / `_px3` mutation → block signal alongside login-page detection.
- 16 Aug 2026 note: generic stateless HTTP clients get **403** (all three tested routes) — corroborates browser-only default.

### 7.6 Open questions (untested)

- Max usable `pagingOffset`; bracket inclusivity at boundaries; live-churn rate (reconciliation thresholds); repost `ilanId` semantics; displayed-date meaning (publication vs renewal); session lifetime under real usage; DataDome/Akamai/Kasada absence confirmation.
