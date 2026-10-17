"""app/display.py: 結果の表示用変換。"""

import pandas as pd

from app.display import row_summary, to_dataframe, unique_columns


def result(columns, rows, kinds, row_count=None, truncated=False):
    return {
        "columns": columns,
        "rows": rows,
        "kinds": kinds,
        "row_count": row_count if row_count is not None else len(rows),
        "truncated": truncated,
    }


def test_unique_columns():
    assert unique_columns(["a", "b", "a", "a"]) == ["a", "b", "a (2)", "a (3)"]


def test_to_dataframe_basic_and_zero_padding():
    df = to_dataframe(result(["cd", "n"], [["04", 1], ["07", 2]], ["string", "integer"]))
    assert list(df.columns) == ["cd", "n"]
    assert df["cd"].tolist() == ["04", "07"]


def test_integer_with_null_is_nullable_int():
    df = to_dataframe(result(["n"], [[1], [None]], ["integer"]))
    assert str(df["n"].dtype) == "Int64"
    assert df["n"].iloc[0] == 1


def test_zero_rows_keep_columns():
    df = to_dataframe(result(["a", "b"], [], ["string", "integer"]))
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 0


def test_duplicate_columns_are_renamed_for_display():
    df = to_dataframe(result(["a", "a"], [[1, 2]], ["integer", "integer"]))
    assert list(df.columns) == ["a", "a (2)"]


def test_other_kind_is_stringified():
    df = to_dataframe(result(["x"], [["[1, 2]"], [None]], ["other"]))
    assert df["x"].iloc[0] == "[1, 2]"
    assert pd.isna(df["x"].iloc[1])


def test_row_summary():
    assert row_summary(result(["a"], [[1]], ["integer"]), 1) == "1行 × 1列"
    big = result(["a"], [[1]] * 200, ["integer"], row_count=104681, truncated=True)
    assert row_summary(big, 200) == "104,681行 × 1列（先頭200行を表示）"
