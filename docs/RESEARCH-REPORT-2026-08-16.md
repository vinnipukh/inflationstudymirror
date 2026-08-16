# Deep Research Report — Gap Hunt & Validation (2026-08-16)

**Status:** received from deep-research agent, 16 August 2026. This file is the
verbatim validation report. It is the authoritative source for the revisions
applied to `docs/APPROACH.md` and `docs/TECH-STACK-SEARCH.md` on 2026-08-16.

**Research cut-off:** 16 August 2026, Europe/Istanbul.
**Baseline:** 15 Aug 2026 live recon, proposed approach, tool catalogue, local scraping-wiki snapshot.

---

## Executive verdict

- **The browser-first core is sound; the browser→wreq bulk layer is not yet justified or validated.** Recon shows ~2,020 + 1,020 + 960 listings and confirms `pagingSize=50`; that is only about **82 index-page requests** for all three cities. At the proposed 8–12 s pacing plus a 30–90 s pause every 20 pages, the deliberate waiting budget is roughly **13–22 minutes** — not "hours". The business case for a second TLS/network stack is much weaker than assumed.
- **P0 identity-continuity gap in the hybrid flow.** CloakBrowser advertises Chromium **150** on all plans; wreq's predefined Chrome emulations stop at **Chrome149**. Cloudflare documents `cf_clearance` as visitor/device-bound with continuously updated precursor state; recon observed PX telemetry and re-issued `_px3`. Cookie copy alone cannot be assumed to recreate browser identity in a non-JS HTTP client.
- **The most important missing blocker is not technical: Sahibinden's published usage conditions.** Current terms contain explicit AI-agent rules: identification in the User-Agent, prohibition of human keystroke/navigation/interaction simulation, and observance of CAPTCHA, firewall, rate-limiting and `robots.txt` controls. `humanize=True`, stealth identity and a CAPTCHA-bypass ladder conflict with that wording **if those provisions apply**. "Public, no login required" is insufficient as an authorisation model. Resolve applicability/permission before making bypass technology a production dependency.
- **Several tool-catalogue assertions need correction:** CloakBrowser free tier is v150 (not an older pin); wreq has Chrome146 but no predefined 150/151; Scrapling's official skill is **v0.4.8**, not v0.4.14; `unicaps` does **not** list Turnstile; `solvecaptcha-python` is the **solvecaptcha.com** client, not the official 2Captcha client (`2captcha-python`). NopeCHA advertises Turnstile+PX, but a May 2026 PX issue shows PX handling is not deterministic enough for a production fallback.
- **Data completeness deserves as much engineering as anti-bot evasion.** Offset pagination over a live, mutating inventory can duplicate/omit listings; price brackets can duplicate boundary prices; plain MongoDB upsert on `ilanId` destroys price/listing-state history; max `pagingOffset` and repost-ID semantics unverified. Acceptance cannot be merely ">99.5% page success" — it needs run-level inventory reconciliation, unique-ID counts, duplicate/omission checks, bracket-boundary checks, and historical observations.

**Overall verdict: conditionally sound after simplification.** Promote: one persistent real-browser session, serial city crawling, index pages only, deterministic extraction, snapshot-aware MongoDB, strong reconciliation. Demote wreq, automated CAPTCHA solving and ghostwire out of the critical path — optional escalation experiments only after the browser-only path demonstrates an actual deficiency, and after the access/compliance gate is resolved.

---

## Site state today (16 Aug 2026)

