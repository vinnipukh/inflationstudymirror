# Concerns

## Environment drift

Scrapers use different browser engines, network stacks and Python versions. Source workflows intentionally install small pinned dependency sets; a package upgrade can change TLS/browser behavior even when imports still succeed.

## Anti-bot and source fragility

- Watsons/Akamai requires serialized, paced requests.
- Protected rental sources require coherent persistent sessions and explicit challenge-stop behavior.
- Browser/driver lifecycle changes can break pagination or memory/session stability.
- Selectors and source APIs change without notice.

Use the mandatory wiki, bounded live runs and source diagnostics before changing behavior.

## Secret handling

Cookies, user-agent bindings and browser profiles are sensitive. Keep them in environment variables/secret stores and out of source, logs, docs and workflow output.

## Data quality

- Retailer schemas and date coverage vary.
- Product IDs/names may drift or be reused.
- Some sources expose lowest-offer prices rather than representative transaction prices.
- Partial scraper runs must not masquerade as complete daily snapshots.
- Inflation results depend on matched products and category mappings.

## Data volume and Git history

Daily CSV and log commits grow repository history quickly. Track required source data, but do not commit regenerable partitions, databases, browser profiles or transient state without an explicit policy decision.

## Calculation coverage

TÜİK-style weighted metrics are normalized over covered groups, not a complete official CPI basket when sectors are missing. Methodology and coverage notes must travel with generated outputs.

Legacy calculator-specific configs are not always consistent with the canonical 2026 main-group codes. In particular, some older personal-care mappings still use `12`, while the repository-wide configuration reserves `12` for insurance/finance and uses `13` for personal care. Reconcile and regenerate affected artifacts before cross-sector aggregation.
