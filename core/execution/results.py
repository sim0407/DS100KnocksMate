"""実行結果の言語非依存な表現。

Python（ワーカーからJSONで受け取る）とSQL（PostgreSQLから取得）の結果を同じ形にそろえ、
比較器（core.grading.compare）と表示の両方で使う。値はJSONで安全に扱える型
（None, bool, int, float, str）に限る。日時はISO 8601文字列にし、列の kind を "datetime" とする。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# 列・値の意味カテゴリ
INTEGER = "integer"
FLOAT = "float"
STRING = "string"
DATETIME = "datetime"
BOOLEAN = "boolean"
NULL = "null"  # すべて欠損で型が決まらない
OTHER = "other"

KINDS = (INTEGER, FLOAT, STRING, DATETIME, BOOLEAN, NULL, OTHER)


@dataclass(frozen=True)
class TableResult:
    columns: list[str]
    rows: list[list[Any]]
    kinds: list[str]
    row_count: int  # 切り詰め前の総行数
    truncated: bool = False  # rows が row_count より少ない（上限で切り詰めた）


@dataclass(frozen=True)
class ScalarResult:
    value: Any
    kind: str


def is_null(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def infer_kind(values: list[Any]) -> str:
    """Pythonの値の列から kind を推定する（欠損は無視）。"""
    present = [v for v in values if not is_null(v)]
    if not present:
        return NULL
    if all(isinstance(v, bool) for v in present):
        return BOOLEAN
    if any(isinstance(v, bool) for v in present):
        return OTHER
    if all(isinstance(v, int) for v in present):
        return INTEGER
    if all(isinstance(v, (int, float)) for v in present):
        return FLOAT
    if all(isinstance(v, str) for v in present):
        return STRING
    return OTHER
