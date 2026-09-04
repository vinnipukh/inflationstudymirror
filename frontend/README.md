# Inflation Study Dashboard — Svelte Frontend

Svelte 5 / SvelteKit client-side dashboard for the Inflation Study project. It
is the **production UI** (the Streamlit app in the repo root is legacy). A static
SPA that queries the Falcon REST API (`inflation_dashboard/api/`) over HTTP — no
server-side rendering, no view reruns.

- **Framework:** Svelte 5 (runes) + SvelteKit (`adapter-static`, `ssr = false`)
- **Charts:** Apache ECharts (Canvas renderer)
- **API contract:** `docs/FALCON_API_CONTRACT.md` (types + client pattern)
- **Design system:** Minimalism & Swiss Style (UI/UX Pro Max) — near-black ink
  `#171717` + gold accent `#A16207`, hairline grid, Fira Sans + Fira Code,
  light/dark themes; see `src/app.css`.

## Quick Start

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The dashboard calls the Falcon API at `http://localhost:8000` by default
(start it from the repo root: `uv run waitress-serve --port=8000 --call
inflation_dashboard.api.falcon_app:create_app`). The API has CORS open and the
Vite dev server proxies `/api` to `:8000`.

### Production build

```bash
npm run build        # static site → frontend/build/
npm run preview      # serve the build locally
```

### Pointing at a different API

- **Build time:** set `VITE_API_BASE_URL` (see `.env.example`). Empty string
  means "same origin" (works with the Vite dev proxy).
- **Runtime:** the API base URL is editable in the dashboard sidebar
  ("API settings") and persists for the session; click **Apply** to reload.
- The Vite dev server proxies `/api` to `http://localhost:8000`.

## Features

- **Gurmar auto-load** — opens with `Markets / Gurmar` selected only; add more
  retailers via the searchable multi-select (`src/lib/stores/filters.svelte.ts`
  → `DEFAULT_RETAILERS`).
- Sidebar filters: retailer multi-select (fuzzy autocorrect, diacritic-insensitive),
  date range, max CSV files per retailer (default 45), all-history mode. Changing
  them reloads every view reactively.
- **Product explorer** — pick retailer + product (both searchable):
  - latest/cheapest metrics;
  - **monthly average price chart** (default view): average price per month over
    the product's *full* observed history, months on X / ₺ on Y. Uses the fast
    SQLite-backed `/api/product` endpoint, with a `/api/history` fallback for
    CSV-only stacks;
  - **daily price history** chart behind the optional **“Show daily chart”**
    toggle (respects the date-range filter);
  - raw history table (category blanks `—` when the source has no category).
- **Retailer averages** — average/median price trends per retailer (multi-line chart).
- **Price movers** — biggest drops vs. peak and biggest gains since first observation.
- **Coverage overview** — dataset summary metrics, tracked-products area chart,
  top-category bar chart, and skipped-file diagnostics expander.
- Light/dark theme (auto follows the OS; manual toggle in the header), keyboard
  navigation for tabs/selects, `prefers-reduced-motion` support.

## Project Structure

```
src/
  app.css                     # design tokens (light/dark) + base styles
  lib/
    api/client.ts             # fetchApi + buildQueryParams (contract §6.1)
    types/api.ts              # TypeScript interfaces (contract §5 + product detail)
    stores/filters.svelte.ts  # global filter state (Svelte runes)
    themes.svelte.ts          # light/dark/auto theme state
    utils/                    # formatting, fuzzy search, chart options, AsyncResource
    components/               # Chart, SearchableSelect(+Multi), MetricCard, DataTable, …
    views/                    # one component per dashboard tab
  routes/+page.svelte         # dashboard shell: header, sidebar, tabs
  routes/+layout.ts           # ssr = false (pure client SPA)
```

## Checks & Build

```bash
npm run check    # svelte-check (types + a11y + unused CSS) — must be 0/0
npm run build    # production static build
```

Both `check` and `build` are clean. End-to-end verification is done by running
the app against the live API (see `docs/TESTING.md`).

## Notes

- `streamlit_app.py` and `inflation_dashboard/frontend/` remain in the repo as
  legacy/admin code and are intentionally untouched.
- If you change API calls, keep `src/lib/types/api.ts` and
  `docs/FALCON_API_CONTRACT.md` in sync.
- Cold-cache note: the first request per filter combination can be slow for
  large retailers (big JSON option lists); the API caches it afterwards.
