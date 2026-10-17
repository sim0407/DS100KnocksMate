"""core/grading/compare.py: 表・スカラーの比較器のテスト。

docs/TECHNICAL_DESIGN.md §5「具体的テストケース」と PRODUCT_REQUIREMENTS §9.2 の採点ルールを固定する。
"""

import pytest

from core.execution.results import ScalarResult, TableResult, infer_kind
from core.grading.compare import SortKey, TableSpec, compare_scalars, compare_tables


def table(columns, rows, kinds=None, truncated=False):
    if kinds is None:
        kinds = [infer_kind([r[i] for r in rows]) for i in range(len(columns))]
    return TableResult(
        columns=list(columns),
        rows=[list(r) for r in rows],
        kinds=list(kinds),
        row_count=len(rows),
        truncated=truncated,
    )


COLS = ["sales_ymd", "customer_id", "amount"]
ROWS = [
    [20181103, "CS006214000001", 158],
    [20181118, "CS008415000097", 81],
    [20170712, "CS028414000014", 170],
    [20190205, "ZZ000000000000", 25],
]
EXPECTED = table(COLS, ROWS)


# ---------------------------------------------------------------- 基本（unordered）


def test_identical_tables_pass():
    assert compare_tables(EXPECTED, table(COLS, ROWS)).passed


def test_row_order_ignored_when_not_required():
    assert compare_tables(EXPECTED, table(COLS, ROWS[::-1])).passed


def test_same_row_count_but_different_value_fails():
    rows = [r[:] for r in ROWS]
    rows[2][2] = 171
    result = compare_tables(EXPECTED, table(COLS, rows))
    assert not result.passed
    assert any("一致しない" in r for r in result.reasons)


def test_missing_column_fails_with_column_names_in_reason():
    actual = table(COLS[:2], [r[:2] for r in ROWS])
    result = compare_tables(EXPECTED, actual)
    assert not result.passed
    assert any("amount" in r for r in result.reasons)


def test_extra_column_fails():
    actual = table([*COLS, "x"], [[*r, 1] for r in ROWS])
    assert not compare_tables(EXPECTED, actual).passed


def test_renamed_column_fails():
    actual = table(["sales_date", *COLS[1:]], ROWS)
    result = compare_tables(EXPECTED, actual)
    assert not result.passed
    assert any("sales_date" in r for r in result.reasons)


def test_column_order_enforced_by_default():
    actual = table([COLS[1], COLS[0], COLS[2]], [[r[1], r[0], r[2]] for r in ROWS])
    assert not compare_tables(EXPECTED, actual).passed


def test_column_order_can_be_relaxed():
    actual = table([COLS[1], COLS[0], COLS[2]], [[r[1], r[0], r[2]] for r in ROWS])
    assert compare_tables(EXPECTED, actual, TableSpec(column_order=False)).passed


def test_dropping_duplicates_fails():
    expected = table(COLS, [*ROWS, ROWS[0]])
    result = compare_tables(expected, table(COLS, ROWS))
    assert not result.passed
    assert any("行数" in r for r in result.reasons)


def test_duplicate_multiplicity_must_match_even_with_same_row_count():
    expected = table(COLS, [ROWS[0], ROWS[0], ROWS[1]])
    actual = table(COLS, [ROWS[0], ROWS[1], ROWS[1]])
    assert not compare_tables(expected, actual).passed


# ---------------------------------------------------------------- 値・型


def test_null_equals_null_and_nan_is_null():
    expected = table(["a", "b"], [[1, None], [2, 3.5]])
    actual = table(["a", "b"], [[1, float("nan")], [2, 3.5]])
    assert compare_tables(expected, actual).passed


def test_null_differs_from_value():
    expected = table(["a"], [[None]], kinds=["float"])
    actual = table(["a"], [[0.0]])
    assert not compare_tables(expected, actual).passed


def test_float_within_tolerance_passes():
    expected = table(["v"], [[0.3]])
    assert compare_tables(expected, table(["v"], [[0.1 + 0.2]])).passed


def test_float_outside_tolerance_fails():
    expected = table(["v"], [[0.3]])
    assert not compare_tables(expected, table(["v"], [[0.30001]])).passed


