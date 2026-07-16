# Phase 1: Hexagonal Core Extraction - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-16
**Phase:** 1-Hexagonal Core Extraction
**Areas discussed:** Module boundary, Plotly boundary, Data contract, CSV diagnostics, Verification

---

## Module Boundary

| Question | Selected | Alternatives Considered |
|----------|----------|-------------------------|
| Package shape | You decide based on repo fit | `inflationstudy_core/` hexagonal package; `dashboard_core/` flat package; modules beside `streamlit_app.py` |
| Public interface | Thin functions returning pandas DataFrames | Dataclass result wrappers; pure Python lists/dicts |
| Import boundary | Core may include chart specs but no Streamlit/Falcon | pandas/pathlib only; Plotly-ready helpers mixed into core |
| Streamlit rewiring | Refactor `streamlit_app.py` to import the new core while preserving UI | Create core only and leave Streamlit unchanged; compatibility wrappers |

**Notes:** User delegated exact package naming/layout to implementation judgment, but locked a practical DataFrame-first extraction and immediate Streamlit use of the new core.

---

## Plotly Boundary

| Question | Selected | Alternatives Considered |
|----------|----------|-------------------------|
| Meaning of Plotly-ready helpers | Core returns Plotly-ready dict specs, not Figure objects | Aggregation DataFrames only; optional Plotly figure-builder functions |
| View coverage | Existing four dashboard views only | Future chart types; only product/retailer charts |
| Spec detail | Chart type, x/y/color columns, titles, axis labels, table columns | Full Plotly layout/data dicts; column names only |
| Plotly imports | No Plotly import in core; Streamlit converts specs to figures | Plotly only in visualization module; Plotly anywhere except adapters |

**Notes:** The core can help the UI decide how to chart, but display libraries remain outside the core boundary.

---

## Data Contract

| Question | Selected | Alternatives Considered |
|----------|----------|-------------------------|
| Normalized history columns | `date`, `retailer`, `product_id`, `product_name`, `category`, `price`, `source_file` | Add raw price/currency/source path/parse confidence; separate narrow view DataFrames only |
| Loader return shape | `(history_df, skipped_df)` | Result dataclass; dict of named DataFrames |
| Public use cases | Separate functions for inventory, product history slice, retailer averages, movers, coverage | Raw history only; one combined dashboard payload |
| JSON readiness | Preserve pandas dtypes; Falcon serialization later | Force API-safe dtypes now; add JSON conversion helpers now |

**Notes:** DataFrame contracts should be stable enough for Phase 2, but Falcon JSON serialization remains out of scope for Phase 1.

---

## CSV Diagnostics

| Question | Selected | Alternatives Considered |
|----------|----------|-------------------------|
| Skipped-file detail | Relative file + reason | Structured stage/exception/columns/row count; log-only diagnostics |
| Delimiter handling | Preserve `sep=None, engine='python'` | Fast default with fallback; explicit delimiter per source |
| Retailer allowlist | Keep current supported-retailer allowlist | Inventory all dated CSVs then skip unsupported; remove allowlist |
| Source-specific quirks | Keep current branches unless tests prove simplification safe | Generalize all sources; per-retailer parser classes |

**Notes:** Behavior preservation is more important than parser cleanup in this phase.

---

## Verification

| Question | Selected | Alternatives Considered |
|----------|----------|-------------------------|
| Proof check | OS-temp ad-hoc script over bounded real CSVs | Add pytest tests now; only `py_compile` |
| Boundary enforcement | Assert core modules do not import Streamlit or Falcon | Code review only; only check Streamlit imports core |
| Output assertions | Expected columns and non-empty rows for small selected data | Exact row counts; no-crash only |
| Compile/static check | Only ad-hoc script; `py_compile` redundant | `py_compile` plus ad-hoc; full app/server checks |

**Notes:** Verification should be lightweight and runtime-based, matching the project’s current lack of a canonical test suite.

---

## Claude's Discretion

- Exact package name and folder layout are left to implementation judgment, provided the hexagonal boundary remains clear.

## Deferred Ideas

None.