- 15 Aug warm-browser recon remains the strongest evidence: CF cookies (`cf_clearance`, `__cf_bm`, `__cflb`), PX/HUMAN cookies (`_px3`, `_pxhd`, `_pxvid`, `window.PX.setChallenge`, obfuscated `init.js`, telemetry to `ift.px-cloud.net`), Turnstile on login only (sitekey `0x4AAAAAAADCdLU7KqusGUET`, explicit render). ~17 navigations, zero blocks.
- 16 Aug lightweight refresh: homepage, Kayseri search, login page all returned **HTTP 403 to a generic web client**. Corroborates stateless/generic HTTP rejection; does not disclose which layer blocked.
- Cloudflare docs (Jul 2026): `cf_clearance` = challenge + precursor clearance, continuously updated from session behaviour, visitor/device-bound; Challenge Passage defaults to 30 min (zone-configurable). Recon profile's 2027 expiry must NOT be generalised to "clearance persists months". `__cf_bm` = bot-score info, expires after 30 min of **inactivity**.
- Community: `tyegen/sahibinden-emlak-scraper` reports aggressive blocking, mandatory-login redirects for new proxy identities, recommends session cookies/residential Turkish egress, low concurrency (community evidence, not ground truth). Chrome extension "Olağan dışı erişim tespit ettik" (updated 8 Apr 2026) — weak signal unusual-access blocking is operational.
- **No credible "best time of day" or fixed "30 pages/session" figure exists** — remove as factual assumptions; drive from own logs.
- Detail-page crawling unnecessary: index rows already carry `tr[data-id]` (ilanId), detail URL, district, rooms, price, date.
- **Kullanım Koşulları** (retrieved 16 Aug): dedicated AI-agent provisions — agent UA identifier required, concealment/human-interaction imitation prohibited, CAPTCHA/firewall/rate/robots controls must be respected; programmatic access may be blocked when conditions are breached/suspected. Formal API/data-transfer mechanism exists but is documented for authorised businesses transferring **their own corporate-store listing data**, not a general public-search inventory API.

### Stack confidence table

| Layer | Status | Confidence |
|---|---|---|
| Cloudflare edge / bot controls | Confirmed baseline + current generic 403 | High |
| PerimeterX / HUMAN | Confirmed 15 Aug; not DOM-reconfirmed 16 Aug (403) | High baseline / medium unchanged-today |
| Turnstile on browse/search | Not observed 15 Aug; no evidence of change | Medium-high |
| Turnstile on login | Verified 15 Aug (explicit, sitekey above) — read live; today's value unverified | High yesterday |
| DataDome / Akamai / Kasada | No evidence found — not proven absent | Medium |

---

## Tool validation table (corrections vs local catalogue)

