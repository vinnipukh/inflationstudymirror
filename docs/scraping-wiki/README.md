# Scraping Wiki — Local Snapshot

Local reference copy of selected pages from
[TheWebScrapingClub/scraping-wiki](https://github.com/TheWebScrapingClub/scraping-wiki)
(main branch), fetched **2026-08-15** for use during the
`InflationItems/Codes/HousesRent/` modernization.

The wiki is updated **daily** — refresh this snapshot periodically:

```bash
# re-fetch everything (same list)
# (commands omitted; see docs/TECH-STACK-SEARCH.md resource evaluation for context)
```

## Files

### Concepts (10)

| File | Relevance |
|---|---|
| `concepts/mouse-movement-emulation.md` | Detects our `human_jittery_move()` pattern; OxyMouse / ghost-cursor fixes |
| `concepts/cookie-session-reuse.md` | Our cookie pool = "cookie factory" pattern; profile binding + DisableCookieTransport caveats |
| `concepts/hybrid-scraping.md` | Browser-for-clearance + curl_cffi for bulk; 27x speedup; TLS consistency |
| `concepts/inventory-tracking.md` | MongoDB time-series use case — needs `ilanId` (currently dropped in `parse_page()`) |
| `concepts/webdriver-vs-cdp-vs-bidi.md` | Protocol detection surfaces; CDP `Runtime.enable` signal |
| `concepts/cdp-detection.md` | CDP detection details (Playwright vector) |
| `concepts/homepage-first-navigation.md` | Validates our `warmup_with_human_surf()`; baseline requirement |
| `concepts/llm-scraping.md` | LLM extraction, self-healing scrapers (fits fragile selectors) |
| `concepts/bot-detection.md` | Detection landscape overview |
| `concepts/browser-fingerprinting.md` | Fingerprint vectors; BrowserForge |

### Entities (6)

| File | Relevance |
|---|---|
| `entities/rayobrowse.md` | Our driver — validation (100% benchmark) + risks (closed-source beta) |
| `entities/camoufox.md` | Open-source alternative; best OSS Cloudflare performer |
| `entities/scrapling.md` | StealthyFetcher (Turnstile headless), adaptive selectors, 1735x parse |
| `entities/ghost-cursor.md` | Bezier mouse movement (+ OxyMouse alternatives) |
| `entities/curl-cffi.md` | TLS impersonation client for hybrid scraping |
| `entities/cloudflare.md` | Our main blocker (Turnstile, JSD, cf_clearance) |

### Index

`index.md` — full wiki catalog (117 entities / 29 concepts) for finding further pages.

## Cross-references

Full analysis, verdicts, and the derived skill list live in
[`docs/TECH-STACK-SEARCH.md`](../TECH-STACK-SEARCH.md).
