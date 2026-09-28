# AGENTS.md

Instructions for agents modifying scraper code under `InflationItems/Codes/`.

## Mandatory knowledge base

Before modifying, refactoring or modernizing any scraper, parser, browser driver or anti-bot path, read:

- `docs/scraping-wiki/README.md`
- the relevant concept/entity pages
- `docs/APPROACH.md` for rental acquisition
- `docs/TECH-STACK-SEARCH.md` for source/tool history
- the source-specific README/config when present

The wiki snapshot contains tested findings about bot detection, fingerprinting, CDP detection, homepage-first navigation, cookie/session reuse, hybrid scraping, driver lifecycle and mouse movement. These findings govern correctness.

The snapshot is dated; refresh it before relying on current anti-bot behavior.

## Repository role

This subtree owns website/API ingestion only. It writes source data/state under `InflationItems/Datas/` and may update generated partitions under `InflationItems/prices_json/`.

The Svelte frontend, Falcon API and SQLite serving database are not part of this repository.

## Data rules

- Preserve source CSV compatibility unless a versioned migration is explicit.
- Keep source-specific parsing and schema checks deterministic.
- Never commit cookies, secrets, browser profiles, challenge tokens or transient checkpoints.
- Prefer preserving the last valid snapshot over writing empty rows after a failed refresh.
- Use bounded live runs before scheduled/full runs.

## TechnologicalProducts (cron server)

`TechnologicalProducts/` (Beymen, DR, Huawei, Koctas, PozitifTeknoloji, Samsung,
VatanComputer) was imported from `TUGC3/InflationResearchStudy@9cb747a` and adapted
for a 2 vCPU / 1.9 GB RAM Ubuntu cron box (not GitHub Actions). Deployment, schedule
and the list of changes vs. upstream: `deploy/scraper-server/README.md`. Constraints:
one scraper at a time, parallelism 1, browser only where Akamai forces it (Koctas
always, Beymen on 403), headless Chrome needs a non-"HeadlessChrome" UA for Akamai,
Chrome major version is auto-detected (never pin `version_main` in code).

## Verification policy

There are no unit tests, mock tests, synthetic HTML fixtures or one-off smoke tests for scraper code. Verify by running the scraper against a bounded live scope and inspecting its CSV, state/checkpoint and log outputs.

Do not add verification scripts under this subtree merely to avoid running the scraper.

## Documentation

Update the source README and, when behavior/tooling changes, `docs/TECH-STACK-SEARCH.md` or `docs/APPROACH.md` in the same change. Update `docs/DATA_PUBLICATION.md` if a web-consumed artifact changes.
