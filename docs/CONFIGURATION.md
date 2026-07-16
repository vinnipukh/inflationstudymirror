<!-- generated-by: gsd-doc-writer -->
# Configuration

## Environment Variables

| Variable | Required | Default | Description |
|---|---:|---|---|
| `VAKKO_COOKIE` | Required for `Codes/ClothingStores/Vakko/vakko_master_scraper.py` | None | Cookie value used by the Vakko scraper. The GitHub workflow passes it from `secrets.VAKKO_COOKIE`. |
| `VAKKO_USER_AGENT` | Required for `Codes/ClothingStores/Vakko/vakko_master_scraper.py` | None | User agent used by the Vakko scraper. The GitHub workflow passes it from `secrets.VAKKO_USER_AGENT`. |

No `.env.example` or `.env.sample` file is present. `.env` and `.env.*` files are ignored by `.gitignore`, so local secret values should stay outside git.

## Config File Format

### `pyproject.toml`

```toml
[project]
name = "inflationstudymirror"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = []
```

`pyproject.toml` exists, but it is skeletal and does not list the scraper, dashboard, or analysis dependencies used by the code.

### `requirements.txt`

`requirements.txt` is the practical dependency list for scraper-related installs. It includes packages such as `requests`, `urllib3`, `python-dotenv`, `beautifulsoup4`, `seleniumbase`, `camoufox`, `cloudscraper`, and `curl-cffi`.

Dashboard packages used by `streamlit_app.py` (`pandas`, `plotly`, and `streamlit`) are imported in code but are not all listed in `requirements.txt`.

### Source-specific config modules

| File | Purpose |
|---|---|
| `Codes/HousesRent/KayseriSivasTokat/config.py` | Browser/scraper settings for the Kayseri, Sivas, and Tokat rental scraper. |
| `Inflations/Codes/Technology/tuik_config.py` | TUIK-style configuration for technology inflation calculations. |
| `Inflations/Codes/Cosmetics/tuik_config.py` | TUIK-style configuration for cosmetics calculations. |
| `Inflations/Codes/HomeGoods/tuik_config.py` | TUIK-style configuration for home goods calculations. |
| `Inflations/Codes/Markets/Gurmar/gurmar_tuik_config.py` | Gurmar category mapping and weighting configuration. |
| `Inflations/Codes/ClothingStores/Vakko/vakko_tuik_config.py` | Vakko category mapping and weighting configuration. |
| `Inflations/Codes/ConstructionMarkets/yapimaks/Category/yapimaks_config.py` | Yapimaks category configuration. |

## Required vs Optional Settings

- `VAKKO_COOKIE` and `VAKKO_USER_AGENT` are required for successful Vakko scraper runs because `vakko_master_scraper.py` reads them with `os.getenv()` after `load_dotenv()`.
- Other scraper and calculator scripts mostly use constants, CLI arguments, or file paths rather than environment variables.
- The current dashboard does not read environment variables; it uses repository-local paths such as `Datas/` through the CSV adapter.

## Defaults

| Setting | Default | Location |
|---|---|---|
| Raw dashboard data root | `Datas/` under the repository root | `inflation_dashboard/adapters/csv_price_repository.py` |
| Supported dashboard retailers | `SUPPORTED_RETAILERS` set | `inflation_dashboard/adapters/csv_price_repository.py` |
| Default dashboard retailers | `("Markets / Gurmar", "ClothingStores / Vakko", "HomeGoods")` | `inflation_dashboard/adapters/csv_price_repository.py` |
| Default dashboard max files per retailer | `45` | `inflation_dashboard/adapters/csv_price_repository.py` |

## Per-Environment Overrides

No checked-in per-environment files such as `.env.development`, `.env.production`, or `.env.test` are present. For local runs, place secret values in an ignored `.env` file or export them in the shell before running the relevant scraper.

Example local Vakko environment:

```bash
export VAKKO_COOKIE="..."
export VAKKO_USER_AGENT="..."
python Codes/ClothingStores/Vakko/vakko_master_scraper.py
```

Do not commit real cookie, token, or user-agent secret values into documentation, logs, or source files.
