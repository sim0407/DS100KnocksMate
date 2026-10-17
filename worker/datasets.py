"""公式教材のCSVを、上流Python解答Notebookのセットアップ（CSV分岐）と同じ型で読み込む。

上流: docker/work/answer/ans_preprocess_knock_Python.ipynb 冒頭セル（PG_PORT未設定時の分岐）。
コード値のゼロ埋め（例: category_major_cd "04"）を壊さないよう、該当列は文字列として読む。
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

DATA_DIR_ENV = "KNOCKS_DATA_DIR"
DEFAULT_DATA_DIR = (
    Path(__file__).resolve().parent.parent
    / "upstream"
    / "100knocks-preprocess"
    / "docker"
    / "work"
    / "data"
)

# 公式セットアップと同じ順序・変数名（df_<table>）
TABLES = ("customer", "category", "product", "receipt", "store", "geocode")

# 公式セットアップの dtype 指定をそのまま採用
STRING_COLUMNS = {
    col: str
    for col in (
        "customer_id",
        "gender_cd",
        "postal_cd",
        "application_store_cd",
        "status_cd",
        "category_major_cd",
        "category_medium_cd",
        "category_small_cd",
        "product_cd",
        "store_cd",
        "prefecture_cd",
        "tel_no",
        "street",
    )
}


def data_dir() -> Path:
    return Path(os.environ.get(DATA_DIR_ENV, DEFAULT_DATA_DIR))


def load_tables() -> dict[str, pd.DataFrame]:
    """`{"df_customer": DataFrame, ...}` を公式セットアップと同じ順序で返す。"""
    base = data_dir()
    return {
        f"df_{name}": pd.read_csv(base / f"{name}.csv", encoding="utf-8-sig", dtype=STRING_COLUMNS)
        for name in TABLES
    }
