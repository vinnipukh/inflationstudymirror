# Documentation Index

Welcome to the **Inflation Study Mirror** documentation. This directory is the unified technical knowledge base and reference manual for the entire repository.

---

## 1. System Architecture & Codebase Overview

- **[Architecture](ARCHITECTURE.md)**: System overview, hexagonal architecture, Falcon API backend, Streamlit frontend, and data flows.
- **[Structure](STRUCTURE.md)**: Top-level directory layout, file conventions, repository boundaries, and artifact locations.
- **[Stack](STACK.md)**: Languages, web frameworks, machine learning dependencies, browser automation engines, and transports.
- **[Integrations](INTEGRATIONS.md)**: Retailer and rental scraping integrations, external endpoints, secrets, and daily timetable.
- **[Conventions](CONVENTIONS.md)**: Coding standards, naming schemes, signal patterns, and testing principles (no unit tests for scrapers).
- **[Concerns](CONCERNS.md)**: Fragile scraping areas, anti-bot mitigation profiles, data volume constraints, and risk management.

---

## 2. Getting Started & Development Guides

- **[Getting Started](GETTING-STARTED.md)**: Local installation, environment setup, and running the Falcon API and Streamlit dashboard.
- **[Development Guide](DEVELOPMENT.md)**: Common developer workflows, running scrapers, executing calculators, and verification commands.
- **[Configuration](CONFIGURATION.md)**: Environment variables, secret keys, scraper arguments, and CI workflow configurations.
- **[API Reference](API.md)**: Falcon REST API endpoints, request parameters, response envelopes, and error codes.
- **[User Guide](USER_GUIDE.md)**: Guide to using the interactive Streamlit dashboard tabs and analytical features.

---

## 3. Scrapers & Scraping Knowledge Base

- **[Approach](APPROACH.md)**: Recommended data-acquisition strategies, anti-bot handling, and decision gates for residential rental scraping.
- **[Tech Stack Search & Recon](TECH-STACK-SEARCH.md)**: Scraping tool catalog, driver evaluations, and historical scraper modernization logs.
- **[Testing Principle](TESTING.md)**: Verification policies, bounded live testing, and API verification test suites.
- **[Scraping Wiki](scraping-wiki/README.md)**: Deep technical wiki snapshot covering bot detection, fingerprinting, CDP detection, cookie reuse, and evasion techniques.

---

## 4. Project Planning & Phase History

- **[Planning Hub](planning/README.md)**: Overview of project requirements, roadmap, milestone state, and historical execution records.
  - **[Project Definition](planning/PROJECT.md)**: Vision, goals, scope boundaries, and deployment architecture target.
  - **[Requirements](planning/REQUIREMENTS.md)**: System requirements and acceptance criteria.
  - **[Roadmap](planning/ROADMAP.md)**: Multi-phase milestones and roadmap.
  - **[Project State](planning/STATE.md)**: Milestone progression, decisions, and metrics.
  - **[Phases History](planning/phases/)**: Detailed execution logs for Phases 01 through 05.
  - **[Quick Tasks](planning/quick/)**: Summaries for quick-patch and speedup tasks.
  - **[Research](planning/research/SUMMARY.md)**: Deep research summaries and scraping gap analysis.
