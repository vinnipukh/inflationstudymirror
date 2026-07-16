---
last_mapped: 2026-07-16
focus: conventions
---

# Conventions

## General style

- Scripts are mostly standalone Python files rather than importable packages.
- Source-specific scripts keep constants at module top, then helper functions, then a `main()` or CLI entrypoint.
- Turkish comments, log messages, and variable names are common in scraper and inflation scripts.
- Path handling is usually based on `os.path` and script-relative project-root derivation; newer code like `streamlit_app.py` uses `pathlib.Path`.

## CSV handling

- CSV encodings often use `utf-8-sig` to handle Excel/BOM compatibility.
- Separators vary by source and time: some scripts write comma-separated CSVs while others write semicolon-separated CSVs.
- Robust readers use `pd.read_csv(..., sep=None, engine="python", on_bad_lines="skip")` or try semicolon then comma fallback.
- Date is commonly extracted from filenames with regex rather than from CSV content.

## Price normalization

- Prices appear as raw floats, Turkish decimal comma strings, `TL` strings, and `₺` strings.
- Calculators normalize prices before comparisons; examples include `Inflations/Codes/Markets/Gurmar/gurmar_inflation.py` and `Inflations/Codes/ClothingStores/Vakko/vakko_inflation.py`.
- Dashboard normalization is centralized in `streamlit_app.py::coerce_price`.

## Error handling

- Scrapers generally log or print errors and continue with remaining pages/categories.
- Inflation calculators usually return early when required files or columns are missing.
- Houses rent scraper uses explicit control-flow exceptions like `SkipCitySignal`, `SkipBracketSignal`, `StopSignal`, and `RestartBrowserSignal` in `Codes/HousesRent/KayseriSivasTokat/scraper.py`.

## UI/dashboard conventions

- `streamlit_app.py` is function-oriented with helpers for loading, normalization, and tab rendering.
- Dashboard tabs are rendered by separate functions: `render_product_explorer`, `render_retailer_average`, `render_price_movers`, and `render_overview`.
- Search/autocorrect helpers are pure functions where possible, which allows lightweight ad-hoc verification without launching Streamlit.

## Git and generated assets

- Generated CSVs are tracked in the repository.
- Virtualenvs, caches, `.env`, keys, and IDE files are ignored by `.gitignore`.
- Avoid committing actual secrets or copied cookie/token values into docs.
