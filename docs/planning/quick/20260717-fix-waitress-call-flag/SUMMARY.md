---
slug: fix-waitress-call-flag
created: 2026-07-17
status: complete
verified: true
---

## Summary

**Fix:** Added `--call` flag to `waitress-serve` command in `docs/DEVELOPMENT.md`.

**Root cause:** `waitress-serve module:func` treats the function as a direct WSGI callable and calls it with `(environ, start_response)`. But `create_app()` is a factory — it returns a `falcon.App`. The `--call` flag tells waitress to invoke the factory first, then WSGI-call the returned app.

**Verification:** Started server with `uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app` and confirmed:
- `GET /api/health` → 200 `{"data": {"status": "ok"}, ...}`
- `GET /api/inventory` → 200 with 753 files across 10 retailers

**File changed:** `docs/DEVELOPMENT.md` (line 59, one-line command fix)