def test_integer_and_float_with_same_value_are_equal():
    """SUMやmeanの結果がint/floatのどちらで返っても値が同じなら同じとみなす。"""
    expected = table(["v"], [[1478]])
    assert compare_tables(expected, table(["v"], [[1478.0]])).passed


def test_zero_padded_code_string_is_not_number():
    expected = table(["category_major_cd"], [["04"]])
    result = compare_tables(expected, table(["category_major_cd"], [[4]]))
    assert not result.passed
    assert any("型" in r for r in result.reasons)


def test_boolean_is_not_integer():
    expected = table(["flag"], [[True], [False]])
    assert not compare_tables(expected, table(["flag"], [[1], [0]])).passed


def test_all_null_column_is_compatible_with_any_kind():
    expected = table(["a"], [[None]], kinds=["string"])
    actual = table(["a"], [[None]], kinds=["null"])
    assert compare_tables(expected, actual).passed


def test_datetime_values_compare_as_iso_strings():
    expected = table(["d"], [["2019-01-01T00:00:00"]], kinds=["datetime"])
    actual = table(["d"], [["2019-01-01T00:00:00"]], kinds=["datetime"])
    assert compare_tables(expected, actual).passed
    other = table(["d"], [["2019-01-02T00:00:00"]], kinds=["datetime"])
    assert not compare_tables(expected, other).passed


# ---------------------------------------------------------------- ordered


def test_ordered_requires_same_row_order():
    spec = TableSpec(rows="ordered")
    assert compare_tables(EXPECTED, table(COLS, ROWS), spec).passed
    result = compare_tables(EXPECTED, table(COLS, ROWS[::-1]), spec)
    assert not result.passed
    assert any("順" in r for r in result.reasons)


# ---------------------------------------------------------------- sorted


SORT_DESC = TableSpec(rows="sorted", sort_keys=(SortKey("amount", descending=True),))


def test_sorted_passes_when_sorted_and_ties_in_any_order():
    expected = table(["id", "amount"], [["a", 30], ["b", 20], ["c", 20], ["d", 10]])
    actual = table(["id", "amount"], [["a", 30], ["c", 20], ["b", 20], ["d", 10]])
    assert compare_tables(expected, actual, SORT_DESC).passed


def test_sorted_fails_when_not_sorted():
    expected = table(["id", "amount"], [["a", 30], ["b", 20], ["d", 10]])
    actual = table(["id", "amount"], [["d", 10], ["b", 20], ["a", 30]])
    result = compare_tables(expected, actual, SORT_DESC)
    assert not result.passed
    assert any("並び" in r for r in result.reasons)


def test_sorted_with_multiple_keys():
    spec = TableSpec(rows="sorted", sort_keys=(SortKey("g"), SortKey("v", descending=True)))
    expected = table(["g", "v"], [["x", 2], ["x", 1], ["y", 5]])
    assert compare_tables(expected, table(["g", "v"], [["x", 2], ["x", 1], ["y", 5]]), spec).passed
    bad = table(["g", "v"], [["x", 1], ["x", 2], ["y", 5]])
    assert not compare_tables(expected, bad, spec).passed


def test_sorted_ignores_pairs_with_null_keys():
    """NULLの位置（先頭/末尾）はDBやpandasで異なるため、NULLを含む比較は判定しない。"""
    spec = TableSpec(rows="sorted", sort_keys=(SortKey("v"),))
    expected = table(["v"], [[1], [2], [None]], kinds=["integer"])
    actual = table(["v"], [[None], [1], [2]], kinds=["integer"])
    assert compare_tables(expected, actual, spec).passed


# ---------------------------------------------------------------- subset_n（先頭N件ルール）

UNIVERSE = table(COLS, ROWS)


def test_subset_n_accepts_any_n_rows_from_universe():
    spec = TableSpec(rows="subset_n", n=2)
    assert compare_tables(UNIVERSE, table(COLS, ROWS[:2]), spec).passed
    assert compare_tables(UNIVERSE, table(COLS, [ROWS[3], ROWS[1]]), spec).passed


def test_subset_n_rejects_wrong_count():
    spec = TableSpec(rows="subset_n", n=2)
    result = compare_tables(UNIVERSE, table(COLS, ROWS[:3]), spec)
    assert not result.passed
    assert any("2" in r and "3" in r for r in result.reasons)


