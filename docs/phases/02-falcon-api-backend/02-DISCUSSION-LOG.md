# Phase 2: Falcon API Backend - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-16
**Phase:** 2-Falcon API Backend
**Areas discussed:** API contract shape, Loading and cache behavior, Errors and empty states, Verification and service boundary

---

## API Contract Shape

| Question | Options Presented | Selected |
|----------|-------------------|----------|
| How should the Falcon endpoints be organized? | REST-ish resources with query params; dashboard-shaped endpoints; single aggregate endpoint; You decide | REST-ish resources with query params: `/api/inventory`, `/api/history`, `/api/retailer-averages`, `/api/movers`, `/api/coverage` |
| Should responses use a consistent envelope or return bare JSON? | `{data, meta, errors}` envelope; bare JSON; hybrid; You decide | Envelope every response as `{data, meta, errors}` |
| How should dates and pandas/numpy values be serialized? | ISO date strings plus JSON-native scalars; epoch timestamps; pandas-like string formatting; You decide | ISO date strings plus JSON-native scalars |
| How should filters be passed to endpoints? | Repeated `retailer` query params plus `start_date`/`end_date`/`max_files`; comma-separated retailers; POST JSON bodies; You decide | Repeated query params |

**Notes:** User accepted the recommended REST-ish, query-param based API contract.

---

## Loading and Cache Behavior

| Question | Options Presented | Selected |
|----------|-------------------|----------|
| When should the API read CSV inventory/history? | Cached inventory; filtered endpoints load after filters; independent endpoint loading; one initialization load | Cached inventory; filtered endpoints load history only after explicit filters |
| What defaults should filtered endpoints use when filters are omitted? | Phase 1 CSV defaults; require all filters; default all retailers/full range; You decide | Use Phase 1 `DEFAULT_RETAILERS` and `DEFAULT_MAX_FILES_PER_RETAILER` |
| Should the API allow full-history/all-files loading? | Explicit `max_files=0` or `all_history=true`; disallow in Phase 2; unrestricted by default; You decide | Allow only through explicit opt-in with metadata warning/count estimate |
| What caching approach should downstream planning assume? | stdlib `lru_cache`/module cache; no API caching; dedicated caching package; You decide | stdlib caching only; no new cache dependency |

**Notes:** User prioritized preserving bounded loading and avoiding new cache infrastructure.

---

## Errors and Empty States

| Question | Options Presented | Selected |
|----------|-------------------|----------|
| How should invalid filters vs empty results behave? | 400 for invalid filters and 200 empty data for valid no-row results; 404 for no rows; always 200; You decide | 400 for invalid filters; 200 with empty data for valid empty results |
| How should skipped CSV file diagnostics surface? | Include in coverage and data endpoint meta; only in coverage; hidden unless debug; You decide | Include skipped-file diagnostics in coverage and data endpoint metadata; non-fatal unless all selected files fail |
| Should API errors include frontend-ready messages or only codes? | Simple English messages; structured codes only; both codes and messages; You decide | Simple English messages suitable for frontend presentation later |
| What should `/api/health` validate? | App import/basic config only; inventory discovery; bounded sample load; You decide | Lightweight app import/basic config only |

**Notes:** The user initially gave an empty response on the message-vs-code question; it was retried once per workflow rules and then answered.

---

## Verification and Service Boundary

| Question | Options Presented | Selected |
|----------|-------------------|----------|
| How should Phase 2 smoke-test the Falcon API? | Falcon testing utilities or direct resource invocation in an ad-hoc temp script; start server and HTTP smoke tests; py_compile/import only; You decide | Falcon testing utilities or direct resource invocation in an ad-hoc temp script; do not launch long-running server |
| Where should Falcon-specific code live? | Dedicated module such as `inflation_dashboard/api/falcon_app.py`; root `api.py`; embed in `streamlit_app.py`; You decide | Dedicated adapter package/module such as `inflation_dashboard/api/falcon_app.py` |
| How should dependency handling be captured for planners? | Add Falcon to dependency metadata if imported, user installs/runs with `uv`; do not touch metadata; add broad dependencies; You decide | Add Falcon if code imports it; user remains responsible for `uv` install/run |
| What boundary checks should Phase 2 include? | API modules do not import Streamlit and core modules do not import Falcon; endpoint payload checks only; defer boundary verification; You decide | Verify API modules do not import Streamlit and domain/core modules do not import Falcon |

**Notes:** User accepted the recommended verification and boundary approach.

---

## Claude's Discretion

- Exact helper names and module splits are flexible as long as the API contract, envelope, bounded loading, and framework boundary decisions are preserved.

## Deferred Ideas

None.
