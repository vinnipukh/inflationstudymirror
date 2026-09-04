"""
Cursor-based (keyset) pagination helpers (principle 8).

Cursors are opaque to clients: a base64url-encoded JSON payload carrying a
version tag and the keyset values. Malformed or stale cursors produce a 400
via ApiFilterError instead of silently returning the wrong page.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from inflation_dashboard.api.filters import ApiFilterError

_CURSOR_VERSION = "v1"


def encode_cursor(payload: dict[str, Any]) -> str:
    """Encode a keyset payload as an opaque cursor string."""
    data = json.dumps({"v": _CURSOR_VERSION, **payload}, separators=(",", ":"))
    return base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(token: str | None, required_fields: tuple[str, ...]) -> dict[str, Any] | None:
    """Decode and validate a cursor; None when absent, ApiFilterError when bad."""
    if token in {None, ""}:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii") + b"=" * (-len(token) % 4))
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("v") != _CURSOR_VERSION:
            raise ValueError("unsupported cursor version")
        for field in required_fields:
            if field not in payload or payload[field] in (None, ""):
                raise ValueError(f"missing cursor field {field}")
        return payload
    except Exception as exc:
        raise ApiFilterError(
            "invalid_cursor",
            "The cursor parameter is malformed or expired; restart pagination from the first page.",
        ) from exc


def page_meta(
    *,
    used_cursor: str | None,
    next_cursor: str | None,
    limit: int,
    count: int,
    total_hint: int | None = None,
) -> dict[str, object]:
    """Standard pagination meta block included in every paginated response."""
    meta: dict[str, object] = {
        "pagination": {
            "cursor": used_cursor,
            "next_cursor": next_cursor,
            "limit": limit,
            "count": count,
        }
    }
    if total_hint is not None:
        meta["pagination"]["total"] = total_hint  # type: ignore[index]
    return meta
