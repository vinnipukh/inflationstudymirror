# Project Planning, Requirements & Phase History

This directory contains the project requirements, architecture decisions, multi-phase roadmap, and execution logs for the **Inflation Study Mirror** dashboard and scraper modernization.

---

## Core Planning Documents

- **[Project Definition](PROJECT.md)**: Vision, goals, scope boundaries, and deployment architecture target.
- **[Requirements](REQUIREMENTS.md)**: Traceable functional requirements, non-functional requirements, and acceptance criteria.
- **[Roadmap](ROADMAP.md)**: Phase overview, milestones, deliverables, and progress tracking across all 5 phases.
- **[Project State](STATE.md)**: Current milestone position, completed phase logs, blocker tracking, and decisions.

---

## Execution Records & Historical Logs

- **[Phases History](phases/)**:
  - `01-hexagonal-core-extraction/`: Domain model extraction, CSV repository adapter, and use case separation.
  - `02-falcon-api-backend/`: Falcon REST API endpoints, filter validation, and in-memory TTL caching.
  - `03-streamlit-api-frontend/`: Frontend API client integration, sidebar controls, and 4 dashboard tabs.
  - `04-deployment-verification-hardening/`: Full-stack smoke tests, verification runners, and WSGI configuration.
  - `05-sari-site-rental-scraper-modernization/`: Residential rental scraper plans and anti-bot hardening.
- **[Quick Tasks](quick/)**: Ad-hoc tasks (waitress flag corrections, rental scraper modernizations, API speedups).
- **[Research](research/SUMMARY.md)**: Deep research summaries and scraping gap analysis.
