"""core/exercises/hints.py: 模範解答から作るヒント（使う関数・骨組み）と解答例の表示データ。"""

import pytest

from core.exercises import hints

# ---------------------------------------------------------------- Python


def test_python_functions_in_order_without_duplicates():
    code = (
        'df_receipt.groupby("store_cd").agg({"amount": "sum"}).reset_index()\n'
        'pd.merge(df_a, df_b, on="x").groupby("y").size()'
    )
    assert hints.python_functions(code) == ["groupby", "agg", "reset_index", "pd.merge", "size"]


def test_python_functions_include_builtins_and_query_strings_are_not_functions():
    code = 'len(df_receipt.query("amount > 10"))'
    assert hints.python_functions(code) == ["len", "query"]


def test_python_functions_ignore_unparsable_code():
    assert hints.python_functions("%%sql\nSELECT 1") == []


def test_python_skeleton_masks_literals_and_drops_comments():
    code = (
        "# コード例1\n"
        'df_receipt[["sales_ymd", "amount"]].query(\n'
        "    'customer_id == \"CS018205000001\" & amount >= 1000'  # 条件\n"
        ").head(10)"
    )
    assert hints.python_skeleton(code) == ('df_receipt[["…", "…"]].query(\n    "…"\n).head(…)')


def test_python_skeleton_handles_fstrings():
    assert hints.python_skeleton('x = f"{a}_{b}"\nprint(x)') == 'x = "…"\nprint(x)'


# ---------------------------------------------------------------- SQL


def test_sql_keywords_and_functions():
    code = (
        "SELECT store_cd, SUM(amount) AS amount\n"
        "FROM receipt\n"
        "WHERE customer_id NOT LIKE 'Z%'\n"
        "GROUP BY store_cd\n"
        "HAVING AVG(amount) >= 330\n"
        "ORDER BY amount DESC\n"
        "LIMIT 5;"
    )
    assert hints.sql_keywords(code) == [
        "SUM",
        "WHERE",
        "NOT LIKE",
        "GROUP BY",
        "HAVING",
        "AVG",
        "ORDER BY",
        "DESC",
        "LIMIT",
    ]


def test_sql_skeleton_masks_literals_and_drops_comments():
    code = "-- コード例1\nSELECT * FROM receipt WHERE customer_id = 'CS018205000001' AND amount >= 1000 LIMIT 10;"
    assert hints.sql_skeleton(code) == "SELECT * FROM … WHERE … = '…' AND … >= … LIMIT …;"


def test_sql_skeleton_keeps_functions_and_hides_identifiers():
    code = "SELECT store_cd, SUM(amount) AS amount FROM receipt GROUP BY store_cd"
    assert hints.sql_skeleton(code) == "SELECT …, SUM(…) AS … FROM … GROUP BY …"


# ---------------------------------------------------------------- 解答例の組み立て


def test_build_hints_uses_upstream_answers_with_notes():
    h = hints.build_hints("023", "python")
    assert h.functions[:3] == ["groupby", "agg", "reset_index"]
    assert "…" in h.skeleton
    assert len(h.answers) == 2
    assert h.answers[0].code.startswith("# コード例1")


def test_build_hints_marks_pandas3_incompatible_answers_and_offers_working_example():
    h = hints.build_hints("071", "python")
    assert h.answers[0].broken is True
    assert "pandas 3" in h.answers[0].note
    assert h.working_example  # pandas 3 で動く書き方（採点用の参照コード）
    assert "relativedelta" in h.working_example
    # ヒントは動く書き方から作る
    assert "relativedelta" in h.functions


def test_build_hints_sql_server_file_note():
    h = hints.build_hints("094", "sql")
    assert "STDOUT" in h.answers[0].note


@pytest.mark.parametrize("exercise_id", [f"{i:03d}" for i in range(1, 101)])
def test_every_problem_has_hints(exercise_id):
    for language in ("python", "sql"):
        h = hints.build_hints(exercise_id, language)
        assert h.answers, (exercise_id, language)
        assert h.functions, (exercise_id, language)
        assert h.skeleton.strip(), (exercise_id, language)
