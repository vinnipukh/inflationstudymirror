# Deep Research Agent Prompt — Sarı Site Scraper: Gap Hunt & Validation

> Copy everything between the lines below. Adjust only the research budget/time constraints.
> Suggested: run with deep research enabled, 2+ hours, web access, 2-4 iterations.

---

## Role

You are an elite web-scraping and anti-bot research analyst. Your job is to **stress-test a proposed architecture for scraping sarı site (Turkish classifieds) and find anything we missed** — missing tools, wrong assumptions, outdated claims, licensing traps, operational risks, or better alternatives. You are NOT writing code. You ARE producing a validation report with prioritized findings.

## Mission

Our goal: **reliably collect daily rental listings (Kayseri ~2,020 / Sivas ~1,020 / Tokat ~960 listings) from sarı site** — fields: ilanId, listing link, district, rooms, price, date. Data is public (no login needed for listing pages). The site is protected by a layered anti-bot stack. We have a proposed architecture (below) built from prior research. **Find the flaws, the gaps, and the missing pieces.**

## Context — read these first (local files)

1. `docs/APPROACH.md` — the proposed approach: threat model (blockers B1–B7), architecture, decision gates G0–G4, risk register, milestones
2. `docs/TECH-STACK-SEARCH.md` — the full tool/skill catalog with verified metadata (CloakBrowser, Scrapling, wreq, NopeCHA, solvecaptcha-python, ghostwire, Antibot-Detector, price-parser, etc.)
3. `docs/APPROACH.md` §7 — live site recon (merged): anti-bot stack observed (Cloudflare cf_clearance/__cf_bm/__cflb, PerimeterX _px3/_pxhd/_pxvid, Turnstile on login only, sitekey), page structure (#searchResultsTable, tr[data-id], pagination pagingOffset/pagingSize, price brackets), selector quirks
4. `docs/scraping-wiki/README.md` + relevant entity/concept pages (cloudflare.md, rayobrowse.md, camoufox.md, hybrid-scraping.md, cookie-session-reuse.md, homepage-first-navigation.md, bot-detection.md, cdp-detection.md, mouse-movement-emulation.md)

## Our proposed architecture (summary — validate this)

- **Driver:** CloakBrowser (C++-patched stealth Chromium, humanize=True, `launch_persistent_context()` per cookie jar) — benchmark alternatives: current rayobrowse, Scrapling StealthyFetcher (Camoufox)
- **Bulk layer:** wreq/wreq-python (Rust, extension-level TLS/HTTP2 emulation, 100+ profiles) fetching pagination pages with fresh cookies handed off from the browser session; TLS profile must match driver's Chromium version
- **Anti-bot stance per layer:** Cloudflare edge → real browser + homepage-first warmup; PerimeterX → silent pass via per-profile persistence + humanize + consistent fingerprint (using a PX field map: screen/window/memory/UA/timings); Turnstile → avoid login entirely (data is public), service fallback via 2captcha (solvecaptcha-python, Turnstile verified) or NopeCHA (also PX-capable); rate limiting → cooldowns + profile rotation
- **Parsing:** recon selectors (quoted attribute selectors only), adaptive-selector pattern (Scrapling-style), price-parser + dateparser + Pydantic, MongoDB upsert on ilanId, idempotent checkpoint/resume
- **Detection ladder:** selector-table + success-selector polling (detect → solve → confirm), PX setChallenge watch, is_login_page, tiny-body check → retry warmup → rotate profile → manual solve → service captcha → ghostwire diagnosis
- **QA:** Antibot-Detector extension + creepjs in-session verification; fingerprint checklist from PX field map + DataDome check list

## Research tasks — do ALL of these

### A. Validate the site's current state (live, today)
1. **Recon refresh:** independently verify the current anti-bot stack on sarı site — still Cloudflare (cf_clearance/__cf_bm) + PerimeterX (_px3/_pxhd)? Any new layers (DataDome, Akamai, Kasada)? Is Turnstile still login-only? Same sitekey? (Use public sources, the wiki, forum reports — do NOT hit the site aggressively.)
2. **Search for recent (2025–2026) reports** of sarı site-specific scraping blocks, PX challenges, Cloudflare changes, or rate-limit tightening. Any known "best time to scrape" or session-length limits reported by others?

### B. Validate every tool in the stack (claims vs reality)
3. **CloakBrowser:** verify the free-tier binary's pinned Chromium version (it must match a wreq profile for TLS matching). Verify the "71 C++ patches / 30/30 tests / 0.9 reCAPTCHA v3" claims are independently confirmed anywhere. License risk: binary is proprietary (BINARY-LICENSE v1.3) — any reported takedowns, ToS issues, or bans from using it?
4. **wreq/wreq-python:** confirm profile list includes Chrome 146/150/151-class profiles; confirm JA3/JA4 stability across nearby Chromium versions (does Chrome 149 profile ≈ Chrome 150 TLS?); any known issues with Cookie Store persistence, HTTP/2 fingerprinting against Cloudflare, or the Rust build requirement?
5. **Scrapling:** validate the adaptive-parser behavior (does it handle table-row relocation?), StealthyFetcher's current Turnstile/Cloudflare success against strict sites in 2026, spider pause/resume correctness, and the official agent skill's quality. Compare Scrapling's Camoufox base vs CloakBrowser for sarı site specifically.
6. **Captcha services:** verify current (2026) Turnstile support in 2captcha (solvecaptcha) and NopeCHA; which actually solves PerimeterX challenges, at what cost/speed; whether tokens are truly UA-bound; free-tier limits (NopeCHA 100/day?).
7. **ghostwire:** maturity check (age, stars, maintenance), whether its MCP server works with current Chrome/CDP versions, and whether the Debugger.setBreakpointOnFunctionCall approach survives PX's VM-obfuscation.
8. **Supporting tools:** price-parser + dateparser handling of Turkish formats (`17.900 TL`, `10 Ağustos 2026`); Antibot-Detector extension's accuracy; unicaps Turnstile support (we marked it unverified — check).

### C. Architecture-level gap hunt (think adversarially)
9. **Missed blockers:** any anti-bot layer we haven't accounted for (e.g., JS challenges beyond Turnstile, TLS fingerprinting at CDN level, HTTP/2 fingerprinting, DNS-based detection, TLS session resumption checks, behavior scoring beyond mouse)?
10. **Hybrid flow flaws:** cookie handoff browser→wreq — does wreq need the SAME IP as the browser? Does PX/CF validate cookie-IP binding? Does __cf_bm need continuous refresh? What's the realistic session length before cookies invalidate?
11. **Pagination/data completeness:** any sarı site pagination caps (e.g., max pagingOffset, max 100 pages?), hidden listing duplicates across price brackets, listings that only appear in category sub-URLs (/kiralik-daire vs /kiralik), or lazy-loaded listings beyond page N?
12. **Data integrity:** ilanId stability across refreshes (do IDs change?), price/date normalization edge cases, dedup strategy across daily runs, and whether the CSV→Mongo migration loses anything (historical daily snapshots vs inventory time-series).
13. **Operational:** Windows-specific issues (CloakBrowser/wreq on Windows, rayobrowse Docker on Windows), scheduler reliability, crash-resume idempotency design, multi-city parallelism vs serial (rate-limit implications).

### D. Legal/ToS/ethics
14. sarı site's terms regarding automated access (public statements, robots.txt, ToS clauses reported by others); Turkish legal context (KVKK, electronic commerce law) for price/listing collection; whether collecting only public listing metadata (no personal data, no phone numbers) materially reduces risk. Any precedent of Turkish sites suing scrapers?

### E. Skills/agent-side completeness
15. Given our planned agent-skill install set (playwright, webapp-testing, modern-python, mongodb-schema-design/connection, pytest, playwright-skill, scrapling-official) — are there skills we're missing that would materially help (e.g., resume/crash-recovery, observability, docker)? Any better skill sources than what we found?

## Output format (be rigorous)

Produce a single report with these sections:

1. **Executive verdict** — is the architecture sound? 3-5 bullet headline findings.
2. **Site state (today)** — confirmed stack, changes since 2026-08-15, new intel with sources.
3. **Tool validation table** — for each tool: claim → verified/refuted/partially (with source) → risk level.
4. **Gap findings (prioritized)** — P0 (blocks the plan) / P1 (should fix) / P2 (nice to have). Each: finding, evidence, recommended action.
5. **Threat model delta** — anything to add/change vs our B1–B7 table.
6. **Decision-gate amendments** — changes to G0–G4 (new gates, better metrics).
7. **Open questions** — what couldn't be verified and how to test it cheaply.
8. **Sources** — every claim cites a URL/date.

Rules: cite everything; distinguish verified facts from marketing claims; flag anything older than 6 months as possibly stale; be specific (versions, costs, dates); when in doubt, say "unverified — test at gate Gx".

---

*Return the report as a single markdown document. Save a copy to `docs/` when done.*
