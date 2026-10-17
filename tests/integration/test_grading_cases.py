"""採点定義（exercises/problems/*.toml）の統合テスト: 模範解答・別解は passed、誤答は failed。

実行: docker compose --profile test run --rm --build tests
"""

import os

import pytest

from core.execution.python_runner import run_python
from core.execution.sql_runner import run_sql
from core.exercises.catalog import get_exercise, load_answers
from core.grading.grader import ReferenceCache, grade

WORKER_URL = os.environ.get("KNOCKS_WORKER_URL")
DB_DSN = os.environ.get("KNOCKS_DB_DSN")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (WORKER_URL and DB_DSN), reason="compose の tests サービスで実行"),
]

CACHE = ReferenceCache()


def runner(language):
    if language == "python":
        return lambda code, rows, timeout: run_python(
            code, url=WORKER_URL, max_rows=rows, timeout_sec=timeout
        )
    return lambda code, rows, timeout: run_sql(code, dsn=DB_DSN, max_rows=rows, timeout_sec=timeout)


def grade_code(exercise_id, language, code):
    return grade(get_exercise(exercise_id), language, code, runner(language), CACHE)


COLS4 = '["sales_ymd", "customer_id", "product_cd", "amount"]'

# (問題ID, 言語, 学習者コード, 期待する採点結果)
CASES = [
    # ---- 001 先頭10件（全列）
    ("001", "python", "df_receipt[:10]", "passed"),
    ("001", "python", "df_receipt.iloc[0:10, :]", "passed"),
    ("001", "python", "df_receipt.tail(10)", "passed"),  # 先頭N件ルール: 任意の10行を許容
    ("001", "python", "df_receipt.head(5)", "failed"),
    ("001", "python", "df_receipt", "failed"),
    ("001", "python", 'df_receipt[["sales_ymd"]].head(10)', "failed"),
    ("001", "python", "len(df_receipt)", "failed"),
    ("001", "python", "x = df_receipt.head(10)", "error"),  # 最後が式でない
    ("001", "python", "df_recipt.head(10)", "error"),  # NameError
    ("001", "sql", "select * from receipt limit 10;", "passed"),
    ("001", "sql", "SELECT * FROM receipt ORDER BY amount DESC LIMIT 10", "passed"),
    ("001", "sql", "SELECT * FROM receipt LIMIT 5", "failed"),
    ("001", "sql", "SELECT *, 1 AS x FROM receipt LIMIT 10", "failed"),
    ("001", "sql", "SELECT * FROM reciept LIMIT 10", "error"),
    # ---- 002 列指定（順序あり）10件
    ("002", "python", f"df_receipt.loc[:, {COLS4}].head(10)", "passed"),
    ("002", "python", f"df_receipt.head(10)[{COLS4}]", "passed"),
    (
        "002",
        "python",
        'df_receipt[["customer_id", "sales_ymd", "product_cd", "amount"]].head(10)',
        "failed",
    ),
    ("002", "python", 'df_receipt[["sales_ymd", "customer_id", "product_cd"]].head(10)', "failed"),
    (
        "002",
        "sql",
        "SELECT sales_ymd, customer_id, product_cd, amount FROM receipt LIMIT 10",
        "passed",
    ),
    (
        "002",
        "sql",
        "SELECT customer_id, sales_ymd, product_cd, amount FROM receipt LIMIT 10",
        "failed",
    ),
    # ---- 003 列名変更
    (
        "003",
        "python",
        f'df_receipt[{COLS4}].head(10).rename(columns={{"sales_ymd": "sales_date"}})',
        "passed",
    ),
    ("003", "python", f"df_receipt[{COLS4}].head(10)", "failed"),
    (
        "003",
        "sql",
        'SELECT sales_ymd AS "sales_date", customer_id, product_cd, amount FROM receipt LIMIT 10',
        "passed",
    ),
    (
        "003",
        "sql",
        "SELECT sales_ymd, customer_id, product_cd, amount FROM receipt LIMIT 10",
        "failed",
    ),
    # ---- 004 条件抽出（順序なし）
    (
        "004",
        "python",
        f'df_receipt.loc[df_receipt["customer_id"] == "CS018205000001", {COLS4}]',
        "passed",
    ),
    (
        "004",
        "python",
        f"df_receipt.query(\"customer_id == 'CS018205000001'\")[{COLS4}]"
        '.sort_values("amount").reset_index(drop=True)',
        "passed",
    ),
    (
        "004",
        "python",
        f"df_receipt[{COLS4}].query(\"customer_id == 'CS018205000001'\").head(5)",
        "failed",
    ),
    ("004", "python", f"df_receipt[{COLS4}].query(\"customer_id == 'CS018205000002'\")", "failed"),
    (
        "004",
        "python",
        f'df_receipt[{COLS4}].query("customer_id == \'CS018205000001\'").drop_duplicates("amount")',
        "failed",
    ),
    (
        "004",
        "sql",
        "SELECT sales_ymd, customer_id, product_cd, amount FROM receipt "
        "WHERE customer_id = 'CS018205000001' ORDER BY amount DESC",
        "passed",
    ),
    (
        "004",
        "sql",
        "SELECT DISTINCT sales_ymd, customer_id, product_cd, amount FROM receipt "
        "WHERE customer_id = 'CS018205000001'",
        "passed",  # このデータでは重複行がないため結果は同じ（有限データでの検証の限界）
    ),
    (
        "004",
        "sql",
        "SELECT sales_ymd, customer_id, product_cd, amount FROM receipt WHERE customer_id LIKE 'CS0182%'",
        "failed",
    ),
    # ---- 005 複数条件
    (
        "005",
        "python",
        f'df = df_receipt[{COLS4}]\ndf[(df["customer_id"] == "CS018205000001") & (df["amount"] >= 1000)]',
        "passed",
    ),
    (
        "005",
        "python",
        f"df_receipt[{COLS4}].query(\"customer_id == 'CS018205000001' | amount >= 1000\")",
        "failed",
    ),
    (
        "005",
        "python",
        f"df_receipt[{COLS4}].query(\"customer_id == 'CS018205000001' & amount > 2000\")",
        "failed",
    ),
    (
        "005",
        "sql",
        "SELECT sales_ymd, customer_id, product_cd, amount FROM receipt "
        "WHERE amount >= 1000 AND customer_id = 'CS018205000001'",
        "passed",
    ),
    (
        "005",
        "sql",
        "SELECT sales_ymd, customer_id, product_cd, amount FROM receipt "
        "WHERE customer_id = 'CS018205000001' AND amount <= 1000",
        "failed",
    ),
]


@pytest.mark.parametrize(("exercise_id", "language", "code", "expected"), CASES)
def test_grading_case(exercise_id, language, code, expected):
    result = grade_code(exercise_id, language, code)
    assert result.status == expected, result.feedback


MODEL_ANSWERS = [
    (eid, lang, i, code)
    for eid in ("001", "002", "003", "004", "005")
    for lang in ("python", "sql")
    for i, code in enumerate(load_answers()[eid][lang])
]


@pytest.mark.parametrize(("exercise_id", "language", "index", "code"), MODEL_ANSWERS)
def test_upstream_model_answers_pass(exercise_id, language, index, code):
    result = grade_code(exercise_id, language, code)
    assert result.status == "passed", result.feedback
