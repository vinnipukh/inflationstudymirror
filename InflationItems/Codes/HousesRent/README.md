# Turkey residential rental scraper

This directory contains the Emlakjet browser-backed scraper for regular,
non-seasonal residential rental listings:

- `Emlakjet/scraper.py` — starts at `https://www.emlakjet.com/kiralik-konut`.
  Emlakjet caps pagination at 50 pages per geographic scope. The scraper
  discovers province routes and recursively uses the district/neighborhood
  routes advertised by Emlakjet whenever a scope is larger than 50 × 30
  cards. It uses `?sayfa=`; the site's robots policy disallows the tempting
  `filtreler=ilan-sayisi=50` query.

The adapter:

- uses a visible, ordinary Chrome session by default (CI adds container-safe
  flags and `pageLoadStrategy=eager`; each launched driver gets a fresh
  temporary profile);
- can attach to an already-running Chrome **remote-debugging/CDP** endpoint
  with `--debugger-address 127.0.0.1:9222` (or `CHROME_DEBUGGER_ADDRESS`);
  this is a conventional Selenium CDP address, not the Browser Use harness'
  own relay service port;
- visits the homepage before the listing route;
- runs every page load under a watchdog (`BrowserSession` in `browser.py`):
  if Chrome stalls or the session dies, the browser is restarted and the page
  retried up to `--max-page-retries` times (default 3) instead of killing the
  whole crawl;
- stops rather than solving or bypassing a CAPTCHA/anti-bot challenge
  (challenge pages are never silently retried);
- never opens listing detail pages; and
- excludes advertiser names, phone numbers, photos, descriptions, and other
  contact data.

The existing `KayseriSivasTokat/` scraper remains a separate, site-specific
adapter documented by `docs/APPROACH.md`.

## Output

By default, Emlakjet writes a dated CSV under `Datas/HousesRent/Emlakjet/`
and its resume checkpoint under the **tracked** directory
`Datas/HousesRent/Emlakjet/state/checkpoint.json` (under `Datas/` so the
workflow can commit it and `--resume` works across GitHub Actions runs — any
directory literally named `checkpoints/` would be gitignored). Checkpoints
are stamped with their date: a stale (previous-day) checkpoint is ignored,
and the file is deleted once the day's crawl completes. The output columns
are public listing data only. The first three columns intentionally match the
legacy rental scraper:

The layout is:

```text
District,Rooms,Price
```

For example, the migrated Emlakjet data currently contains rows such as:

```text
District,Rooms,Price
Merkez,3+1,29.000 TL
Merkez,3+1,15.000 TL
```

If a neighborhood is actually present in the source card, the formatter can
represent it as `District / Neighborhood`; the current Emlakjet card markup
normally exposes only province and district, so it must not invent
neighborhood names.

Additional traceability columns follow those first three:

```text
ilanId,ListingURL,Province,Neighborhood,PropertyType,AreaM2,
Currency,ListingDate,CollectedAt
```

`ilanId` is the site's public listing identifier and is used for deduplication
and crash recovery. `ListingURL` is retained for traceability, but the scraper
does not navigate to it.

## Commands

Run from the repository root:

```bash
# Small live smoke run
uv run python -m Codes.HousesRent.Emlakjet.scraper \
  --start-url https://www.emlakjet.com/kiralik-konut/tokat \
  --max-pages-per-scope 1

# Full Turkey residential inventory
uv run python -m Codes.HousesRent.Emlakjet.scraper

# Continue a paused run after a browser challenge or interruption
uv run python -m Codes.HousesRent.Emlakjet.scraper --resume
```

For a running Chrome relay, add `--debugger-address HOST:PORT`. If a
challenge is detected, the process exits with a checkpoint; solve it manually
in the visible browser only if you are authorised to do so, then rerun with
`--resume`.

Useful flags: `--max-page-retries N` (browser restarts per page, default 3),
`--page-timeout SECONDS` (grid wait, default 45), `--resume` (continue
today's checkpoint — the normal CI mode). The default delay is two seconds
between listing pages. Keep the crawl serial, respect the site's
robots/terms, and use `--max-pages-per-scope` or a narrower geographic start
URL for controlled verification.

## GitHub Actions

`.github/workflows/emlakjet_scraper.yml` runs the full scraper every day at
**16:00 UTC (19:00 Türkiye time, UTC+3)**. It can also be started manually
from the GitHub Actions interface. The workflow runs Chrome under Xvfb with
`--resume`, writes and commits the whole `Datas/HousesRent/Emlakjet/` dir
(CSV + checkpoint state) with the repository's GitHub Actions bot account. A
CAPTCHA or anti-bot challenge causes the run to stop rather than attempting
an automated bypass.

## Tests

Per the project principle in `AGENTS.md`, scrapers have **no unit/smoke
tests** — they are verified by running them (bounded `--start-url` runs,
scheduled runs, and inspecting the CSV/checkpoint/logs they produce). See
`docs/TECH-STACK-SEARCH.md` §3.1 for the CI-hardening and verification runs
(2026-09-02).
