---
phase: 04-deployment-verification-hardening
plan: 04-01
subsystem: docs-deployment
tags: [falcon, streamlit, deployment, documentation, dependencies, user-guide]
verification: docs/04-VERIFICATION.md (passed 2026-07-17; re-verified 2026-08-16)

requires:
  - phase: 03-streamlit-api-frontend
    provides: separated Falcon API + Streamlit frontend architecture on HTTP
provides:
  - Documentation reflecting the full 3-phase architecture with separate run commands for API and frontend
  - USER_GUIDE.md end-user walkthrough of all four dashboard tabs
  - Dependency declarations for the dashboard stack in pyproject.toml and requirements.txt (uv-managed)
affects: [04-deployment-verification-hardening, docs, pyproject, requirements]

tech-stack:
  added: [pandas>=2.0, plotly, streamlit, requests>=2.32.0 as tracked deps]
  patterns:
    - Two-process run model documented: Terminal 1 waitress-serve (Falcon API), Terminal 2 streamlit run (frontend)
    - Dependency tracking via uv-managed pyproject.toml (+ requirements.txt mirror)

key-files:
  modified:
    - README.md (Dashboard Quick Start, updated structure, doc links)
    - docs/ARCHITECTURE.md (rewritten: core -> Falcon API -> Streamlit frontend on HTTP, run commands, data-flow diagram)
    - docs/API.md (all 6 endpoints + frontend integration table mapping client methods)
    - docs/GETTING-STARTED.md ("Run the Stack" Terminal 1/Terminal 2 commands)
    - docs/DEVELOPMENT.md (repo shape and development commands for the API/frontend split)
    - docs/TESTING.md (three verification scripts documented with expected output)
    - docs/CONFIGURATION.md (dependency declarations, frontend API client defaults, running the stack)
    - pyproject.toml (dashboard deps added to [project.dependencies])
    - requirements.txt (dashboard deps added)
  created:
    - docs/USER_GUIDE.md

key-decisions:
  - "Run docs show separate commands for the two processes (REQ-12): waitress-serve for the Falcon API, streamlit run for the dashboard."
  - "All dashboard dependencies are declared in pyproject.toml so `uv sync` is the single install command (NFR-03); no hardcoded secrets introduced (NFR-02)."
  - "CSV remains the single storage adapter — no database or cache infrastructure added (NFR-01, NFR-06 bounded loading preserved)."

patterns-established:
  - "Docs distinguish the two deployment processes explicitly, with a run-command reference and expected verifier output for every check script."