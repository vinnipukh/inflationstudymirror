from __future__ import annotations

import falcon

from inflation_dashboard.api import resources


def create_app() -> falcon.App:
    """Create the Falcon WSGI application and register API resources."""

    app = falcon.App()
    app.add_route("/api/health", resources.HealthResource())
    app.add_route("/api/inventory", resources.InventoryResource())
    app.add_route("/api/history", resources.HistoryResource())
    app.add_route("/api/retailer-averages", resources.RetailerAveragesResource())
    app.add_route("/api/movers", resources.MoversResource())
    app.add_route("/api/coverage", resources.CoverageResource())
    return app
