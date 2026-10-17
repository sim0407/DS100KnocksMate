"""tools/extract_problems.py のテスト。

前半は人工的な小さいNotebookで境界ケースを、後半は同梱した実物の上流Notebookで全体を検証する。
"""

import json

import pytest

from tools import extract_problems as ep


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "outputs": [], "source": text.splitlines(True)}


# ---------------------------------------------------------------- 問題文の正規化


def test_normalize_statement_strips_rule_quote_and_id():
    raw = "---\n> P-001: レシート明細データ（df_receipt）から先頭10件を表示せよ。"
    assert ep.normalize_statement(raw) == "レシート明細データ（df_receipt）から先頭10件を表示せよ。"


def test_normalize_statement_accepts_fullwidth_colon_and_keeps_bullets():
    raw = "---\n> P-043： 売上サマリを作成せよ。\n>\n> - 条件A\n> - 条件B"
    assert ep.normalize_statement(raw) == "売上サマリを作成せよ。\n\n- 条件A\n- 条件B"


def test_normalize_statement_keeps_inline_code():
    raw = "---\n> P-009: 以下を書き換えよ。\n> \n> `df_store.query('not(a | b)')`"
    assert ep.normalize_statement(raw).endswith("`df_store.query('not(a | b)')`")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\n> P-001: x", ("P", "001")),
        ("---\n> S-100： x", ("S", "100")),
        ("---\n> P-閑話: x", ("P", "閑話")),
        ("TIPS:\n- something P-001: not a header", None),
        ("# これで１００本終わりです。", None),
    ],
)
def test_parse_header(text, expected):
    assert ep.parse_header(text) == expected


# ---------------------------------------------------------------- Notebookの分割


def test_split_notebook_groups_cells_by_problem():
    cells = [
        md("# タイトル"),
        code("import pandas as pd"),  # 冒頭のセットアップ（問題外）
        md("---\n> P-001: 問1"),
        code("df.head(10)"),
        md("---\n> P-002: 問2"),
        code("a = 1"),
        code("a"),
        md("TIPS:\n補足"),
        md("# これで１００本終わりです。おつかれさまでした！"),
    ]
    result = ep.split_notebook(cells, "P")
    assert list(result.problems) == ["001", "002"]
    assert result.problems["001"].statement == "問1"
    assert result.problems["001"].code_cells == ["df.head(10)"]
    assert result.problems["002"].code_cells == ["a = 1", "a"]
    assert result.problems["002"].notes == ["TIPS:\n補足"]
    assert result.setup_cells == ["import pandas as pd"]


def test_split_notebook_puts_interlude_cells_aside():
    cells = [
        md("---\n> P-001: 問1"),
        code("x"),
        md("---\n> P-閑話: 変数を削除する。"),
        code("del x"),
        md("---\n> P-002: 問2"),
        code("y"),
    ]
    result = ep.split_notebook(cells, "P")
    assert result.problems["001"].code_cells == ["x"]
    assert result.interludes == [
        {"after": "001", "statement": "変数を削除する。", "code_cells": ["del x"]}
    ]


def test_split_notebook_drops_empty_code_cells():
    cells = [md("---\n> P-001: 問1"), code(""), code("  \n")]
    assert ep.split_notebook(cells, "P").problems["001"].code_cells == []


def test_split_notebook_rejects_duplicate_ids():
    cells = [md("---\n> P-001: a"), md("---\n> P-001: b")]
    with pytest.raises(ValueError, match="重複"):
        ep.split_notebook(cells, "P")


def test_split_notebook_rejects_wrong_language_prefix():
    with pytest.raises(ValueError, match="接頭辞"):
        ep.split_notebook([md("---\n> S-001: a")], "P")


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("%%sql\n\nSELECT *\nFROM receipt\nLIMIT 10\n;", "SELECT *\nFROM receipt\nLIMIT 10\n;"),
        ("%%sql\nSELECT 1;", "SELECT 1;"),
        ("SELECT 1;", "SELECT 1;"),
    ],
)
def test_strip_sql_magic(cell, expected):
    assert ep.strip_sql_magic(cell) == expected


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("043で作成した売上サマリデータ（df_sales_summary）を使う", ["043"]),
        ("056の抽出結果と性別コード（gender_cd）により", ["056"]),
        ("079で確認した件数だけ減少していることも確認", ["079"]),
        ("レシート明細データから先頭10件", []),
        ("東京（先頭3桁が100〜209のもの）を1", []),
    ],
)
def test_detect_dependencies(statement, expected):
    assert ep.detect_dependencies(statement) == expected


