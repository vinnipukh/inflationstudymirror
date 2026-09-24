# Configuration

## Environment variables

| Variable | Used by | Purpose |
|---|---|---|
| `VAKKO_COOKIE` | Vakko scraper | Optional authenticated cookie fallback |
| `VAKKO_USER_AGENT` | Vakko scraper | User-Agent paired with supplied cookie |
| `VAKKO_HEADED` | Vakko scraper | `1` runs the cookie-factory browser headed |
| `CHROME_DEBUGGER_ADDRESS` | Emlakjet | Optional existing Chrome debugger endpoint |

Keep `.env` and secret values out of Git. Prefer GitHub Actions secrets for scheduled jobs.

## Source configuration

- Scraper constants and browser settings live beside each source under `InflationItems/Codes/`.
- Rental city/room/pacing/profile settings live in `InflationItems/Codes/HousesRent/KayseriSivasTokat/config.py`.
- TÜİK weights and category mappings live in calculator-specific `*_tuik_config.py` / `tuik_config.py` files.
- Source data roots and output directories should remain repository-relative or CLI-configurable.

## Scheduled workflows

`.github/workflows/*.yml` define:

- cron schedule;
- workflow-specific Python version;
- minimal dependency installation;
- scraper command and bounded flags;
- exact data/log paths committed by the bot.

See `SCRAPER_TIMETABLE.md` for the summary.

## Generated publication data

- `InflationItems/prices_json/` is generated and gitignored by default.
- Raw CSV under `InflationItems/Datas/` and generated reports under `Inflations/Datas/` follow their existing Git policy.
- SQLite is built and owned by the separate web repository; do not configure or commit it here.
