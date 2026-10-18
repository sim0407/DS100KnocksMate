"""core/grading/files.py（出力ファイルの比較）と core/grading/validators.py（性質による採点）。"""

from core.execution.results import TableResult
from core.grading.files import FileFormat, compare_files
from core.grading.validators import VALIDATORS

CSV = FileFormat(delimiter=",", header=True, encoding="utf-8")
EXPECTED = b"product_cd,category_major_cd,unit_price\nP001,04,198.0\nP002,07,\n"


def test_same_file_passes():
    assert compare_files(EXPECTED, EXPECTED, CSV).passed


def test_row_order_and_numeric_formatting_do_not_matter():
    actual = b"product_cd,category_major_cd,unit_price\nP002,07,\nP001,04,198\n"
    assert compare_files(EXPECTED, actual, CSV).passed


def test_bom_is_allowed_for_utf8():
    assert compare_files(EXPECTED, b"\xef\xbb\xbf" + EXPECTED, CSV).passed


def test_zero_padded_code_must_be_kept():
    actual = b"product_cd,category_major_cd,unit_price\nP001,4,198.0\nP002,7,\n"
    result = compare_files(EXPECTED, actual, CSV)
    assert not result.passed


def test_index_column_is_extra():
    actual = b",product_cd,category_major_cd,unit_price\n0,P001,04,198.0\n1,P002,07,\n"
    result = compare_files(EXPECTED, actual, CSV)
    assert not result.passed
    assert any("ヘッダ" in r for r in result.reasons)


def test_missing_header_fails():
    actual = b"P001,04,198.0\nP002,07,\n"
    assert not compare_files(EXPECTED, actual, CSV).passed


def test_no_header_format():
    fmt = FileFormat(delimiter=",", header=False, encoding="utf-8")
    expected = b"P001,04,198.0\n"
    assert compare_files(expected, expected, fmt).passed
    assert not compare_files(expected, b"a,b,c\nP001,04,198.0\n", fmt).passed


def test_wrong_delimiter_hint():
    tsv = FileFormat(delimiter="\t", header=True, encoding="utf-8")
    expected = b"a\tb\n1\t2\n"
    result = compare_files(expected, b"a,b\n1,2\n", tsv)
    assert not result.passed
    assert any("区切り" in r for r in result.reasons)


def test_encoding_mismatch():
    fmt = FileFormat(delimiter=",", header=True, encoding="cp932")
    expected = "name\n惣菜\n".encode("cp932")
    assert compare_files(expected, expected, fmt).passed
    result = compare_files(expected, "name\n惣菜\n".encode(), fmt)
    assert not result.passed
    assert any("文字コード" in r for r in result.reasons)


# ---------------------------------------------------------------- validators


def table(columns, rows):
    return TableResult(
        columns=columns, rows=rows, kinds=["string"] * len(columns), row_count=len(rows)
    )


UNIVERSE = table(["customer_id", "x"], [[f"C{i:03d}", "v"] for i in range(10)])


def test_unparsable_learner_csv_is_failure_not_exception():
    """標準の csv の項目サイズ上限（131072文字）を超えるファイルでも例外にしない。"""
    actual = b"product_cd,category_major_cd,unit_price\nP001," + b"x" * 140_000 + b",198\n"
    result = compare_files(EXPECTED, actual, CSV)
    assert not result.passed
    assert result.gradable
    assert "CSVとして読み取れません" in result.reasons[0]


def test_unparsable_expected_csv_is_not_gradable():
    expected = b"a,b\n1," + b"x" * 140_000 + b"\n"
    result = compare_files(expected, b"a,b\n1,2\n", CSV)
    assert not result.passed
    assert not result.gradable


def test_train_test_split_ok():
    train = table(["customer_id", "x"], UNIVERSE.rows[:8])
    test = table(["customer_id", "x"], UNIVERSE.rows[8:])
    result = VALIDATORS["train_test_split"](
        {"train": train, "test": test}, UNIVERSE, {"test_ratio": 0.2}
    )
    assert result.passed, result.reasons


def test_train_test_split_detects_overlap_missing_and_ratio():
    v = VALIDATORS["train_test_split"]
    overlap = {
        "train": table(["customer_id", "x"], UNIVERSE.rows[:8]),
        "test": table(["customer_id", "x"], UNIVERSE.rows[7:]),
    }
    assert not v(overlap, UNIVERSE, {"test_ratio": 0.2}).passed
    missing = {
        "train": table(["customer_id", "x"], UNIVERSE.rows[:7]),
        "test": table(["customer_id", "x"], UNIVERSE.rows[8:]),
    }
    assert not v(missing, UNIVERSE, {"test_ratio": 0.2}).passed
    ratio = {
        "train": table(["customer_id", "x"], UNIVERSE.rows[:5]),
        "test": table(["customer_id", "x"], UNIVERSE.rows[5:]),
    }
    result = v(ratio, UNIVERSE, {"test_ratio": 0.2})
    assert not result.passed
    assert any("割合" in r for r in result.reasons)


def test_undersampling():
    universe = TableResult(
        columns=["customer_id", "is_buy"],
        rows=[["A", 1], ["B", 1], ["C", 0], ["D", 0], ["E", 0]],
        kinds=["string", "integer"],
        row_count=5,
    )
    v = VALIDATORS["undersampling"]
    ok = table(["customer_id", "name"], [["A", "a"], ["B", "b"], ["C", "c"], ["E", "e"]])
    assert v({"sample": ok}, universe, {}).passed
    unbalanced = table(["customer_id", "name"], [["A", "a"], ["B", "b"], ["C", "c"]])
    assert not v({"sample": unbalanced}, universe, {}).passed
    dropped_minority = table(["customer_id", "name"], [["A", "a"], ["C", "c"]])
    assert not v({"sample": dropped_minority}, universe, {}).passed
    no_id = table(["id", "name"], [["A", "a"]])
    assert not v({"sample": no_id}, universe, {}).passed
