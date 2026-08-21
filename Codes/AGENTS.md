# AGENTS.md — Codes/

Scope: everything under `Codes/` (scrapers and related scripts).

## Mandatory

Before modifying, refactoring, or modernizing **any** file in this
directory (or its subdirectories, e.g. `Codes/HousesRent/`):

1. Read `docs/scraping-wiki/README.md` (snapshot index + relevance table).
2. Read the entity/concept pages relevant to the change (at minimum the
   pages listed in the README table for the touched subsystem:
   driver → `entities/rayobrowse.md`, `entities/camoufox.md`; browser-backed
   rental adapters also → `Codes/HousesRent/README.md` (Emlakjet contract) and
   `undetected-chromedriver`/persistent-profile findings; anti-bot →
   `concepts/mouse-movement-emulation.md`, `concepts/cookie-session-reuse.md`,
   `concepts/homepage-first-navigation.md`; data layer →
   `concepts/inventory-tracking.md`, `concepts/hybrid-scraping.md`).
3. Read `docs/TECH-STACK-SEARCH.md` — the modernization plan, skill registry,
   and resource evaluations for this codebase.

The wiki snapshot is the source of truth for scraping techniques. Do not
"improve" anti-bot or driver code from intuition; the findings in the wiki
are tested results.

## Rules

- Do not drop data that later stages need (e.g. listing IDs/links) — see
  the pain-points list in `docs/TECH-STACK-SEARCH.md`.
- Keep output formats consistent (price normalization drift is a known
  issue — see `docs/TECH-STACK-SEARCH.md`).
- Never bypass or weaken anti-bot protections in ways the wiki documents
  as detectable; follow the wiki's tested patterns instead.
- Record what you change and why in the relevant doc files so the next
  agent inherits the context.
