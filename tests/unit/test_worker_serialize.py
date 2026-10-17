"""worker/serialize.py: Pythonの値をJSON安全な結果表現へ変換するテスト。"""

import datetime as dt
import json
import math

import numpy as np
import pandas as pd
import pytest

from worker.serialize import serialize_value


def roundtrip(value, **kwargs):
    result = serialize_value(value, **kwargs)
    return json.loads(json.dumps(result))  # JSONで往復できること


def test_dataframe_basic():
    df = pd.DataFrame({"code": ["04", "07"], "amount": [158, 81], "price": [1.5, np.nan]})
    r = roundtrip(df)
    assert r == {
        "type": "table",
        "columns": ["code", "amount", "price"],
        "rows": [["04", 158, 1.5], ["07", 81, None]],
        "kinds": ["string", "integer", "float"],
        "row_count": 2,
        "truncated": False,
    }


def test_unnamed_index_is_dropped():
    """query等で残る元の行番号は意味を持たないので比較対象にしない。"""
    df = pd.DataFrame({"a": [1, 2, 3]}).query("a > 1")
    assert roundtrip(df)["columns"] == ["a"]


def test_named_index_becomes_column():
    """groupbyの集計キーはindexに入るため、名前付きindexは列に戻す。"""
    s = (
        pd.DataFrame({"store_cd": ["S1", "S1", "S2"], "amount": [1, 2, 5]})
        .groupby("store_cd")["amount"]
        .sum()
    )
    r = roundtrip(s)
    assert r["columns"] == ["store_cd", "amount"]
    assert r["rows"] == [["S1", 3], ["S2", 5]]


def test_multiindex_columns_are_flattened():
    df = (
        pd.DataFrame({"g": ["a", "a", "b"], "v": [1, 2, 3]}).groupby("g").agg({"v": ["min", "max"]})
    )
    r = roundtrip(df)
    assert r["columns"] == ["g", "v_min", "v_max"]


def test_unnamed_series_gets_value_column():
    r = roundtrip(pd.Series([1, 2]))
    assert r["columns"] == ["value"]
    assert r["rows"] == [[1], [2]]


def test_row_limit_sets_truncated():
    df = pd.DataFrame({"a": range(10)})
    r = roundtrip(df, max_rows=3)
    assert r["rows"] == [[0], [1], [2]]
    assert r["row_count"] == 10
    assert r["truncated"] is True


def test_datetime_column_is_iso_string():
    df = pd.DataFrame({"d": pd.to_datetime(["2019-01-01", None])})
    r = roundtrip(df)
    assert r["kinds"] == ["datetime"]
    assert r["rows"] == [["2019-01-01T00:00:00"], [None]]


def test_object_column_with_timestamps_is_datetime():
    df = pd.DataFrame({"d": [pd.Timestamp("2020-02-03"), None]}, dtype=object)
    r = roundtrip(df)
    assert r["kinds"] == ["datetime"]
    assert r["rows"][0] == ["2020-02-03T00:00:00"]


def test_object_column_with_dates():
    df = pd.DataFrame({"d": [dt.date(2020, 2, 3)]})
    assert roundtrip(df)["rows"] == [["2020-02-03"]]


def test_nullable_integer_and_boolean():
    df = pd.DataFrame(
        {"i": pd.array([1, None], dtype="Int64"), "b": pd.array([True, None], dtype="boolean")}
    )
    r = roundtrip(df)
    assert r["kinds"] == ["integer", "boolean"]
    assert r["rows"] == [[1, True], [None, None]]


def test_category_column_uses_underlying_values():
    df = pd.DataFrame({"c": pd.Categorical(["x", "y", "x"])})
    r = roundtrip(df)
    assert r["kinds"] == ["string"]
    assert r["rows"] == [["x"], ["y"], ["x"]]


def test_numeric_category_column():
    df = pd.DataFrame({"c": pd.cut([1, 15], bins=[0, 10, 20], labels=[0, 10])})
    r = roundtrip(df)
    assert r["kinds"] == ["integer"]


def test_infinite_float_is_kept():
    r = serialize_value(pd.DataFrame({"v": [np.inf]}))
    assert math.isinf(r["rows"][0][0])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (np.int64(5), {"type": "scalar", "value": 5, "kind": "integer"}),
        (np.float64(2.5), {"type": "scalar", "value": 2.5, "kind": "float"}),
        (np.float64("nan"), {"type": "scalar", "value": None, "kind": "null"}),
        (True, {"type": "scalar", "value": True, "kind": "boolean"}),
        ("abc", {"type": "scalar", "value": "abc", "kind": "string"}),
        (
            pd.Timestamp("2020-01-02"),
            {"type": "scalar", "value": "2020-01-02T00:00:00", "kind": "datetime"},
        ),
        (None, {"type": "none"}),
    ],
)
def test_scalars(value, expected):
    assert roundtrip(value) == expected


def test_other_objects_become_capped_text():
    r = roundtrip(list(range(100000)), max_text_chars=50)
    assert r["type"] == "text"
    assert len(r["text"]) <= 50 + len("…（省略）")
    assert r["truncated"] is True


def test_duplicate_column_names_are_kept_as_strings():
    df = pd.DataFrame([[1, 2]], columns=["a", "a"])
    assert roundtrip(df)["columns"] == ["a", "a"]


def test_index_name_colliding_with_column_is_dropped_safely():
    df = pd.DataFrame({"a": [1, 2]}).set_index(pd.Index([5, 6], name="a"))
    r = roundtrip(df)
    assert r["columns"] == ["a"]
    assert r["rows"] == [[1], [2]]
