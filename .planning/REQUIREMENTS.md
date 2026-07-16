# Requirements: Inflation Study Dashboard Deployment

## Scope

Initialize a deployable dashboard architecture for scraped price data using a Falcon API backend and Streamlit frontend. Existing CSV files remain the source of truth for v1, but access must move behind backend/domain boundaries.

## User Stories

### US-01: Product price exploration

As a dashboard user, I want to select or search a product and see its price over time, so I can understand when it was cheapest to buy.

### US-02: Retailer average exploration

As a dashboard user, I want to select one or more retailers and see their average prices over time, so I can compare pricing trends.

### US-03: Price movers

As a dashboard user, I want to see products with the biggest drops and increases, so I can identify notable changes.

### US-04: Coverage overview

As a dashboard user, I want to see dataset coverage, retailer counts, date ranges, and skipped-file diagnostics, so I can trust what data is powering the charts.

### US-05: API-backed dashboard

As a maintainer, I want Streamlit to call a Falcon API instead of scanning CSVs directly, so the UI stays responsive and the backend owns data loading/caching.

### US-06: Hexagonal architecture

As a maintainer, I want data parsing, use cases, and adapters separated, so I can test domain logic and later replace CSV storage without rewriting the frontend.

## Functional Requirements

- REQ-01: Provide Falcon API endpoints for dashboard inventory, retailers, product history, retailer averages, price movers, and coverage.
- REQ-02: API endpoints must accept filters for selected retailers, start date, end date, and max files per retailer where relevant.
- REQ-03: Streamlit must read dashboard data through HTTP calls to Falcon endpoints.
- REQ-04: Streamlit must keep four tabs: product explorer, retailer averages, price movers, and coverage overview.
- REQ-05: Product explorer must display a price chart and cheapest observed date/price for the selected product.
- REQ-06: Retailer averages tab must chart average/median price trends for selected retailers.
- REQ-07: Price movers tab must show strongest drops and increases based on loaded filtered history.
- REQ-08: Coverage tab must show row counts, retailer coverage, date coverage, categories, and skipped-file diagnostics.
- REQ-09: Search/autocorrection must remain available for Streamlit selection controls.
- REQ-10: Domain/application logic must be usable without importing Streamlit or Falcon.
- REQ-11: CSV reading must remain bounded by filters/caps to avoid full eager scans.
- REQ-12: Deployment/run docs must show separate commands for Falcon API and Streamlit frontend.

## Non-Functional Requirements

- NFR-01: Keep implementation simple and local-first; avoid introducing database infrastructure in v1.
- NFR-02: Do not hardcode secrets, cookies, or credentials into new API/dashboard code.
- NFR-03: Preserve user preference that dependencies are installed by the user with `uv`.
- NFR-04: Use focused ad-hoc verification if no canonical test suite exists.
- NFR-05: Keep API response payloads JSON-serializable and stable enough for the frontend.
- NFR-06: Minimize frontend startup cost; Streamlit should render controls before expensive data calls where possible.

## Acceptance Criteria

- AC-01: A Falcon API module exists and can expose health/inventory/history/aggregation endpoints.
- AC-02: Streamlit has a configurable API base URL and does not directly scan `Datas/` for tab data.
- AC-03: Four tabs still render from API responses with equivalent user-facing behavior.
- AC-04: A focused verification script can exercise domain/API data functions without launching Streamlit visually.
- AC-05: Documentation states how to run the API and frontend separately with `uv`.
- AC-06: Planning and implementation cite live file paths/symbols and avoid stale assumptions.

## Definition of Done

- Falcon backend and Streamlit frontend are separated by HTTP API calls.
- Domain/application code is separated from framework adapters.
- Existing dashboard capabilities continue to work against the API.
- Lightweight verification passes and is labeled as ad-hoc if no suite exists.
- No secrets are introduced.
- User can run the result locally with documented commands.

---
*Last updated: 2026-07-16 after initialization*
