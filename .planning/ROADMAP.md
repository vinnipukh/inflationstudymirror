# Roadmap: Inflation Study Dashboard Deployment

## Overview

Move the current single-file, direct-CSV Streamlit dashboard into a separated deployment architecture: shared domain/application logic first, Falcon API second, Streamlit frontend third, then deployment documentation and verification hardening. The roadmap is intentionally coarse, matching the user's preference for 3-5 larger phases.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work.
- Decimal phases (2.1, 2.2): Urgent insertions if needed.

- [ ] **Phase 1: Hexagonal Core Extraction** - Extract data parsing/loading/use cases from `streamlit_app.py` into framework-independent modules.
- [ ] **Phase 2: Falcon API Backend** - Add Falcon resources/endpoints that serve filtered dashboard data from the domain layer.
- [ ] **Phase 3: Streamlit API Frontend** - Refactor Streamlit tabs to call the Falcon API instead of reading CSVs directly.
- [ ] **Phase 4: Deployment & Verification Hardening** - Document two-process deployment and add focused checks for API/frontend contracts.

## Phase Details

### Phase 1: Hexagonal Core Extraction

**Goal**: Create a clean application/domain layer for price data without Streamlit or Falcon imports.

**Depends on**: Nothing (first phase)

**Requirements**: REQ-02, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-11

**Success Criteria** (what must be TRUE):
  1. Domain/application modules expose inventory, price history, retailer averages, movers, and coverage use cases.
  2. Existing CSV parsing behavior from `streamlit_app.py` is preserved behind a CSV adapter.
  3. Core functions can be imported and checked without launching Streamlit.
  4. Existing performance caps remain available as function parameters.

**Plans**: 2 plans

Plans:
- [ ] 01-01: Extract price parsing, CSV inventory, and history loading into shared modules.
- [ ] 01-02: Extract aggregation/use-case functions and add focused ad-hoc verification.

### Phase 2: Falcon API Backend

**Goal**: Provide a Falcon API that exposes all dashboard data needed by the frontend.

**Depends on**: Phase 1

**Requirements**: REQ-01, REQ-02, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-11

**Success Criteria** (what must be TRUE):
  1. Falcon app exposes health, inventory/retailers, product history, retailer averages, movers, and coverage endpoints.
  2. Endpoints accept retailer/date/file-cap filters where relevant.
  3. API responses are JSON-serializable and stable for Streamlit consumption.
  4. API code does not import Streamlit.

**Plans**: 2 plans

Plans:
- [ ] 02-01: Add Falcon app/resources and response serialization.
- [ ] 02-02: Add API smoke verification and error/empty-state handling.

### Phase 3: Streamlit API Frontend

**Goal**: Refactor the dashboard so all tab data comes from Falcon HTTP endpoints.

**Depends on**: Phase 2

**Requirements**: REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-11

**Success Criteria** (what must be TRUE):
  1. Streamlit has a configurable Falcon API base URL.
  2. Product explorer, retailer averages, price movers, and overview tabs render from API responses.
  3. Search/autocorrection controls still guide user selection.
  4. Streamlit no longer directly scans raw CSVs for dashboard tab data.

**Plans**: 2 plans

Plans:
- [ ] 03-01: Add API client layer and wire sidebar/filter flows to API calls.
- [ ] 03-02: Refactor all four tabs to use API payloads and preserve existing UX behavior.

### Phase 4: Deployment & Verification Hardening

**Goal**: Make the separated Falcon + Streamlit app understandable, runnable, and safely verifiable.

**Depends on**: Phase 3

**Requirements**: REQ-12, NFR-01, NFR-02, NFR-03, NFR-04, NFR-05, NFR-06

**Success Criteria** (what must be TRUE):
  1. Documentation explains separate Falcon API and Streamlit frontend run commands.
  2. Verification scripts cover core domain behavior and API/frontend contract assumptions.
  3. Dependency notes are clear for the user's `uv` workflow without surprise installs.
  4. No new secrets or generated temp artifacts are left behind.

**Plans**: 2 plans

Plans:
- [ ] 04-01: Add run/deployment documentation and dependency notes.
- [ ] 04-02: Add focused verification scripts/checks and final cleanup.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4.
Independent plans inside a phase may run in parallel when they do not touch the same files.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Hexagonal Core Extraction | 0/2 | Not started | - |
| 2. Falcon API Backend | 0/2 | Not started | - |
| 3. Streamlit API Frontend | 0/2 | Not started | - |
| 4. Deployment & Verification Hardening | 0/2 | Not started | - |

---
*Last updated: 2026-07-16 after initialization*