| Tool / claim | Validation | Risk |
|---|---|---|
| CloakBrowser free binary version | **v150 on all plans** (first-party site). Remove "older pin" assumption unless an installed binary says otherwise | Medium |
| CloakBrowser "71 patches / 30+ tests / 0.9 reCAPTCHA v3" | **Vendor claim only** — no independent controlled reproduction found; treat as marketing until G0 | High if used as selection evidence |
| CloakBrowser licence | MIT wrapper, proprietary binary (BINARY-LICENSE v1.3). Permits internal scraping use; restricts redistribution/reverse engineering; vendor lock-in, not takedown | Medium-high |
| wreq Chrome profiles | Chrome **146, 147, 148, 149** — **no 150/151**; no exact match for CloakBrowser v150 | High for hybrid critical path |
| wreq "149 ≈ 150" | Unverified — wreq says "often identical", not equivalent; must be measured (ClientHello, ALPN, H2 settings/order, headers, H3) | High |
| wreq build | Rust/BoringSSL toolchain for source builds; prebuilt distribution exists; Windows supported | Medium-high |
| Scrapling adaptive parsing | Verified feature, but **overstated for repeating rows** — similarity relocation is not a semantic guarantee for repetitive tables; fallback only around invariant `tr[data-id]` + schema/count assertions | Low-medium |
| Scrapling StealthyFetcher | Official capability claim (auto Turnstile/interstitial, CDP/WebRTC mitigation) — not independently verified on Sahibinden; genuine G0 experiment | Medium |
| Scrapling spiders pause/resume | Verified (checkpointed `crawldir`, graceful Ctrl+C, resume; recent dedup fixes) — own crash tests still needed | Low-medium |
| Scrapling official skill | **v0.4.8** (409 lines), requires `--ai-targeted` for CLI (prompt-injection guard). Catalogue's v0.4.14 unsupported | Low-medium |
| solvecaptcha-python | **solvecaptcha.com client — NOT official 2Captcha.** Official: `2captcha/2captcha-python`. Correct naming before implementation | Medium |
| 2Captcha Turnstile | Supported, **US$1.45/1,000**; standalone widgets + Challenge pages; pricing table shows "0 sec" speed — benchmark latency yourself | Low (optional login fallback) |
| "Turnstile tokens UA-bound" | **Overstated.** Cloudflare: tokens single-use, **300 s** validity; no universal UA-binding rule. 2Captcha Challenge flow does require returned UA — record the narrower rule | Medium if integration assumes it |
| NopeCHA Turnstile + PX | Verified vendor capability; free 100 req/day/IP; paid from US$4.99/mo (2,000 solves/day) | Medium |
| NopeCHA PX reliability | **Partial** — May 2026 issue: PX stuck after press-and-hold. Comparison table stale (Jan 2025, wrongly says 2Captcha lacks Turnstile). Do not use that table | Medium-high for PX |
| unicaps Turnstile | **Refuted** — support matrix lists image/text, reCAPTCHA v2/v3, FunCaptcha, KeyCAPTCHA, GeeTest, hCaptcha, Capy — **no Turnstile** | High if relied on |
| ghostwire maturity | Young: 69 stars, 2 forks, **no releases**; arms-race caveat (CDP presence detectable) | Medium-high |
| ghostwire `Debugger.setBreakpointOnFunctionCall` | Exists in CDP but marked **Experimental**; tip-of-tree has no backwards-compat guarantee; PX-VM hooking unproven | High as dependency, acceptable as lab tool |
| price-parser `17.900 TL` | Partially verified — separator logic handles dot-grouped amounts; **add exact fixture + Turkish boundary cases to unit tests** | Low |
| dateparser `10 Ağustos 2026` | Strongly supported (Turkish locale); pass `languages=["tr"]`; exact fixtures recommended | Low |
| Antibot-Detector | Capability verified; **accuracy unverified** (no TP/FP benchmark); installs JS hooks at `document_start` → **separate diagnostic profile only**; licence **NPOSL-3.0** — review if bundled | Medium |
| CreepJS as pass/fail gate | **Misuse** — diagnostic only; replace with "fingerprint values internally coherent and stable where intended" | Low |
| rayobrowse vs CloakBrowser vs Scrapling | No new Sahibinden evidence picks a winner; existing warm session already succeeded; G0 A/B is the right method | Medium |

**Consequence:** captcha solving should not be a major design axis. All six required fields are in public search-table rows; the only Turnstile observed was login. Treat a CAPTCHA on ordinary listing pages as a **stop/degrade signal**, not an invitation to invoke a paid solver.

---

## Gap findings (prioritised)

**P0 — Access/compliance gate (B0)** before anti-detection engineering. Retain dated copy of terms/robots policy. If stealth/humanisation is required, obtain permission or an approved data-access arrangement first. (Operational/contractual recommendation, not legal advice.)

**P0 — Remove wreq from default critical path.** No exact Chrome150 profile; handoff transfers only selected HTTP state, not browser process/network/JS runtime/storage/PX telemetry; CF clearance is visitor/device-bound and continuously updated. Browser-only first; hybrid only after measured runtime requirement + a dedicated one-request identity experiment.

**P0 — Correct the performance premise.** ~82 pages/day total; 13–22 min deliberate-delay budget at proposed pacing. Define runtime SLO first (e.g., "all three cities within 45 minutes"); add a bulk layer only if browser-only violates it consistently.

