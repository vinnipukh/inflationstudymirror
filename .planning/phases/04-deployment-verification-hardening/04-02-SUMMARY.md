---
phase: 04-deployment-verification-hardening
plan: 04-02
subsystem: verification
tags: [falcon, streamlit, smoke-test, verifier, cross-layer, full-stack]
verification: docs/04-VERIFICATION.md (passed 2026-07-17; re-verified 2026-08-16 -- exit 0)

requires:
  - phase: 04-deployment-verification-hardening
    provides: 04-01 docs + dependency metadata
  - phase: 02-falcon-api-backend
    provides: Falcon endpoint contract with {data, meta, errors} envelopes
  - phase: 03-streamlit-api-frontend
    provides: inflation_dashboard.frontend.api_client consuming those envelopes
provides:
  - scripts/verify_full_stack.py: one-command combined smoke test of the entire dashboard/API stack
  - TESTING.md sections documenting all three verification modes and expected output
  - Cross-layer integration proving the frontend client can consume real Falcon TestClient responses
affects: [04-deployment-verification-hardening, scripts, docs/TESTING.md]

tech-stack:
  added: []
  patterns:
    - In-process Falcon TestClient (no persistent server) driving the real frontend api_client end-to-end
    - Envelope validation and ApiClientError propagation verified across the API -> client boundary
    - ASCII-safe console output + UTF-8 stdout reconfigure so Unicode prints never crash verifiers on Windows cp1252 consoles

key-files:
  created:
    - scripts/verify_full_stack.py
  modified:
    - docs/TESTING.md (three verification modes documented with expected output)

key-decisions:
  - "verify_full_stack.py is the recommended single command: it folds in every check from verify_falcon_api.py and verify_streamlit_api_frontend.py plus cross-layer integration (NFR-04)."
  - "The frontend api_client calls directly through an in-process Falcon TestClient, never via HTTP, and never starts a persistent server."
  - "2026-08-16 re-verification fix: the final PASS line used the U+2194 'left-right arrow' character, which crashed with UnicodeEncodeError on Windows cp1252 consoles after all checks passed. Replaced with ASCII '<->' and added sys.stdout/stderr reconfigure(encoding='utf-8', errors='replace') at script top. docs/TESTING.md and docs/GETTING-STARTED.md expected output updated to match."

patterns-established:
  - "Verifiers must be console-encoding-proof: ASCII-only prints plus a UTF-8 stdout reconfigure guard, so environment console codepage cannot mask a real pass/fail result."
  - "Cross-layer checks exercise the real frontend client against the real API app; envelope structure and error propagation are asserted end-to-end."