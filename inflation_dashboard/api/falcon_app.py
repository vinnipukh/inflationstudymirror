from __future__ import annotations

import falcon

import orjson

from inflation_dashboard.api import resources

# orjson serializes large record payloads several times faster than stdlib
# json.dumps; every value leaving the API is already JSON-native (NaN/NaT are
# mapped to None by serialization.to_json_value), so orjson's strict mode is
# safe.
_JSON_HANDLER = falcon.media.JSONHandler(dumps=orjson.dumps, loads=orjson.loads)


def create_app() -> falcon.App:
    """Create the Falcon WSGI application and register API resources."""

    app = falcon.App()
    app.req_options.media_handlers[falcon.MEDIA_JSON] = _JSON_HANDLER
    app.resp_options.media_handlers[falcon.MEDIA_JSON] = _JSON_HANDLER
    app.add_route("/api/health", resources.HealthResource())
    app.add_route("/api/inventory", resources.InventoryResource())
    app.add_route("/api/history", resources.HistoryResource())
    app.add_route("/api/retailer-averages", resources.RetailerAveragesResource())
    app.add_route("/api/movers", resources.MoversResource())
    app.add_route("/api/coverage", resources.CoverageResource())
    return app
