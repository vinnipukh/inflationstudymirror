<!-- generated-by: gsd-doc-writer -->
# Testing

## Test Framework and Setup

No dedicated test framework configuration or `tests/` directory was found. There is no canonical `pytest`, lint, or build command in `pyproject.toml`, `requirements.txt`, or project scripts.

Current verification is ad-hoc and file-focused:

- Python syntax checks with `python -m py_compile <file>`.
- Temporary helper scripts under the OS temp directory for focused behavior checks.
- Manual scraper runs and inspection of generated CSV files.
- Manual Streamlit browser checks for visual dashboard behavior.

## Running Tests

Because there is no canonical suite, choose the smallest relevant check for the file you changed.

### Syntax-check a Python file

```bash
python -m py_compile streamlit_app.py
python -m py_compile inflation_dashboard/domain/prices.py
python -m py_compile inflation_dashboard/adapters/csv_price_repository.py
python -m py_compile inflation_dashboard/application/use_cases.py
```

### Run dashboard helper checks

Create a temporary script under the OS temp directory with a `hermes-verify-` filename prefix, import the helper functions you changed, exercise bounded real data or tiny in-memory frames, then delete the script. Report this as ad-hoc verification, not as a full suite result.

### Inspect calculator CLIs

```bash
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h
python Inflations/Codes/HousesRent/sahibinden_inflation.py -h
```

## Writing New Tests

No naming convention is established yet. If a test suite is added, prefer small fixture-driven tests for reusable code rather than full-history data scans.

Good initial targets:

- `inflation_dashboard/domain/prices.py::coerce_price()` for Turkish lira strings, decimal commas, and invalid values.
- `inflation_dashboard/domain/prices.py::parse_date_from_name()` for supported filename patterns.
- `inflation_dashboard/adapters/csv_price_repository.py::discover_csv_inventory()` with a temporary directory of small CSVs.
- `inflation_dashboard/adapters/csv_price_repository.py::load_price_history()` with max-file limits and skipped-file diagnostics.
- `inflation_dashboard/application/use_cases.py` aggregation functions using small in-memory pandas DataFrames.
- Search/autocorrection helpers in `streamlit_app.py`.

## Coverage Requirements

No coverage tool or threshold is configured. There is no `.coveragerc`, `coverage` config, or CI coverage gate in the repository.

| Type | Threshold |
|---|---|
| Lines | Not configured |
| Branches | Not configured |
| Functions | Not configured |
| Statements | Not configured |

## CI Integration

GitHub Actions workflows under `.github/workflows/` run operational scrapers on schedules or manual dispatch. They are not test workflows.

| Workflow | Trigger | What it runs |
|---|---|---|
| `vakko_scraper.yml` | Schedule and manual dispatch | Installs selected packages, runs `Codes/ClothingStores/Vakko/vakko_master_scraper.py`, commits new Vakko CSVs. |
| `gurmar.yml` | Schedule and manual dispatch | Installs selected packages, runs `Codes/Markets/Gurmar/gurmar_scraper.py`, commits new Gurmar CSVs. |
| Other scraper workflows | Schedule/manual patterns | Run source-specific scrapers and commit generated CSV outputs. |

These workflows validate that scraper automation can execute in GitHub Actions, but they do not replace unit tests or dashboard/API contract tests.