# ---------------------------------------------------------------- 実物の上流Notebook


@pytest.fixture(scope="module")
def catalog():
    return ep.build_catalog()


def test_real_catalog_has_100_contiguous_problems(catalog):
    ids = [p["id"] for p in catalog["problems"]["problems"]]
    assert ids == [f"{i:03d}" for i in range(1, 101)]


def test_real_catalog_every_problem_has_statements_and_answers(catalog):
    answers = {a["id"]: a for a in catalog["answers"]["answers"]}
    for p in catalog["problems"]["problems"]:
        pid = p["id"]
        assert p["python"]["source_id"] == f"P-{pid}"
        assert p["sql"]["source_id"] == f"S-{pid}"
        assert p["python"]["statement"].strip(), pid
        assert p["sql"]["statement"].strip(), pid
        assert answers[pid]["python"]["code_cells"], pid
        assert answers[pid]["sql"]["code_cells"], pid


def test_real_catalog_first_problem_content(catalog):
    p001 = catalog["problems"]["problems"][0]
    assert p001["python"]["statement"].startswith(
        "レシート明細データ（df_receipt）から全項目の先頭10件"
    )
    assert p001["sql"]["statement"].startswith("レシート明細データ（receipt）から全項目の先頭10件")
    a001 = catalog["answers"]["answers"][0]
    assert a001["python"]["code_cells"] == ["df_receipt.head(10)"]
    assert a001["sql"]["code_cells"] == ["SELECT\n    *\nFROM receipt\nLIMIT 10\n;"]


def test_real_catalog_does_not_contain_answers_in_problem_file(catalog):
    text = json.dumps(catalog["problems"], ensure_ascii=False)
    assert "df_receipt.head(10)" not in text


def test_real_catalog_detects_known_dependencies(catalog):
    deps = {p["id"]: p["depends_on"] for p in catalog["problems"]["problems"] if p["depends_on"]}
    assert deps == {
        "044": ["043"],
        "057": ["056"],
        "080": ["079"],
        "086": ["085"],
        "088": ["087"],
        "094": ["093"],
        "095": ["093"],
        "096": ["093"],
        "097": ["094"],
        "098": ["096"],
        "099": ["093"],
        "100": ["099"],
    }


def test_real_catalog_known_upstream_warnings(catalog):
    """上流の既知の不整合（2026-10-17確認）。増減したら上流の変化として要確認。

    - P-003: 解答版は「変更しながら」、設問版は「変更して」（表現差のみ）
    - P-086: 解答版の数式は `+` が欠落。設問版を正とする
    """
    assert catalog["problems"]["warnings"] == [
        "P-003: 設問Notebookと解答Notebookで問題文が異なる",
        "P-086: 設問Notebookと解答Notebookで問題文が異なる",
    ]


def test_real_catalog_interlude_is_kept_out_of_answers(catalog):
    interludes = catalog["answers"]["interludes"]["python"]
    assert [i["after"] for i in interludes] == ["088"]
    answers = {a["id"]: a for a in catalog["answers"]["answers"]}
    assert not any("del df_customer_1" in c for c in answers["088"]["python"]["code_cells"])


def test_generated_files_are_up_to_date(catalog):
    """コミット済みの生成物が、同梱Notebookからの再生成結果と一致すること。"""
    for name, data in catalog.items():
        path = ep.OUTPUT_DIR / f"{name}.json"
        assert path.read_text(encoding="utf-8") == ep.dumps(data), (
            f"{path} が古い。`uv run python -m tools.extract_problems` で再生成すること"
        )
