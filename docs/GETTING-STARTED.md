<!-- generated-by: gsd-doc-writer -->
# Getting Started

## Prerequisites

- Python. Local project metadata declares `requires-python = ">=3.14"` in `pyproject.toml`, while GitHub Actions workflows use Python 3.10 and 3.12. Use the Python version required by the script or workflow you are running.
- `pip` or another Python package installer.
- Optional: Streamlit and Plotly if you want to run the dashboard.
- Optional: scraper-specific browser/anti-bot dependencies from `requirements.txt` for browser-heavy scripts.

## Installation Steps

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd inflationstudymirror
   ```

2. Install the tracked scraper dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Install dashboard dependencies if you want to run `streamlit_app.py`:

   ```bash
   python -m pip install pandas streamlit plotly
   ```

4. Configure secrets only for scrapers that need them. For the Vakko scraper, export `VAKKO_COOKIE` and `VAKKO_USER_AGENT` or place them in a local ignored `.env` file.

## First Run

The shortest non-destructive dashboard path is:

```bash
streamlit run streamlit_app.py
```

The dashboard uses the tracked CSV files under `Datas/`, builds a lazy inventory, and applies retailer/date/file-count controls before loading row data.

To inspect an inflation calculator CLI without writing output, start with help:

```bash
python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h
```

## Common Setup Issues

### `pyproject.toml` and runtime versions disagree

`pyproject.toml` declares `requires-python = ">=3.14"`, but checked GitHub Actions workflows use Python 3.10 or 3.12. If a tool refuses to create an environment because of the `pyproject.toml` constraint, use the workflow/script-specific Python version or adjust metadata intentionally.

### Dashboard dependencies are not all in `requirements.txt`

`streamlit_app.py` imports `pandas`, `plotly.express`, and `streamlit`. Install these explicitly before launching the dashboard if they are missing.

### Vakko scraper needs local secrets

`Codes/ClothingStores/Vakko/vakko_master_scraper.py` reads `VAKKO_COOKIE` and `VAKKO_USER_AGENT`. Keep these values in environment variables or an ignored `.env` file; do not write them into docs or source files.

### Large CSV history can be slow

The dashboard and extracted CSV adapter include retailer, date, and max-file controls. Keep bounded defaults when exploring the data locally instead of loading every tracked CSV.

## Next Steps

- Read `docs/ARCHITECTURE.md` for the repository structure and data flow.
- Read `docs/DEVELOPMENT.md` before changing scrapers, calculators, or dashboard code.
- Read `docs/TESTING.md` for the current verification posture and suggested checks.
- Read `docs/CONFIGURATION.md` for environment variables and source-specific config files.
