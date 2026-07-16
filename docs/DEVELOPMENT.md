<!-- generated-by: gsd-doc-writer -->
# Development

## Local Setup

1. Clone and enter the repository:

   ```bash
   git clone <repository-url>
   cd inflationstudymirror
   ```

2. Create and activate a Python environment using your preferred tool.

3. Install tracked dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Install dashboard dependencies when working on `streamlit_app.py` or `inflation_dashboard/`:

   ```bash
   python -m pip install pandas streamlit plotly
   ```

5. Keep secrets local. `.env` and `.env.*` are ignored, and the Vakko scraper reads `VAKKO_COOKIE` and `VAKKO_USER_AGENT` through `python-dotenv`.

## Build Commands

No canonical build, lint, or test scripts are defined in `pyproject.toml`, `requirements.txt`, or a Makefile.

Useful development commands discovered from the repository:

| Command | Description |
|---|---|
| `streamlit run streamlit_app.py` | Launch the current dashboard over tracked `Datas/` CSV files. |
| `python Codes/Markets/Gurmar/gurmar_scraper.py` | Run the Gurmar scraper and write raw CSV data. |
| `python Codes/ClothingStores/Vakko/vakko_master_scraper.py` | Run the Vakko scraper; requires `VAKKO_COOKIE` and `VAKKO_USER_AGENT`. |
| `python Codes/HousesRent/KayseriSivasTokat/main.py -h` | Inspect rental scraper CLI options. |
| `python Inflations/Codes/Markets/Gurmar/gurmar_inflation.py -h` | Inspect Gurmar inflation calculator options. |
| `python -m py_compile <path>` | Syntax-check a Python file. |

## Code Style

- Scripts are mostly standalone Python modules with constants near the top, helper functions in the middle, and a `main()` or `if __name__ == "__main__"` entrypoint.
- Newer reusable dashboard code uses a package split under `inflation_dashboard/domain`, `inflation_dashboard/adapters`, and `inflation_dashboard/application`.
- Use `pathlib.Path` for new shared code where practical; older scraper code often uses `os.path` and script-relative paths.
- CSV readers should be tolerant of source drift. Existing robust readers use patterns like `pd.read_csv(..., sep=None, engine="python", encoding="utf-8-sig", on_bad_lines="skip")`.
- Do not copy real cookies, tokens, or credential values into source, generated docs, or logs.

No formatter or linter configuration file was found (`ruff`, `black`, `flake8`, ESLint, Prettier, Biome, or EditorConfig configs were not detected).

## Branch Conventions

No branch naming convention is documented in the repository. The checked-out branch used for current work is `main`.

## PR Process

No pull request template or contributing guide is present. A practical process for this repository is:

- Keep scraper, calculator, dashboard, and documentation changes separated when possible.
- Run a focused syntax check or ad-hoc verification script for files you changed.
- Avoid broad `.gitignore` changes for `Datas/`, `Inflations/Datas/`, or `logs/` because workflows may intentionally commit generated outputs.
- Do not include secrets, cookies, or generated credential files in commits.
- Summarize whether checks are canonical suite results or ad-hoc verification.
