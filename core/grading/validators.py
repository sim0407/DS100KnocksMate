"""性質による採点（乱数を使い、正解の行が1つに決まらない問題用）。

各バリデータは (作成されたデータ {名前: 表}, 参照データ, パラメータ) を受け取り、Comparison を返す。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from core.execution.results import TableResult
from core.grading.compare import Comparison


def _canon_rows(table: TableResult) -> Counter:
    return Counter(tuple("" if v is None else str(v) for v in row) for row in table.rows)


def train_test_split(
    artifacts: dict[str, TableResult], universe: TableResult, params: dict[str, Any]
) -> Comparison:
    """学習用・テスト用に分割したデータ（089）: 重なりなし・合わせると全体・テストの割合。

    artifacts は {"train": 表, "test": 表}（採点定義の artifacts の順に train, test）。
    """
    train, test = artifacts["train"], artifacts["test"]
    reasons = []
    for label, table in (("学習用", train), ("テスト用", test)):
        if sorted(table.columns) != sorted(universe.columns):
            reasons.append(f"{label}データの項目が違います（期待: {', '.join(universe.columns)}）")
    if reasons:
        return Comparison(False, reasons)

    order = [train.columns.index(c) for c in universe.columns]
    train = TableResult(
        universe.columns,
        [[r[i] for i in order] for r in train.rows],
        universe.kinds,
        len(train.rows),
    )
    order = [test.columns.index(c) for c in universe.columns]
    test = TableResult(
        universe.columns, [[r[i] for i in order] for r in test.rows], universe.kinds, len(test.rows)
    )

    train_rows, test_rows, all_rows = _canon_rows(train), _canon_rows(test), _canon_rows(universe)
    if train_rows & test_rows:
        reasons.append(
            f"学習用とテスト用に同じ顧客が{sum((train_rows & test_rows).values())}件含まれています"
        )
    if train_rows + test_rows != all_rows:
        reasons.append(
            f"学習用とテスト用を合わせても、対象の顧客全体（{len(universe.rows)}件）と一致しません"
            f"（実際: {len(train.rows) + len(test.rows)}件）"
        )
    total = len(universe.rows)
    expected_test = params.get("test_ratio", 0.2) * total
    if abs(len(test.rows) - expected_test) > 1:
        reasons.append(
            f"テスト用データの割合が違います（期待: 約{params.get('test_ratio', 0.2):.0%} = 約{expected_test:.0f}件 / "
            f"実際: {len(test.rows)}件）"
        )
    return Comparison(not reasons, reasons)


def undersampling(
    artifacts: dict[str, TableResult], universe: TableResult, params: dict[str, Any]
) -> Comparison:
    """アンダーサンプリング（091）: 売上あり/なしが1:1で、少ない方は全件・実在する顧客のみ。

    universe は (customer_id, 売上ありなら1) の表。artifacts は {"sample": 表}。
    """
    sample = artifacts["sample"]
    id_column = params.get("id_column", "customer_id")
    if id_column not in sample.columns:
        return Comparison(False, [f"抽出したデータに {id_column} 列がありません"])
    is_buy = {row[0]: bool(row[1]) for row in universe.rows}
    ids = [row[sample.columns.index(id_column)] for row in sample.rows]
    if len(ids) != len(set(ids)):
        return Comparison(False, ["同じ顧客が複数回抽出されています"])
    unknown = [i for i in ids if i not in is_buy]
    if unknown:
        return Comparison(False, [f"顧客データにない顧客IDが含まれています（例: {unknown[0]}）"])

    buyers = sum(1 for i in ids if is_buy[i])
    non_buyers = len(ids) - buyers
    minority = min(sum(is_buy.values()), len(is_buy) - sum(is_buy.values()))
    reasons = []
    if buyers != non_buyers:
        reasons.append(
            f"売上実績あり・なしの件数が1:1ではありません（あり: {buyers}件 / なし: {non_buyers}件）"
        )
    elif buyers != minority:
        reasons.append(
            f"件数が少ない方の顧客は全件（{minority}件）残してください（実際: {buyers}件ずつ）"
        )
    return Comparison(not reasons, reasons)


# 採点定義の artifacts を、この順で各バリデータの役割名に対応づける
VALIDATOR_ROLES: dict[str, tuple[str, ...]] = {
    "train_test_split": ("train", "test"),
    "undersampling": ("sample",),
}

VALIDATORS: dict[
    str, Callable[[dict[str, TableResult], TableResult, dict[str, Any]], Comparison]
] = {
    "train_test_split": train_test_split,
    "undersampling": undersampling,
}
