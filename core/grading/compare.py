"""表・スカラーの比較器。

採点ルール（docs/PRODUCT_REQUIREMENTS.md §9.2）:
列は既定で名前・順序とも一致が必要。column_names=False なら名前を問わず位置で対応づける。

- unordered: 行の多重集合が一致（重複を保持、行順は問わない）
- ordered:   行の並びまで一致
- sorted:    多重集合が一致し、学習者の結果が sort_keys の順に並んでいる（同順位内は問わない）
- subset_n:  「先頭N件」ルール。min(N, 全体)行で、各行が全結果（universe）に含まれる
- top_n:     「上位N件」。subset_n に加えて sort_keys の順に並び、キー列の値の並びが上位N件と一致
             （境界の同順位はどの行でもよい）

日時は表記をそろえて比較する（深夜0時の日時は日付とみなす: 2019-01-01 == 2019-01-01T00:00:00）。
数値は integer/float を区別せず、小数第 `float_decimals` 位に丸めて比較する。
丸め境界をまたぐごく僅かな差は不一致になりうる（既知の限界）。
不一致の理由には期待値（模範解答の値）を含めない。学習者自身の行は例示してよい。
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from core.execution.results import (
    BOOLEAN,
    DATETIME,
    FLOAT,
    INTEGER,
    NULL,
    OTHER,
    STRING,
    ScalarResult,
    TableResult,
    is_null,
)

RowMode = Literal["unordered", "ordered", "sorted", "subset_n", "top_n"]

_KIND_GROUP = {
    INTEGER: "数値",
    FLOAT: "数値",
    STRING: "文字列",
    DATETIME: "日時",
    BOOLEAN: "真偽値",
    OTHER: "その他",
}
_MAX_EXAMPLES = 3


@dataclass(frozen=True)
class SortKey:
    column: str
    descending: bool = False


@dataclass(frozen=True)
class TableSpec:
    rows: RowMode = "unordered"
    sort_keys: tuple[SortKey, ...] = ()
    n: int | None = None
    column_order: bool = True
    # False: 列名を問わず位置で対応づける（問題文が列名を指定しない集計など）。列の数と順序は一致が必要
    column_names: bool = True
    # 先頭の何列だけを比べるか（以降の列は自由）。None なら全列
    key_columns: int | None = None
    float_decimals: int = 6

    def __post_init__(self) -> None:
        if self.rows in ("subset_n", "top_n") and (self.n is None or self.n < 1):
            raise ValueError(f"rows={self.rows} には正の n が必要")
        if self.rows in ("sorted", "top_n") and not self.sort_keys:
            raise ValueError(f"rows={self.rows} には sort_keys が必要")


@dataclass(frozen=True)
class Comparison:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    gradable: bool = True


# ---------------------------------------------------------------- 値の正規化


def _canon(value: Any, decimals: int) -> tuple:
    if is_null(value):
        return ("null",)
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, (int, float)):
        rounded = round(float(value), decimals)
        return ("n", 0.0 if rounded == 0 else rounded)
    if isinstance(value, str):
        return ("s", value)
    return ("o", repr(value))


def _canon_datetime(value: Any) -> Any:
    """ISO形式の日時文字列を比較用にそろえる（タイムゾーン付きはUTCへ、深夜0時は日付へ）。"""
    if not isinstance(value, str):
        return value
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.UTC).replace(tzinfo=None)
    if parsed.time() == dt.time(0):
        return parsed.date().isoformat()
    return parsed.isoformat()


def _normalize_datetime_columns(rows: list[list[Any]], indexes: list[int]) -> list[list[Any]]:
    if not indexes:
        return rows
    result = []
    for row in rows:
        row = list(row)
        for i in indexes:
            row[i] = _canon_datetime(row[i])
        result.append(row)
    return result


def _canon_row(row: Sequence[Any], decimals: int) -> tuple:
    return tuple(_canon(v, decimals) for v in row)


def _kinds_compatible(expected: str, actual: str) -> bool:
    if NULL in (expected, actual):
        return True
    return _KIND_GROUP.get(expected) == _KIND_GROUP.get(actual)


def _fmt_value(value: Any) -> str:
    if is_null(value):
        return "NULL"
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


def _fmt_row(row: Sequence[Any]) -> str:
    text = "(" + ", ".join(_fmt_value(v) for v in row) + ")"
    return text if len(text) <= 120 else text[:117] + "..."


def _examples(rows: list[Sequence[Any]]) -> str:
    return " / ".join(_fmt_row(r) for r in rows[:_MAX_EXAMPLES])


# ---------------------------------------------------------------- 比較本体


def compare_scalars(
    expected: ScalarResult, actual: ScalarResult, float_decimals: int = 6
) -> Comparison:
    if not _kinds_compatible(expected.kind, actual.kind):
        return Comparison(
            False,
            [
                f"値の型が違います（期待: {_KIND_GROUP.get(expected.kind, expected.kind)}"
                f" / 実際: {_KIND_GROUP.get(actual.kind, actual.kind)}）"
            ],
        )
    expected_value, actual_value = expected.value, actual.value
    if DATETIME in (expected.kind, actual.kind):
        expected_value, actual_value = (
            _canon_datetime(expected_value),
            _canon_datetime(actual_value),
        )
    if _canon(expected_value, float_decimals) != _canon(actual_value, float_decimals):
        return Comparison(False, [f"値が一致しません（実際: {_fmt_value(actual.value)}）"])
    return Comparison(True)


def compare_tables(
    expected: TableResult, actual: TableResult, spec: TableSpec | None = None
) -> Comparison:
    """expected は採点の基準となる結果（subset_n / top_n では件数制限のない全結果）。"""
    spec = spec or TableSpec()
    for key in spec.sort_keys:
        if key.column not in expected.columns:
            raise ValueError(f"sort key の列が期待結果にない: {key.column}")

    if expected.truncated:
        return Comparison(False, ["参照結果が上限を超えているため採点できません"], gradable=False)
    if actual.truncated:
        return Comparison(
            False,
            [f"結果が大きすぎるため採点できません（{actual.row_count}行）"],
            gradable=False,
        )

    if spec.key_columns is not None:
        k = spec.key_columns
        if len(actual.columns) < k:
            return Comparison(
                False,
                [
                    f"列の数が足りません（少なくとも先頭{k}列が必要 / 実際: {len(actual.columns)}列）"
                ],
            )
        expected = replace(
            expected,
            columns=expected.columns[:k],
            kinds=expected.kinds[:k],
            rows=[r[:k] for r in expected.rows],
        )
        actual = replace(
            actual,
            columns=actual.columns[:k],
            kinds=actual.kinds[:k],
            rows=[r[:k] for r in actual.rows],
        )

    if not spec.column_names:
        if len(actual.columns) != len(expected.columns):
            return Comparison(
                False,
                [
                    f"列の数が違います（期待: {len(expected.columns)}列 / 実際: {len(actual.columns)}列）"
                ],
            )
        actual = replace(actual, columns=list(expected.columns))

    reasons = _check_columns(expected, actual, spec)
    if reasons:
        return Comparison(False, reasons)

    # 列を期待結果の順にそろえる（column_order=False の場合のため）
    order = [actual.columns.index(c) for c in expected.columns]
    actual_rows = [[row[i] for i in order] for row in actual.rows]
    actual_kinds = [actual.kinds[i] for i in order]

    reasons = [
        f"列 {col} の型が違います（期待: {_KIND_GROUP.get(ek, ek)} / 実際: {_KIND_GROUP.get(ak, ak)}）"
        for col, ek, ak in zip(expected.columns, expected.kinds, actual_kinds, strict=True)
        if not _kinds_compatible(ek, ak)
    ]
    if reasons:
        return Comparison(False, reasons)

    datetime_columns = [
        i
        for i, (ek, ak) in enumerate(zip(expected.kinds, actual_kinds, strict=True))
        if DATETIME in (ek, ak)
    ]
    if datetime_columns:
        expected = replace(
            expected, rows=_normalize_datetime_columns(expected.rows, datetime_columns)
        )
        actual_rows = _normalize_datetime_columns(actual_rows, datetime_columns)

    checker = _ROW_CHECKERS[spec.rows]
    reasons = checker(expected, actual_rows, spec)
    return Comparison(not reasons, reasons)


def _check_columns(expected: TableResult, actual: TableResult, spec: TableSpec) -> list[str]:
    exp_set, act_set = set(expected.columns), set(actual.columns)
    reasons = []
    missing = [c for c in expected.columns if c not in act_set]
    extra = [c for c in actual.columns if c not in exp_set]
    if missing:
        reasons.append(f"不足している列があります: {', '.join(missing)}")
    if extra:
        reasons.append(f"不要な列があります: {', '.join(extra)}")
    if len(actual.columns) != len(set(actual.columns)):
        reasons.append("同じ名前の列が重複しています")
    if not reasons and spec.column_order and actual.columns != expected.columns:
        reasons.append(
            f"列の順序が違います（期待: {', '.join(expected.columns)}"
            f" / 実際: {', '.join(actual.columns)}）"
        )
    return reasons


# ---------------------------------------------------------------- 行の比較


def _count_reason(expected_n: int, actual_n: int) -> str:
    return f"行数が違います（期待: {expected_n}行 / 実際: {actual_n}行）"


def _multiset_reasons(
    expected_rows: list[list[Any]], actual_rows: list[list[Any]], decimals: int
) -> list[str]:
    if len(expected_rows) != len(actual_rows):
        return [_count_reason(len(expected_rows), len(actual_rows))]
    exp = Counter(_canon_row(r, decimals) for r in expected_rows)
    act_canon = [_canon_row(r, decimals) for r in actual_rows]
    surplus = Counter(act_canon) - exp
    if not surplus:
        return []
    bad = [r for r, c in zip(actual_rows, act_canon, strict=True) if c in surplus]
    return [f"期待と一致しない行が{sum(surplus.values())}行あります（例: {_examples(bad)}）"]


def _subset_reasons(
    universe_rows: list[list[Any]], actual_rows: list[list[Any]], decimals: int
) -> list[str]:
    universe = Counter(_canon_row(r, decimals) for r in universe_rows)
    act_canon = [_canon_row(r, decimals) for r in actual_rows]
    surplus = Counter(act_canon) - universe
    if not surplus:
        return []
    bad = [r for r, c in zip(actual_rows, act_canon, strict=True) if c in surplus]
    return [f"条件を満たさない行（または重複しすぎた行）があります（例: {_examples(bad)}）"]


def _key_indexes(expected: TableResult, spec: TableSpec) -> list[tuple[int, bool]]:
    return [(expected.columns.index(k.column), k.descending) for k in spec.sort_keys]


def _first_unsorted(
    rows: list[list[Any]], keys: list[tuple[int, bool]], decimals: int
) -> int | None:
    """並び順に違反する最初の位置 i（rows[i] と rows[i+1] の間）を返す。NULLを含む比較は判定しない。"""
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        for idx, descending in keys:
            va, vb = _canon(a[idx], decimals), _canon(b[idx], decimals)
            if va[0] == "null" or vb[0] == "null":
                break
            if va == vb:
                continue
            if (va > vb) != descending:
                return i
            break
    return None


def _sorted_reason(rows: list[list[Any]], keys: list[tuple[int, bool]], decimals: int) -> list[str]:
    pos = _first_unsorted(rows, keys, decimals)
    if pos is None:
        return []
    return [f"指定された並び順になっていません（{pos + 1}行目と{pos + 2}行目）"]


def _check_unordered(expected: TableResult, rows: list[list[Any]], spec: TableSpec) -> list[str]:
    return _multiset_reasons(expected.rows, rows, spec.float_decimals)


def _check_ordered(expected: TableResult, rows: list[list[Any]], spec: TableSpec) -> list[str]:
    reasons = _multiset_reasons(expected.rows, rows, spec.float_decimals)
    if reasons:
        return reasons
    for i, (e, a) in enumerate(zip(expected.rows, rows, strict=True)):
        if _canon_row(e, spec.float_decimals) != _canon_row(a, spec.float_decimals):
            return [f"行の順序が違います（最初に異なるのは{i + 1}行目）"]
    return []


def _check_sorted(expected: TableResult, rows: list[list[Any]], spec: TableSpec) -> list[str]:
    reasons = _multiset_reasons(expected.rows, rows, spec.float_decimals)
    if reasons:
        return reasons
    return _sorted_reason(rows, _key_indexes(expected, spec), spec.float_decimals)


def _check_subset_n(expected: TableResult, rows: list[list[Any]], spec: TableSpec) -> list[str]:
    assert spec.n is not None
    want = min(spec.n, len(expected.rows))
    if len(rows) != want:
        return [_count_reason(want, len(rows))]
    return _subset_reasons(expected.rows, rows, spec.float_decimals)


def _sort_rows(
    rows: list[list[Any]], keys: list[tuple[int, bool]], decimals: int
) -> list[list[Any]]:
    """キー順に安定ソート（NULLは方向によらず末尾）。"""
    result = list(rows)
    for idx, descending in reversed(keys):
        present = [r for r in result if not is_null(r[idx])]
        nulls = [r for r in result if is_null(r[idx])]
        present.sort(key=lambda r, i=idx: _canon(r[i], decimals), reverse=descending)
        result = present + nulls
    return result


def _check_top_n(expected: TableResult, rows: list[list[Any]], spec: TableSpec) -> list[str]:
    reasons = _check_subset_n(expected, rows, spec)
    if reasons:
        return reasons
    keys = _key_indexes(expected, spec)
    reasons = _sorted_reason(rows, keys, spec.float_decimals)
    if reasons:
        return reasons
    top = _sort_rows(expected.rows, keys, spec.float_decimals)[: len(rows)]

    def key_seq(rs: list[list[Any]]) -> list[tuple]:
        return [tuple(_canon(r[i], spec.float_decimals) for i, _ in keys) for r in rs]

    if key_seq(top) != key_seq(rows):
        return ["上位の行になっていない行があります（並び順の基準となる列の値を確認してください）"]
    return []


_ROW_CHECKERS = {
    "unordered": _check_unordered,
    "ordered": _check_ordered,
    "sorted": _check_sorted,
    "subset_n": _check_subset_n,
    "top_n": _check_top_n,
}
