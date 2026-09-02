---
quick_id: 260816-fx3
status: complete
date: 2026-08-16
description: Modernize KayseriSivasTokat rental scraper — ilanId, 3+1 filter, live sitekey, quoted selectors
---

# SUMMARY — 260816-fx3

## What changed

| File | Change |
|---|---|
| `InflationItems/Codes/HousesRent/KayseriSivasTokat/scraper.py` | `parse_page`: rows via `tr[data-id]` (quoted, B6) with `.searchResultsItem` fallback; captures **ilanId** from `data-id`; applies `ROOMS_FILTER`. `save_incremental`: CSV header now `District,Rooms,Price,ilanId` (compliance scope). `_is_enterprise_turnstile` + `solve_enterprise_turnstile`: **sitekey read live** from `#cloudflareTurnStileSiteKey` (recon-verified), stale `#sitekeyEnterprise` kept as fallback |
| `InflationItems/Codes/HousesRent/KayseriSivasTokat/config.py` | New `ROOMS_FILTER = "3+1"` (default; `None` = all) with compliance comment |
| `InflationItems/Codes/HousesRent/KayseriSivasTokat/main.py` | New `--rooms` CLI flag overriding `config.ROOMS_FILTER` |

## Verification

- ✅ All three files compile (`py_compile`)
- ✅ parse_page fixture: `data-id` row → `ilanId` captured; `ROOMS_FILTER="3+1"` keeps only the 3+1 row; `None` keeps all; `22.000 TL` → `22000.0`
- ✅ save_incremental (real temp file): header `District,Rooms,Price,ilanId` + row written
- ✅ `--rooms` flag present in CLI help; default `ROOMS_FILTER=3+1`
- ✅ Quoted-selector sweep: no unquoted attribute selectors remain

## Compliance

- Fields: **ilanId + District + Rooms + Price ONLY** (docs/APPROACH.md B0 — law-faculty confirmed)
- No phone/name/photo fields; no detail-page crawling (unchanged)
- Browser-only modernization — rayobrowse/Playwright architecture untouched, no wreq, no new services

## Out of scope (follow-ups)

- Snapshot-aware MongoDB storage (B10) — future phase
- Unit test suite (pytest) for parse_page/normalize_price — future
- Recon refresh of live sitekey value on next run (sitekey read live now, so self-healing)

## Addendum (same task, 2026-08-16) — engine_selenium.py (friend-tactics)

CloakBrowser and vanilla Playwright both FAILED cold-session Turnstile tests. Adopted the
proven pattern from urazkagangunes' IstanbulAvrupa scraper (3 months daily, 24.5k rows/day):

- **`engine_selenium.py`** (new): undetected-chromedriver + persistent `SeleniumProfile/`
  (--user-data-dir) = cookie-saving trust strategy · manual solve-retry loop (pause → human
  solves in Chrome window → ENTER → verify listings) · adaptive delay tracker (2.5s base,
  ±50% jitter, 1.5–8s adaptive) · adaptive bracket splitting at the 1,000-listing query cap
  · result-text + pager fallback count extraction · reuses our parse_page/ilanId/ROOMS_FILTER/
  compliance schema (District, Rooms, Price, ilanId)
- **config.py**: + MAX_LISTINGS_PER_QUERY, MIN_BRACKET_WIDTH, ADAPTIVE_MIN/MAX_DELAY
- **requirements.txt**: + selenium, undetected-chromedriver, lxml
- Verified offline only (site cooldown — IP flagged after today's tests): compile + parse/
  extract/URL/split checks all pass. **Day-1 ritual required**: run once headed, solve the
  Turnstile manually, profile saved → warm sessions thereafter.
- Run: `python InflationItems/Codes/HousesRent/KayseriSivasTokat/engine_selenium.py --city kayseri --rooms 3+1`

## Addendum 2 (same task, 2026-08-16) — full alignment rewrite

Line-by-line review per user request ("rewrite anything not inline with friend's
tactics + our talks"). Result: the folder is now a single aligned path.

| File | Action |
|---|---|
| `scraper.py` (2,322 lines, Playwright+rayobrowse monolith) | **DELETED** — JS patching / jittery mouse / auto-Turnstile / console all superseded by friend's tactics (git history preserves) |
| `run_scraper.py` (rayobrowse daemon check) | **DELETED** |
| `main.py` (174 lines) | **REWRITTEN** — thin entry over engine_selenium (--city/--rooms/--resume/-v) |
| `config.py` | **REWRITTEN** — removed all RAYOBROWSE_*/viewport/login-retry legacy; friend-aligned: PAGE_LOAD_DELAY 2.5s, adaptive factors, MAX_RETRIES/backoff, PROFILE_DIR, MAX_LISTINGS_PER_QUERY, MAX_BRACKET_SPLIT_DEPTH; kept compliance ROOMS_FILTER + output paths |
| `engine_selenium.py` | **UPGRADED** — + checkpoint save/load/clear (atomic, per-day brackets cache + done markers), + fetch retry w/ exponential backoff, + tqdm progress, + typed signatures, ruff-clean |

Also: requirements.txt += tqdm; ruff (uvx) clean with `select` defaults + targeted noqa
(DTZ011 date, S110 best-effort excepts); all offline checks pass (parse/filter/
normalize/extract/CSV-header/checkpoint-atomic/adaptive-delay/bracket-URL).
Docs updated: DEVELOPMENT.md run command, CONFIGURATION.md engine note.
