"""worker/datasets.py: 公式教材CSVを公式セットアップと同じ型で読み込めることを検証する。"""

import pandas as pd
import pytest

from worker import datasets


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return datasets.load_tables()


def test_variable_names_match_official_setup(tables):
    assert list(tables) == [
        "df_customer",
        "df_category",
        "df_product",
        "df_receipt",
        "df_store",
        "df_geocode",
    ]


@pytest.mark.parametrize(
    ("name", "shape"),
    [
        ("df_customer", (21971, 11)),
        ("df_category", (228, 6)),
        ("df_product", (10030, 6)),
        ("df_receipt", (104681, 9)),
        ("df_store", (53, 10)),
        ("df_geocode", (127252, 9)),
    ],
)
def test_shapes(tables, name, shape):
    assert tables[name].shape == shape


def test_code_columns_are_strings_with_zero_padding_kept(tables):
    for name in ("df_category", "df_product"):
        df = tables[name]
        for col, width in [
            ("category_major_cd", 2),
            ("category_medium_cd", 4),
            ("category_small_cd", 6),
        ]:
            assert pd.api.types.is_string_dtype(df[col]), (name, col)
            assert df[col].str.len().eq(width).all(), (name, col)
    assert tables["df_category"]["category_major_cd"].iloc[0] == "04"
    assert tables["df_store"]["tel_no"].str.startswith("0").all()
    assert tables["df_geocode"]["postal_cd"].str.fullmatch(r"\d{3}-\d{4}").all()
    assert set(tables["df_customer"]["gender_cd"].unique()) == {"0", "1", "9"}
    # 問題文どおり application_date は YYYYMMDD 形式の文字列（上流CSV分岐との意図的な差分）
    application_date = tables["df_customer"]["application_date"]
    assert pd.api.types.is_string_dtype(application_date)
    assert application_date.str.fullmatch(r"\d{8}").all()


def test_numeric_columns(tables):
    receipt = tables["df_receipt"]
    for col in ("sales_ymd", "sales_epoch", "receipt_no", "receipt_sub_no", "quantity", "amount"):
        assert receipt[col].dtype == "int64", col
    assert tables["df_product"]["unit_price"].dtype == "float64"  # 欠損を含むためfloat


def test_missing_values_are_preserved(tables):
    product = tables["df_product"]
    assert product["unit_price"].isna().sum() == 7
    assert product["unit_cost"].isna().sum() == 7
    assert tables["df_geocode"]["town"].isna().sum() == 1954


def test_row_order_follows_csv(tables):
    """「先頭10件」の問題はCSVの行順に依存するため、行順を保つこと。"""
    first = tables["df_receipt"].iloc[0]
    assert (first["sales_ymd"], first["store_cd"], first["receipt_no"]) == (20181103, "S14006", 112)
    assert tables["df_receipt"].index.equals(pd.RangeIndex(104681))


def test_data_dir_can_be_overridden(tmp_path, monkeypatch):
    for name in datasets.TABLES:
        (tmp_path / f"{name}.csv").write_text(
            "category_major_cd,x\n01,1\n" if name == "category" else "a\n1\n",
            encoding="utf-8-sig",
        )
    monkeypatch.setenv(datasets.DATA_DIR_ENV, str(tmp_path))
    loaded = datasets.load_tables()
    assert loaded["df_category"]["category_major_cd"].iloc[0] == "01"
