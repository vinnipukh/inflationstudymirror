<!-- generated-by: gsd-doc-writer (rewritten 2026-09 for the Svelte frontend) -->
# User Guide

## Welcome

The Inflation Study Dashboard lets you explore price data scraped from Turkish retailers and services. You can view price histories, compare prices across retailers, see the biggest price movements, and understand what data is available.

The **production dashboard is the Svelte frontend** (`frontend/`). The legacy Streamlit dashboard is described at the end of this guide.

## Quick Start

### 1. Install dependencies

```bash
uv sync
cd frontend && npm install && cd ..
```

### 2. Start the API server

Open a terminal and run:

```bash
uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app
```

You should see output like:

```text
INFO:waitress:Serving on http://localhost:8000
```

### 3. Start the dashboard

Open a **second terminal** and run:

```bash
cd frontend && npm run dev
```

Open your browser at `http://localhost:5173`. (For a production preview of the
built static site: `cd frontend && npm run build && npm run preview`.)

## Dashboard Layout

The dashboard has a **sidebar** on the left and **four tabs** in the main area. The design is intentionally minimal — numbers first, no decorative chrome.

### Sidebar Controls

Control | What it does
--- | ---
**Falcon API base URL** | The address of the API server (default `http://localhost:8000`; **Apply** reloads the inventory)
**Retailers to load** | Which stores to view. Opens with **Markets / Gurmar** selected by default; search and pick more (misspellings are tolerated)
**Start date / End date** | Narrow the date range (defaults to the last 60 days)
**Max CSV files per retailer** | How many recent files to load per store (default 45, slider range 10–160)
**Load all files in date range** | Check to bypass the limit (may be slow; sends `all_history=true`)
**Inventory summary** | File count and earliest/latest dates of the loaded data

### Tab 1: Product Explorer

Pick a **retailer** then a **product** (both searchable). You get:

- **Latest price**, **cheapest price**, **cheapest date**, and **change since first observation**
- **Monthly average price chart** (shown by default): average price per calendar month over the *full observed history* of that product — months on the X axis, price (₺) on the Y axis. Independent of the date-range filter.
- **Daily price history** (optional): enable the **“Show daily chart”** toggle to see the raw daily series within the selected date range.
- The raw history table (date, price, category — blanked `—` when the source has no category — and source file).

### Tab 2: Retailer Averages

Compare average or median prices across retailers over time.

- Choose **Average** or **Median** aggregation
- Select one or more retailers (searches with autocorrect)
- View the trend chart and table

### Tab 3: Price Movers

See products with the biggest price changes.

- **Biggest drops vs. peak**: products whose price fell the most
- **Biggest gains since first observation**: products whose price rose the most
- Adjust **Retailer scope** and **Rows to show** (5–30)
- Each mover shows retailer, product, price data, and percentage change

### Tab 4: Coverage Overview

Understand what data is powering the dashboard:

- **Summary**: retailers, products, observations, date range
- **Coverage over time**: how many products were tracked each day
- **Category coverage**: products grouped by category
- **Skipped files**: any files that couldn't be loaded (with reasons)

## Tips

### Search with autocorrect
When searching for products or selecting retailers, type partial or misspelled names. Matching is Unicode-normalized (Turkish characters) and ranks prefixes first, then contains, then fuzzy matches — with a “Closest match” hint.

### Monthly vs. daily charts
- The **monthly average** chart always covers the product's full history, so it is the best view for long-term trends and is **not** affected by the sidebar date range.
- The **daily chart** respects the sidebar date range; turn it on with the “Show daily chart” toggle.

### Gurmar by default
The dashboard opens with `Markets / Gurmar` pre-selected. Add more retailers from the sidebar when you need them.

### Bounded loading
The dashboard limits files per retailer (45 by default). To see all historical data, check **Load all files in date range** — the API then sends `max_files=0` and `all_history=true`.

### Performance
- The API caches loaded history in memory (TTL-based): the first request per filter combination hits SQLite/disk; subsequent requests with the same filters return in milliseconds.
- The very first visit after a fresh API start can take a while for large filter sets (the option list for a big retailer is a large JSON payload). Reloading afterwards is instant.
- Reduce the date range or lower “Max CSV files per retailer” for faster filter changes.

### Theme
Use the header toggle to switch light/dark (Auto follows your OS). Reduced-motion and keyboard navigation are supported throughout.

## Troubleshooting

**Dashboard shows no data**
- Make sure the API server is running (`uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app`)
- Check the API base URL in the sidebar (`http://localhost:8000`) and click **Apply**

**Dashboard shows “API unreachable”**
- The API is not running, or a firewall/proxy blocks `localhost:8000` from the browser
- Check the terminal running the API for errors

**“Falcon is missing” / Python errors**
- Run `uv sync` from the repository root
- Run verifiers with `uv run python scripts/...`

**Slow first load**
- Reduce the date range in the sidebar
- Lower the max files per retailer value (slider range 10–160, step 5)
- Avoid “Load all files” unless necessary
- Note: the first, uncached request per filter combination is the slow one; the API caches it afterwards

**Frontend doesn't start**
- `npm install` must be run once inside `frontend/`
- Node.js >= 20 is required

## Legacy Streamlit Dashboard

The older Streamlit dashboard is still available for administrative review:

```bash
uv run streamlit run streamlit_app.py
```

It reads the same Falcon API (sidebar API URL default `http://localhost:8000`) and offers the same four tabs. Feature development now happens in the Svelte frontend; the Streamlit app is frozen as a legacy/prototype reference.