def test_subset_n_rejects_rows_outside_universe_and_shows_learner_row():
    spec = TableSpec(rows="subset_n", n=2)
    outsider = [20200101, "CS999999999999", 1]
    result = compare_tables(UNIVERSE, table(COLS, [ROWS[0], outsider]), spec)
    assert not result.passed
    assert any("CS999999999999" in r for r in result.reasons)


def test_subset_n_respects_multiplicity():
    spec = TableSpec(rows="subset_n", n=2)
    assert not compare_tables(UNIVERSE, table(COLS, [ROWS[0], ROWS[0]]), spec).passed


def test_subset_n_when_universe_smaller_than_n_requires_all_rows():
    spec = TableSpec(rows="subset_n", n=10)
    assert compare_tables(UNIVERSE, table(COLS, ROWS[::-1]), spec).passed
    assert not compare_tables(UNIVERSE, table(COLS, ROWS[:3]), spec).passed


# ---------------------------------------------------------------- top_n


def test_top_n_accepts_tie_at_boundary():
    spec = TableSpec(rows="top_n", n=2, sort_keys=(SortKey("amount", descending=True),))
    universe = table(["id", "amount"], [["a", 30], ["b", 20], ["c", 20], ["d", 10]])
    assert compare_tables(universe, table(["id", "amount"], [["a", 30], ["b", 20]]), spec).passed
    assert compare_tables(universe, table(["id", "amount"], [["a", 30], ["c", 20]]), spec).passed


def test_top_n_rejects_non_top_rows():
    spec = TableSpec(rows="top_n", n=2, sort_keys=(SortKey("amount", descending=True),))
    universe = table(["id", "amount"], [["a", 30], ["b", 20], ["d", 10]])
    assert not compare_tables(
        universe, table(["id", "amount"], [["a", 30], ["d", 10]]), spec
    ).passed


def test_top_n_rejects_wrong_order():
    spec = TableSpec(rows="top_n", n=2, sort_keys=(SortKey("amount", descending=True),))
    universe = table(["id", "amount"], [["a", 30], ["b", 20], ["d", 10]])
    assert not compare_tables(
        universe, table(["id", "amount"], [["b", 20], ["a", 30]]), spec
    ).passed


# ---------------------------------------------------------------- 採点不能・フィードバック


def test_truncated_result_is_not_gradable():
    result = compare_tables(EXPECTED, table(COLS, ROWS, truncated=True))
    assert not result.passed
    assert not result.gradable


def test_reasons_do_not_leak_expected_values():
    actual = table(COLS, [[1, "X", 1]] * 4)
    result = compare_tables(EXPECTED, actual)
    text = " ".join(result.reasons)
    for row in ROWS:
        assert row[1] not in text


def test_spec_validation():
    with pytest.raises(ValueError):
        TableSpec(rows="subset_n")  # n が必要
    with pytest.raises(ValueError):
        TableSpec(rows="sorted")  # sort_keys が必要
    with pytest.raises(ValueError):
        compare_tables(
            EXPECTED, table(COLS, ROWS), TableSpec(rows="sorted", sort_keys=(SortKey("nope"),))
        )


# ---------------------------------------------------------------- スカラー


@pytest.mark.parametrize(
    ("expected", "actual", "passed"),
    [
        (ScalarResult(10, "integer"), ScalarResult(10, "integer"), True),
        (ScalarResult(10, "integer"), ScalarResult(10.0, "float"), True),
        (ScalarResult(0.3, "float"), ScalarResult(0.1 + 0.2, "float"), True),
        (ScalarResult(10, "integer"), ScalarResult(11, "integer"), False),
        (ScalarResult("13", "string"), ScalarResult(13, "integer"), False),
        (ScalarResult(None, "null"), ScalarResult(None, "null"), True),
    ],
)
def test_compare_scalars(expected, actual, passed):
    assert compare_scalars(expected, actual).passed is passed


# ---------------------------------------------------------------- infer_kind


@pytest.mark.parametrize(
    ("values", "kind"),
    [
        ([1, 2, None], "integer"),
        ([1, 2.5], "float"),
        (["a", None], "string"),
        ([True, False], "boolean"),
        ([None, None], "null"),
        ([], "null"),
        ([{"a": 1}], "other"),
    ],
)
def test_infer_kind(values, kind):
    assert infer_kind(values) == kind
