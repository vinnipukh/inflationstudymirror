---
slug: fix-waitress-call-flag
created: 2026-07-17
status: in-progress
---

# Fix waitress-serve missing --call flag

## Problem

`uv run waitress-serve --port=8000 inflation_dashboard.api.falcon_app:create_app` crashes with:
```
TypeError: create_app() takes 0 positional arguments but 2 were given
```

Waitress interprets `module:func` as a direct WSGI callable and calls it with `(environ, start_response)`. But `create_app()` is a factory function — it returns a `falcon.App`. The `--call` flag tells waitress to call the function first, then WSGI-call the returned app.

## Fix

1. Update `docs/DEVELOPMENT.md` line 59 to include `--call`:
   ```
   uv run waitress-serve --port=8000 --call inflation_dashboard.api.falcon_app:create_app
   ```
2. Verify with a quick smoke test.

## Impact

- Single-command fix, no code changes needed.
- The Streamlit "API response from /api/inventory was not valid JSON" error was a consequence — the server was crashing before any route could respond.
