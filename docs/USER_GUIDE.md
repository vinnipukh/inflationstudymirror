<!-- generated-by: gsd-doc-writer -->
# User Guide

## Welcome

The Inflation Study Dashboard lets you explore price data scraped from Turkish retailers and services. You can view price histories, compare prices across retailers, see the biggest price movements, and understand what data is available.

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

### 2. Start the API server

Open a terminal and run:

```bash
uv run waitress-serve --port=8000 inflation_dashboard.api.falcon_app:create_app
```

You should see output like:

```text
INFO:waitress:Serving on http://localhost:8000
```

### 3. Start the dashboard

Open a **second terminal** and run:

```bash
uv run streamlit run streamlit_app.py
```

Your browser should open the dashboard at `http://localhost:5000` (or the next available port).

## Dashboard Layout

The dashboard has a **sidebar** on the left and **four tabs** in the main area.

### Sidebar Controls

Control | What it does
--- | ---
**Falcon API base URL** | The address of the API server (keep as `http://localhost:8000` unless you changed the port)
**Retailers to load** | Select which stores to view data from
**Start date / End date** | Narrow the date range
**Max files per retailer** | How many recent CSV files to load per store (25 files by default, slider range 10–160)
**Load all files in date range** | Check this to bypass the limit (may be slower)
**Dashboard start prediction** | Enable ML-based price trend estimation (requires ML model)

### Tab 1: Product Explorer

Search for a product by name and see:
- Its **price chart** over time
- The **cheapest price** ever observed and when
- **Latest price** and change since first observation

**Tips:**
- Type partial names — the search handles misspellings
- Use the retailer filter in the sidebar first if you know which store

### Tab 2: Retailer Averages

Compare average or median prices across retailers over time.

- Choose **Average** or **Median** aggregation
- Select one or more retailers
- View the trend chart

### Tab 3: Price Movers

See products with the biggest price changes.

- **Biggest drops**: Products whose price has fallen the most
- **Biggest gains**: Products whose price has increased the most
- Adjust the **Retailer scope** and **Rows to show** controls
- Each mover shows: retailer, product name, price data, and percentage change

### Tab 4: Coverage Overview

Understand what data is powering the dashboard:

- **Summary**: Total products, observations, date range
- **Coverage over time**: How many products were tracked each day
- **Category coverage**: Products grouped by category
- **Skipped files**: Any CSV files that couldn't be loaded (with reasons)

## Tips

### Search with autocorrect
When searching for products or selecting retailers, you can type partial or misspelled names. The dashboard will suggest the closest match automatically.

### Bounded loading
The dashboard limits how many files it loads per retailer (25 by default). This keeps things fast. If you need to see all historical data, check **Load all files in date range** in the sidebar.

### Performance
- First load after changing filters takes ~280ms as the API reads CSV data from disk
- Subsequent tab renders with the same filters return in **~5ms** — the API caches loaded history for 45 seconds (TTL-based dedup across endpoints)
- Simply clicking between tabs is instant — the cache is warm from the initial page load
- Large date ranges with "load all files" may take a moment, and bypass the bounded-load cache

### Troubleshooting

**Dashboard shows no data**
- Make sure the API server is running (`uv run waitress-serve --port=8000 ...`)
- Check the API base URL in the sidebar — it should be `http://localhost:8000`

**Dashboard shows an error**
- Check that `uv sync` completed successfully
- Verify the API is running in the other terminal
- Check the terminal running the API for error messages

**"Falcon is missing" error**
- Run `uv sync` from the repository root
- Then run verifiers with `uv run python scripts/...`

**Slow loading**
- Reduce the date range in the sidebar
- Lower the max files per retailer value (slider range 10–160, step 5)
- Avoid checking "Load all files" unless necessary
- The API caches loaded data for 45 seconds; subsequent tab switches with the same filters are nearly instant
