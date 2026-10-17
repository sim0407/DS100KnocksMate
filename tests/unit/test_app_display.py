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


def test_file_preview_utf8_and_cp932():
    from app.display import file_preview

    label, text = file_preview("a,b\n惣菜,1\n".encode())
    assert label == "UTF-8"
    assert text.splitlines()[1] == "惣菜,1"
    label, text = file_preview("a,b\n惣菜,1\n".encode("cp932"))
    assert label == "CP932（Shift_JIS）"
    assert "惣菜" in text


def test_file_preview_limits_lines_and_marks_bom():
    from app.display import file_preview

    data = b"\xef\xbb\xbf" + "\n".join(str(i) for i in range(100)).encode()
    label, text = file_preview(data, max_lines=5)
    assert label == "UTF-8（BOM付き）"
    assert text.splitlines() == ["0", "1", "2", "3", "4", "…"]


def test_file_label():
    from app.display import file_label

    assert file_label("data/out.csv") == "data/out.csv"
    assert file_label("COPY_TO_STDOUT_2") == "COPY ... TO STDOUT の出力（2）"
