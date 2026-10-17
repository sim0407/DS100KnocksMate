"""学習者コードの結果（DataFrame/Series/スカラー等）をJSON安全な辞書に変換する。

出力形式（core.execution.results の TableResult / ScalarResult に対応）:
    {"type": "table", "columns", "rows", "kinds", "row_count", "truncated"}
    {"type": "scalar", "value", "kind"}
    {"type": "text", "text", "truncated"}   # 表やスカラーでない値（repr、文字数制限あり）
    {"type": "none"}                         # 最後の式の値が None

index の扱い: 名前のない index（queryで残る行番号など）は捨て、名前付き/MultiIndex
（groupby の集計キーなど）は列に戻す。Series の名前のない index が整数以外（列名など
のラベル）なら列 `index` として残す。pickle 等の任意オブジェクトは返さない。
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from core.execution.results import (
    BOOLEAN,
    DATETIME,
    FLOAT,
    INTEGER,
    NULL,
    STRING,
    infer_kind,
)

TRUNCATION_MARK = "…（省略）"


def serialize_value(value: Any, *, max_rows: int = 200, max_text_chars: int = 20000) -> dict:
    if value is None:
        return {"type": "none"}
    if isinstance(value, (pd.DataFrame, pd.Series)):
        return _table(value, max_rows)
    if isinstance(value, np.ndarray) and value.ndim in (1, 2):
        # np.percentile 等の結果。1次元は列 value、2次元は列 0, 1, ... の表として扱う
        frame = pd.DataFrame(value) if value.ndim == 2 else pd.Series(value, name="value")
        return _table(frame, max_rows)
    scalar = _scalar(value)
    if scalar is not None:
        return scalar
    text = repr(value)
    truncated = len(text) > max_text_chars
    if truncated:
        text = text[:max_text_chars] + TRUNCATION_MARK
    return {"type": "text", "text": text, "truncated": truncated}


# ---------------------------------------------------------------- スカラー


def _is_missing(value: Any) -> bool:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return missing is True or missing is np.True_


def _scalar(value: Any) -> dict | None:
    if isinstance(value, (bool, np.bool_)):
        return {"type": "scalar", "value": bool(value), "kind": BOOLEAN}
    if isinstance(value, (int, np.integer)):
        return {"type": "scalar", "value": int(value), "kind": INTEGER}
    if isinstance(value, (float, np.floating, Decimal)):
        if _is_missing(value):
            return {"type": "scalar", "value": None, "kind": NULL}
        return {"type": "scalar", "value": float(value), "kind": FLOAT}
    if isinstance(value, str):
        return {"type": "scalar", "value": value, "kind": STRING}
    if isinstance(value, (pd.Timestamp, dt.date, np.datetime64)):
        if _is_missing(value):
            return {"type": "scalar", "value": None, "kind": NULL}
        return {"type": "scalar", "value": _iso(value), "kind": DATETIME}
    if value is pd.NA or value is pd.NaT:
        return {"type": "scalar", "value": None, "kind": NULL}
    return None


def _iso(value: Any) -> str:
    if isinstance(value, np.datetime64):
        value = pd.Timestamp(value)
    return value.isoformat()


# ---------------------------------------------------------------- 表


def _column_name(name: Any) -> str:
    if isinstance(name, tuple):
        return "_".join(str(part) for part in name if str(part) != "")
    return str(name)


def _restore_index(df: pd.DataFrame) -> pd.DataFrame:
    index = df.index
    if not isinstance(index, pd.MultiIndex) and index.name is None:
        return df.reset_index(drop=True)
    if any(name is not None and name in df.columns for name in index.names):
        return df.reset_index(drop=True)  # 列名と衝突する場合はindexを捨てる
    return df.reset_index()


def _table(value: pd.DataFrame | pd.Series, max_rows: int) -> dict:
    if isinstance(value, pd.Series):
        index = value.index
        # 名前のない index でも、列名などのラベル（整数以外）なら意味があるので残す
        # 例: df.isnull().sum() の index は列名。query 等で残る整数の行番号は捨てる
        keep_labels = (
            index.name is None
            and not isinstance(index, pd.MultiIndex)
            and not pd.api.types.is_integer_dtype(index.dtype)
        )
        value = value.to_frame(name=value.name if value.name is not None else "value")
        if keep_labels:
            value.index = value.index.rename("index")
    df = value.copy(deep=False)
    df.columns = [_column_name(c) for c in df.columns]
    df = _restore_index(df)

    total = len(df)
    head = df.iloc[:max_rows]
    columns: list[list[Any]] = []
    kinds: list[str] = []
    for i in range(head.shape[1]):
        values, kind = _convert_column(head.iloc[:, i])
        columns.append(values)
        kinds.append(kind)
    rows = [list(row) for row in zip(*columns, strict=True)] if columns else [[]] * len(head)
    return {
        "type": "table",
        "columns": [str(c) for c in df.columns],
        "rows": rows,
        "kinds": kinds,
        "row_count": total,
        "truncated": total > len(head),
    }


def _convert_value(value: Any) -> Any:
    if _is_missing(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating, Decimal)):
        return float(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (pd.Timestamp, dt.date, np.datetime64)):
        return _iso(value)
    if isinstance(value, (pd.Timedelta, dt.timedelta)):
        return str(value)
    return repr(value)[:200]


def _is_datetime_like(value: Any) -> bool:
    return isinstance(value, (pd.Timestamp, dt.date, np.datetime64))


def _convert_column(series: pd.Series) -> tuple[list[Any], str]:
    dtype = series.dtype
    if isinstance(dtype, pd.CategoricalDtype):
        series = series.astype(object)
        dtype = series.dtype

    values = [_convert_value(v) for v in series.tolist()]
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return values, DATETIME
    if pd.api.types.is_bool_dtype(dtype):
        return values, BOOLEAN
    if pd.api.types.is_integer_dtype(dtype):
        return values, INTEGER
    if pd.api.types.is_float_dtype(dtype):
        return values, FLOAT
    if isinstance(dtype, pd.StringDtype):
        return values, STRING

    present = [v for v in series.tolist() if not _is_missing(v)]
    if present and all(_is_datetime_like(v) for v in present):
        return values, DATETIME
    return values, infer_kind(values)
