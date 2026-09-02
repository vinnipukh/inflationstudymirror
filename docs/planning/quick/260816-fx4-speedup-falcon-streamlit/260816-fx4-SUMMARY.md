---
id: 260816-fx4
date: 2026-08-16
type: quick
status: complete
verification: all three verifiers exit 0; before/after benchmarks in body
---

# Summary 260816-fx4: Speed Up Streamlit + Falcon Dashboard

## Result

A single Streamlit interaction (one rerun firing ~5 overlapping API requests)
went from **~20s+ of API time to ~4.5s cold / ~1.1s warm**; the largest
single endpoint (history options, 355k rows / 83MB) went from ~4.4s+serialize
to **~0.9s warm**. All three verifier scripts pass.

## Root causes (measured before)

1. **No server-side caching** — every API request re-read and re-parsed the
   same 135 CSVs with the slow `sep=None, engine="python"` reader
   (`load_filtered_history` ≈ 4.4s each; 5 overlapping requests per rerun).
2. **Repeated filter parsing** — `parse_common_filters` ≈ 0.37s per request.
3. **Triple serialization** — `records_from_frame` walked 2.5M cells through
   the full `to_json_value` isinstance chain; `envelope()` → `json_safe()`
   walked every record again; stdlib `json.dumps` walked them a third time.
4. **No HTTP keep-alive** — frontend opened a fresh connection per request.

## Changes

| File | Change |
|---|---|
| `inflation_dashboard/api/filters.py` | TTL+LRU loaded-history cache (row/byte-budgeted, copy-on-return), `parse_common_filters` signature dedupe, `clear_history_cache()`, cheap dtype-based frame-size estimate (replaces `memory_usage(deep=True)` which cost seconds); `clear_inventory_cache()` clears all derived caches |
| `inflation_dashboard/adapters/csv_price_repository.py` | Per-file built-frame cache keyed `(path, mtime_ns, size)`, TTL 600s, maxsize 512, row cap; `clear_price_cache()` |
| `inflation_dashboard/api/serialization.py` | Typed vectorized `records_from_frame` fast paths (str/StringDtype/float/int/bool/datetime64 with distinct-value date map), byte-identical to generic loop, automatic fallback; `JsonSafeList` marker stops `envelope()` re-walking already-safe records |
| `inflation_dashboard/api/falcon_app.py` | `orjson` JSON media handler for both req and resp |
| `inflation_dashboard/frontend/api_client.py` | Module-level `requests.Session()` keep-alive |
| `scripts/verify_full_stack.py`, `scripts/verify_streamlit_api_frontend.py` | Mock `_SESSION.get` instead of `requests.get`; token assertion updated to `requests.Session` |
| `requirements.txt` | `orjson>=3.12.0` mirror |
| `docs/CONFIGURATION.md` | New "Server-side caching & performance" section |

## Benchmarks (3 retailers × 45 newest files, default frontend filters)

| Scenario | Before | After |
|---|---|---|
| Load filtered history (single request) | ~4.4s | ~0.9s warm (cache hit) |
| Full rerun, cold (all 5 data requests) | ~20s | ~4.5s |
| Full rerun, warm (identical filters) | ~20s | ~1.1s |
| Serialization of 355k-row options payload | ~4s+ | ~0.9s (orjson dump 0.1s) |

Correctness: history payloads byte-identical fast-vs-generic (asserted in a
standalone identity check across str/Timestamp/NaN/NaT/pd.NA/int/bool dtypes);
all three verifiers exit 0.

## Notes / follow-ups

- Options payload still transfers ~355k rows by design (product options reuse
  `/api/history`). A dedicated distinct-products options endpoint would cut
  the remaining ~1s to ~50ms, but changes the API surface — deferred.
- Engine swap (`c` vs `python` sniffing) was benchmarked and is NOT the
  bottleneck (~13%); not adopted.
- Caches are in-process (waitress single process); a multi-worker deployment
  would need an external cache or per-worker warmup.