# Phase 3: Streamlit API Frontend - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-17
**Phase:** 3-Streamlit API Frontend
**Areas discussed:** API base URL and client error behavior, Sidebar/filter flow over HTTP, Tab payload mapping, Loading/caching/empty states

---

## API Base URL and Client Error Behavior

| Question | Selected | Alternatives considered |
|----------|----------|-------------------------|
| How should Streamlit get the Falcon API base URL? | Sidebar text input with default `http://localhost:8000` | Environment variable only; `st.secrets`/config file first with sidebar override; Claude decides |
| If the API is unreachable or invalid, what should the dashboard do? | Show a clear Streamlit error and stop data rendering | Fall back to direct CSV/domain calls; render cached previous data if available; Claude decides |
| What timeout behavior should the client use? | Small requests around 10s, data requests around 60s | One global 30s timeout; no explicit timeout; Claude decides |
| How strictly should the client handle the API envelope? | Require `{data, meta, errors}`; display errors and keep meta | Accept both envelopes and bare payloads; ignore meta/errors; Claude decides |

**Notes:** User chose the recommended local-first and strict-boundary options. Direct CSV fallback was rejected for this phase because Streamlit must rely on Falcon API data.

---

## Sidebar/filter flow over HTTP

| Question | Selected | Alternatives considered |
|----------|----------|-------------------------|
| How should Streamlit populate retailer/date controls? | Call `/api/inventory` first and render controls from its payload | Derive options locally from Streamlit inventory code; hardcode defaults; Claude decides |
| What defaults should the sidebar use? | Preserve current defaults: `DEFAULT_RETAILERS`, last 60 days, `DEFAULT_MAX_FILES` | Let API defaults decide everything; default to all retailers/date range with capped files; Claude decides |
| How should filters flow into tab data calls? | Pass selected filters to every endpoint as repeated `retailer`, `start_date`, `end_date`, `max_files`, and `all_history` | Load `/api/history` once and compute tabs in Streamlit; use a dashboard aggregate endpoint; Claude decides |
| How should all-history work? | Keep checkbox, send `all_history=true`/`max_files=0`, show API warning/meta | Remove all-history UI; keep max-files slider only; Claude decides |

**Notes:** User chose to preserve the current sidebar UX while moving all data discovery and loading behind HTTP.

---

## Tab payload mapping

| Question | Selected | Alternatives considered |
|----------|----------|-------------------------|
| Product explorer source | Product tab calls `/api/history` with `product_name` and `product_retailer` after selection | Use full history records already loaded in client; defer until a product-search endpoint exists; Claude decides |
| Retailer averages source | Use `/api/retailer-averages` records directly; Streamlit only renders Plotly/table | Fetch `/api/history` and calculate average/median in Streamlit; show only chart; Claude decides |
| Price movers behavior | Use `/api/movers` `biggest_drops` and `biggest_gains`; keep existing two-column tables | Compute movers from loaded history in Streamlit; only show drops first; Claude decides |
| Coverage overview sections | Use `/api/coverage` `summary`, `coverage_over_time`, `category_coverage`, and `skipped_files`; keep metrics/charts/expander | Show only summary metrics and skipped files; fetch separate coverage section endpoints; Claude decides |

**Notes:** User chose endpoint-specific payloads and backend-owned aggregation/calculation. Streamlit remains a renderer, not the calculation owner.

---

## Loading/caching/empty states

| Question | Selected | Alternatives considered |
|----------|----------|-------------------------|
| How should Streamlit cache API data? | Cache API client calls with `st.cache_data`, keyed by base URL plus filters, with separate inventory/data TTLs | No HTTP caching; cache only inventory; Claude decides |
| How much loading feedback should be shown? | Use Streamlit spinners around each API fetch and preserve sidebar estimated/loaded dataset summary from meta | One global loading spinner; no explicit spinners; Claude decides |
| How should empty data vs errors display? | HTTP 200 empty data shows tab-specific info; HTTP 400/API errors show error and stop affected section | Any empty data stops whole app; all API errors are warnings; Claude decides |
| How visible should warnings/skipped diagnostics be? | Show meta warnings and skipped-file diagnostics in sidebar/coverage expander; do not crash for non-fatal skipped files | Show skipped diagnostics only on coverage tab; hide unless every selected file fails; Claude decides |

**Notes:** User chose visible diagnostics and partial-section error handling while preserving trust signals from API metadata.

---

## Claude's Discretion

- Exact API client helper names and module split.
- Exact cache TTL values.
- Exact request wrapper implementation details.
- Exact Streamlit placement of warnings/diagnostics, as long as sidebar/coverage visibility is preserved.

## Deferred Ideas

None — discussion stayed within phase scope.
