from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd


def to_json_value(value: object) -> object:
    """Convert pandas/numpy/date scalar values into JSON-native values."""

    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, np.generic):
        return to_json_value(value.item())
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, Mapping):
        return json_safe_mapping(value)
    if isinstance(value, tuple):
        return [to_json_value(item) for item in value]
    if isinstance(value, list):
        return [to_json_value(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def json_safe(value: object) -> object:
    """Recursively convert values into a JSON-native object graph."""

    return to_json_value(value)


def records_from_frame(frame: pd.DataFrame | None, columns: Sequence[str] | None = None) -> list[dict[str, object]]:
    """Return JSON-safe records from a DataFrame, preserving requested column order."""

    if frame is None or frame.empty:
        return []

    selected_columns = list(frame.columns)
    if columns is not None:
        selected_columns = [column for column in columns if column in frame.columns]

    if not selected_columns:
        return []

    records: list[dict[str, object]] = []
    for row in frame[selected_columns].itertuples(index=False, name=None):
        records.append(
            {
                column: to_json_value(value)
                for column, value in zip(selected_columns, row, strict=True)
            }
        )
    return records


def json_safe_mapping(mapping: Mapping[object, object] | None) -> dict[str, object]:
    """Return a JSON-safe dict with string keys."""

    if not mapping:
        return {}
    return {str(key): to_json_value(value) for key, value in mapping.items()}


def envelope(data: object, meta: Mapping[object, object] | None = None, errors: Sequence[object] | None = None) -> dict[str, object]:
    """Return the stable API response envelope."""

    return {
        "data": json_safe(data),
        "meta": json_safe_mapping(meta or {}),
        "errors": json_safe(list(errors or [])),
    }


def error_envelope(code: str, message: str, *, meta: Mapping[object, object] | None = None) -> dict[str, object]:
    """Return a JSON-safe HTTP error envelope with a short displayable message."""

    return envelope(None, meta=meta or {}, errors=[{"code": code, "message": message}])
