# Development

## Workflows

### Scraper change

1. Read the mandatory scraping wiki and source documentation.
2. Inspect the existing output schema and current CLI.
3. Make the smallest source-specific change.
4. Run a bounded live scraper execution.
5. Inspect CSV/state/log output and downstream compatibility.
6. Update source README, `docs/TECH-STACK-SEARCH.md` or `docs/APPROACH.md` when behavior changes.

Do not add mock/synthetic scraper tests or one-off scraper verification scripts. The scraper is verified by real bounded use.

### Inflation change

1. Identify the source/category mapping and output schema involved.
2. Use a small real date range first.
3. Compare generated detail/summary values and row counts.
4. Update calculator README/methodology when formulas or mappings change.

### Publication change

If the web-consumed artifact layout changes, update `docs/DATA_PUBLICATION.md` and coordinate the corresponding web repository contract.

## Common commands

```bash
# Syntax check without executing a scraper
python -m py_compile path/to/file.py

# Data consolidation
python scripts/consolidate_inflation_details.py --help

# Source-specific checks retained as operational data tools
python scripts/check_vakko_coverage.py --help
```

## Repository boundaries

- `InflationItems/Codes/` owns source acquisition.
- `InflationItems/Datas/` owns raw source artifacts.
- `Inflations/Codes/` owns inflation computation.
- `Inflations/Datas/` owns generated calculation artifacts.
- No web/API/frontend code belongs in this repository.

## Code style

- Prefer explicit source-specific helpers and CLI entrypoints.
- Use `pathlib.Path` for new code.
- Keep network retry/rate-limit policies visible and source-specific.
- Preserve source CSV compatibility unless intentionally migrating it.
- Log operational failures clearly; never log secrets/cookies.
- Prefer deterministic schema assertions over LLM extraction for known sources.
