# Research Summary: Falcon API + Streamlit Hexagonal Dashboard

Date: 2026-07-16

## Decision Context

The project needs a fully separated dashboard architecture. The frontend must be Streamlit, the API must use Falcon Python Web Framework, and Streamlit must read from the Falcon API.

## Recommended Architecture

Use a hexagonal structure with clear framework boundaries:

```text
src or app modules
├── domain/              # entities/value objects and pure calculations
├── application/         # use cases: inventory, history, averages, movers, coverage
├── adapters/csv/        # reads existing Datas/**/*.csv
├── adapters/http_falcon/ # Falcon resources and JSON serialization
└── frontend_streamlit/  # Streamlit API client and UI rendering
```

For a smaller brownfield step, the same boundary can be introduced with root-level modules first, then moved into packages later if desired.

## Falcon Notes

- Falcon is a WSGI/ASGI-oriented Python web framework based around resources and request/response objects.
- Keep Falcon resource classes thin: parse query params, call application use cases, serialize results.
- Do not put CSV parsing or aggregation logic in resource methods.
- Use explicit JSON payload shapes for Streamlit consumption.

## Streamlit Notes

- Keep Streamlit as a client of API endpoints only.
- Cache API calls with `st.cache_data`, not raw CSV scans in the frontend.
- Keep API base URL configurable in sidebar or environment variable.
- Preserve typo-tolerant search/autocorrection helpers for user selection.

## Performance Notes

- API endpoints should keep retailer/date/max-file filters and apply them before expensive CSV reads.
- Inventory discovery can be cheaper than full history loading; use it to populate filters first.
- CSV remains acceptable for v1 if loading is bounded and cached.
- A future cache/database adapter can replace CSV behind the same application ports.

## Risks

- Payloads can become large if product history endpoints return all products. Prefer filtered endpoints and limited defaults.
- Streamlit and Falcon run as separate processes, so documentation must make startup order clear.
- Dependency files currently do not represent the full dashboard/API stack.

## Implications for Phase 1

Start by extracting domain/application functions out of `streamlit_app.py` before adding Falcon. This keeps Phase 2 small and prevents duplicating loader/aggregation logic inside API handlers.
