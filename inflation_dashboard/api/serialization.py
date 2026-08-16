from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd


class JsonSafeList(list):
    """List marker whose contents are already JSON-native values.

    `records_from_frame` marks its output so envelope()'s recursive
    `json_safe` pass-through skips re-walking every record cell (which costs
    seconds on 350k-row payloads). Serialization is byte-identical to a plain
    list; only the deep re-conversion is skipped.
    """


def to_json_value(value: object) -> object:
    """Convert pandas/numpy/date scalar values into JSON-native values."""

    if isinstance(value, JsonSafeList):
        return value
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
    """Return JSON-safe records from a DataFrame, preserving requested column order.

    Uses vectorized per-column conversion for the common scalar dtypes
    (str/Timestamp/float/int) so large history payloads serialize in a fraction
    of the per-cell time, with a byte-identical fallback to the generic path.
    """

    if frame is None or frame.empty:
        return []

    selected_columns = list(frame.columns)
    if columns is not None:
        selected_columns = [column for column in columns if column in frame.columns]

    if not selected_columns:
        return []

    column_values: list[list[object]] = []
    for column in selected_columns:
        values = _typed_column_values(frame[column])
        if values is None:
            break
        column_values.append(values)

    if len(column_values) == len(selected_columns):
        return JsonSafeList(dict(zip(selected_columns, row)) for row in zip(*column_values))

    records: list[dict[str, object]] = []
    for row in frame[selected_columns].itertuples(index=False, name=None):
        records.append(
            {
                column: to_json_value(value)
                for column, value in zip(selected_columns, row, strict=True)
            }
        )
    return JsonSafeList(records)


_TIMESTAMP_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _object_scalar_json_value(value: object) -> object:
    """Fast JSON-safe conversion for scalar values found in object columns."""

    value_type = type(value)
    if value_type is str:
        return value
    if value_type is pd.Timestamp:
        return None if pd.isna(value) else value.isoformat()
    if value_type is dt.datetime or value_type is dt.date:
        return None if pd.isna(value) else value.isoformat()
    if value_type is float:
        return None if math.isnan(value) else value
    if value_type is int:
        return value
    if isinstance(value, np.generic):
        return value.item()
    if value is None or value is pd.NA:
        return None
    return to_json_value(value)


def _typed_column_values(series: pd.Series) -> list[object] | None:
    """JSON-safe per-row values for common dtypes, or None for the generic path.

    Output matches `to_json_value` scalar-for-scalar (including None for
    NaN/NaT), so payloads stay byte-identical to the generic loop.
    """

    dtype = series.dtype

    if isinstance(dtype, pd.StringDtype):
        if bool(series.isna().any()):
            return None
        return list(series.tolist())

    if pd.api.types.is_datetime64_any_dtype(dtype):
        if bool(series.isna().any()):
            values = list(series.tolist())
            return [None if pd.isna(value) else value.isoformat() for value in values]
        # dt.strftime() is per-element Python and costs ~1.5s on 350k rows; the
        # history date column has one distinct value per source CSV, so convert
        # the uniques once and index-map them back. Both sides use raw numpy
        # datetime64 so the dict lookup stays all-numpy (unique()/to_numpy()
        # can surface Timestamp vs datetime64 inconsistently in pandas 3.x).
        array = series.to_numpy()
        uniques = np.unique(array)
        lookup = {value: value.item().isoformat() for value in uniques}
        return [lookup[value] for value in array]

    if pd.api.types.is_float_dtype(dtype):
        return [None if math.isnan(value) else value for value in series.to_numpy().tolist()]

    if pd.api.types.is_integer_dtype(dtype):
        return [int(value) for value in series.to_numpy().tolist()]

    if pd.api.types.is_bool_dtype(dtype):
        return [bool(value) for value in series.to_numpy().tolist()]

    if dtype == object:
        has_na = bool(series.isna().any())
        probe = series.iloc[:8]
        if probe.apply(lambda value: value is None or isinstance(value, pd.Timestamp)).all():
            converted = pd.to_datetime(series)
            if converted.dtype != object:
                if bool((converted.dt.microsecond != 0).any()):
                    return None
                if has_na:
                    return [None if pd.isna(value) else value for value in converted.dt.strftime(_TIMESTAMP_ISO_FORMAT).tolist()]
                array = converted.to_numpy()
                uniques = np.unique(array)
                lookup = {value: value.item().isoformat() for value in uniques}
                return [lookup[value] for value in array]
        if not has_na and probe.apply(lambda value: isinstance(value, str)).all():
            return list(series.tolist())
        values = series.tolist()
        if has_na:
            return [None if pd.isna(value) else _object_scalar_json_value(value) for value in values]
        return [_object_scalar_json_value(value) for value in values]

    return None


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