**P0 — Completeness as a first-class gate.** Offset pagination against a live inventory can duplicate/omit records; bracket inclusivity at boundaries must be determined empirically (`price_max=A` vs next bracket's `price_min=A`); dedup recovers duplicates but not skips. Add expected/observed counts, unique-ID count, duplicate rate, first/last-page reconciliation, second lightweight pass on anomalous deltas.

**P1 — Inventory model:** not plain `upsert({ilanId})`. Use `listings_current` (keyed ilanId, with first_seen/last_seen/active flag) + `listing_observations` (unique `(run_date, ilanId)`) + `crawl_runs` (segments, counts, status, errors). Crash-recovery auditable.

**P1 — ilanId repost semantics unverified** — never treat as permanent property ID; track a sample over days; fuzzy secondary identity only if needed.

**P1 — Category scope decision** — `/kiralik/{city}` vs `/kiralik-daire`: define inclusion rule in schema; test in G3; do not blindly merge superset URLs.

**P1 — Max offset validation** — one normal-browser visit to each city's calculated final page; price brackets only if a cap or completeness benefit is demonstrated.

**P1 — CF session lifetime language** — `__cf_bm` 30-min inactivity expiry; `cf_clearance` Challenge Passage default 30 min, zone-configurable; measure own session, don't schedule from hard-coded lifetimes.

**P1 — Same-IP handoff as experiment requirement**, not proven universal rule.

**P1 — Identity surface > TLS** — compare negotiated protocol, ClientHello/extension order, H2 settings/pseudo-headers, UA/Client Hints, Accept-*, locale/timezone, cookies, request context, egress identity, H3/QUIC when negotiated.

**P1 — Same-browser "middle layer"** (same-origin fetch inside the trusted browser context) worth benchmarking before wreq — preserves process/egress/network stack; different Fetch Metadata semantics, still needs A/B.

**P1 — Rate limiting adaptive/empirical** — serial, one city at a time; structured measurements; increase concurrency only after soak shows margin.

**P1 — Multi-city parallelism has negative expected value at ~82 pages/day** — serial cities under one identity first.

**P1 — CAPTCHA service architecture overbuilt** — challenge on search page = stop segment + preserve diagnostics; no automatic paid-bypass loop.

**P1 — Correct captcha dependency registry now** (vendor names, unicaps Turnstile absence, NopeCHA PX nondeterminism).

**P1 — QA extensions must not contaminate production fingerprint** — separate `diagnostic-profile` vs minimal `production-profile`.

**P1 — Crash recovery transactionally coupled to persistence** — per-page idempotent transitions: fetch → parse → validate → commit observations → record page manifest/checksum/count → advance checkpoint. Mongo = source of truth; Scrapling crawldir = scaffolding only.

**P1 — Agent-side content/skill supply-chain security** — deterministic extraction without sending arbitrary listing HTML through an LLM; pin skills to reviewed versions; `--ai-targeted` style prompt-injection guards.

**P1 — Skills: operations + data-quality + observability over another stealth skill** — author internally: scraper-operations (leases, scheduler, checkpoints, retries, run manifests), inventory/data-quality (snapshots, first/last seen, reconciliation, anomaly thresholds), observability (structured events, metrics, alerts, evidence bundles). Docker skill only if the winning driver deploys in Docker.

**P2 — Adaptive selectors = emergency recovery only**; require semantic checks before committing recovered data.

**P2 — ghostwire after diagnostics, not in the detection ladder** (experimental CDP, arms race).

**P2 — DNS leakage / TLS session resumption: investigation items, unsupported blockers today** — record, don't speculate.

**P2 — Explore an official/internal data route** — Sahibinden documents an API/data-transfer programme (authorised corporate-store transfer); ask about research/partner/feed/licensed inventory interface — even paid could beat maintaining two anti-detection stacks.

**P2 — Windows not a blocker** — profile lifecycle, process cleanup, source-build tooling are the real risks; Windows soak fixture (forced kills, profile-lock recovery, run lock, no overlapping scheduler).

---

## Threat model delta (B0, B8–B12 added)

| Threat | Amendment |
|---|---|
| **New B0 — access-policy/contractual controls** | Before every technical blocker: ToS AI-agent provisions (UA identification, no human-interaction mimicry, respect CAPTCHA/firewall/rate/robots). Determine applicability/authorisation first |
| B1 Cloudflare | Replace "cf_clearance persists months" with "site/session dependent"; visitor/device binding, precursor clearance, continuous updating, `__cf_bm` inactivity expiry, sequencing, clearance-reuse rate limiting — possible capabilities, not all proven enabled |
| B2 HUMAN/PX | Keep and promote; add **telemetry continuity** (browser executes PX code, `_px3` re-issued; non-JS stack needs its own acceptance proof) |
| B3 Turnstile | Narrow: login only, outside collection requirement; on index page = "unexpected defence-state transition" → stop/degrade; automated solve optional and permission-dependent; sitekey always read live |
| B4 Rate limiting | Remove unsupported fixed thresholds; track empirical request rate, session age, challenge rate, block recovery |
| B5 Detail-page walls | Demote — mission fields are in search results |
| B6 Selector/parser quirks | Keep quoted-selector rule; add schema assertions (row count range, link/ID agreement, price/date parse validation, city/district sanity) |
| B7 IP reputation | Keep; don't equate rotation with improvement; stable identity + stable residential egress may be safer; profile↔IP rotation policy experimental |
| **New B8 — mutable-pagination drift** | Offset pages ≠ snapshot isolation; changing ordering → omissions/duplicates; reconciliation mandatory |
| **New B9 — cross-stack network identity mismatch** | TLS/H2/client-hints/header/request-mode/connection divergence browser↔wreq; wreq profiles end at 149 vs CloakBrowser 150 |
| **New B10 — persistence/history corruption** | Loss of time-series history, partial-run persistence, stale "active" status — overwrite/upsert does not represent history |
| **New B11 — tool/driver lifecycle** | Proprietary binary revocation/version drift, experimental CDP changes, profile corruption, closed-source maintenance |
| **New B12 — agent/skill integrity** | Prompt injection from crawled content; unreviewed SKILL.md/tool updates |

Do NOT elevate DataDome/Akamai/Kasada to confirmed B-items — keep in a generic "unknown/new vendor detection" signature table.

---

## Decision-gate amendments

| Gate | Amended |
|---|---|
| **G0** | Authorisation + terms record FIRST; benchmark the **existing working driver first**, then CloakBrowser/Scrapling only if switching has value; warm AND clean profiles; metrics incl. `_px3` issuance/mutation, extraction correctness, startup, latency, profile recovery, total runtime; no third-party CAPTCHA solving in this gate |
| **G1** | "Identity coherence, not fingerprint-test-passed": record fingerprint surface values, verify intended within-profile stability and between-profile separation; Antibot-Detector on a cloned diagnostic profile; final metric = silent normal browsing |
| **G2** | **Browser-only three-city index crawl first** at production pacing; passes if inside SLO with acceptable block rate → **wreq not introduced**. Only on SLO miss: G2b same-browser fetch path, then wreq |
| **G2b** | Hybrid identity experiment: ONE browser-cleared request to wreq, same egress, capture full fingerprint (ClientHello, ALPN, H2 settings/order, headers/Client Hints, request mode, negotiated H3/H2); compare status/body and CF/PX cookie mutation; expand only if equivalence observed |
| **G3** | Completeness + crash recovery: final-page reachability, category scope, bracket boundary, duplicate-ID ratio, expected-vs-observed counts, repeated-crawl reconciliation; kill tests at 3 points (after fetch/before commit, during write, after commit/before checkpoint); no missing committed observations, no duplicate logical observations |
| **G4** | Production soak, **data correctness not just HTTP success**: ≥99.5% successful planned page ops after retry; zero unexplained segment gaps; 100% unique `(run, ilanId)`; duplicate-ID rate tracked; count deltas explained/flagged; no unplanned login/CAPTCHA solves; p50/p95 latency; session age at failure; scheduler heartbeat. A run with 100% HTTP 200s but a 7% ID deficit is a failed run |

Original G2's "100 pagination pages with zero blocks" is problematic — zero-event over one artificial batch says little; production need is ~82 pages/day at size 50. Measure the exact production pattern.

---

## Open questions & cheapest tests

1. Stack unchanged on 16 Aug? → one authorised warm-browser homepage + listing page; save HAR/cookie names/script hosts.
2. Turnstile still login-only, sitekey same? → one login-page DOM inspection of `#cloudflareTurnStileSiteKey`; no credentials.
3. DataDome/Akamai/Kasada active? → one diagnostic profile with Antibot-Detector + HAR inspection (not production).
4. CloakBrowser installed build really v150? → print installed version at install time; pin in benchmark artefact.
5. Cloak's 71 patches materially better on Sahibinden? → A/B vs existing working driver, same segment/IP/time window; no solver.
6. wreq Chrome149 ≈ Cloak Chromium150? → compare against a controlled fingerprint endpoint (full ClientHello, ALPN, H2 settings/order, headers, H3/H2); never JA3 alone.
7. Browser cookies → wreq handoff works? → after permission: one browser-cleared request + one same-IP wreq request; compare response/challenge indicators/cookie mutation.
8. Same-IP requirement? → same IP initially; change one variable at a time; conservative assumption, not fact.
9. Healthy session lifetime? → passive telemetry (cookie issue/change times, session age at first challenge); don't drive to failure.
10. Max `pagingOffset`? → navigate once to each city's calculated final page at size 50; remove unnecessary brackets if it works.
11. Price filters inclusive at both ends? → compare adjacent-bracket ID sets at one known boundary price; still dedup on ID.
12. Live offset movement omit rows? → two sequential small snapshots; compare ordered IDs; build reconciliation thresholds from real churn.
13. Repost keeps ilanId? → seven-day sample of known IDs; manual inspection of disappear/reappear.
14. Displayed date = publication or renewal? → compare row date vs detail-page "İlan Tarihi" for 5–10 listings in a permitted manual session.
15. price-parser corpus? → offline fixtures: `17.900 TL`, `4.500 TL`, `16000 TL`, `1.000.000 TL`, whitespace/NBSP, `₺`, empty/invalid; exact integer expectation.
16. dateparser determinism? → offline tests: 12 Turkish month names, newline forms, year boundaries, `languages=["tr"]`.
17. Scrapling adaptive confusion on repeated rows? → offline fixture: move columns/rows, mutate classes; require data-id/field-count/semantics match.
18. Scrapling resume after hard kills? → fixture crawl + Mongo test DB; kill at commit boundaries; assert manifest + unique keys.
19. NopeCHA on Sahibinden's specific PX? → do NOT trigger intentionally; provider/demo environment only.
20. ghostwire vs this PX VM? → offline/saved obfuscated script or authorised lab only.
21. Better time of day? → 2–4 weeks of scheduled outcomes correlated with hour; no forum anecdotes.
22. Windows crash semantics? → 10 cycles launch → work → forced kill → relaunch; overlapping-scheduler lock test.
23. Formal feed/API available? → ask Sahibinden for approved research/data/feed route before investing in bypass infrastructure.

**Cheapest high-information sequence:** access-policy decision → browser-only complete run → completeness reconciliation → seven-day browser-only soak. Only after those results, consider proving cross-stack browser→wreq identity.

---

## Final validation judgement

The design correctly identified the important technical actors — Cloudflare, HUMAN/PerimeterX, persistent browser identity, index-table extraction, checkpointing, data validation — but **overweights bypass technology and underweights permission, identity continuity and inventory correctness**. The highest-confidence production path is not CloakBrowser→wreq→captcha service→ghostwire; it is **approved access mode → one proven persistent browser → public search rows only → serial crawl → immutable daily observations + current state → reconciliation → measured escalation only when evidence requires it**.

---

## Sources (key)

Local: 15 Aug recon, approach, catalogue, wiki snapshot · Sahibinden live fetches 16 Aug (403s) · Sahibinden Kullanım Koşulları + Kurumsal Hesap Sözleşmesi + API data-transfer help page (16 Aug) · `tyegen/sahibinden-emlak-scraper` (community) · "Olağan dışı erişim" Chrome extension (8 Apr 2026) · Cloudflare cookies/Challenge Passage/clearance/rate-limit docs (May–Jul 2026) · Turnstile token docs (May 2026) · CloakBrowser site + BINARY-LICENSE v1.3 (Jul 2026) · wreq-python docs (Aug 2026) · Scrapling repo/skill v0.4.8/StealthyFetcher docs · solvecaptcha-python + 2captcha-python repos · 2Captcha pricing/API · NopeCHA extension v0.6.1 + pricing + PX issue #278 (7 May 2026) + stale comparison table (Jan 2025) · unicaps README · ghostwire (69★, no releases) + CDP docs (Experimental flag) · price-parser, dateparser · Scrapfly Antibot-Detector (NPOSL-3.0).
