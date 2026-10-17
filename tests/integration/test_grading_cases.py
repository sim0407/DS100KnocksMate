"""採点定義（exercises/problems/*.toml）の統合テスト: 模範解答・別解は passed、誤答は failed。

実行: docker compose --profile test run --rm --build tests
"""

import os

import pytest

from core.execution.python_runner import run_python
from core.execution.sql_runner import run_sql
from core.exercises.catalog import get_exercise, load_answers, load_exercises
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
    # ---- Phase 2 拡大: 別の参照（alternatives）で許容するもの
    (
        "030",
        "python",
        'df_receipt.groupby("store_cd").amount.var().sort_values(ascending=False).head(5)',
        "passed",
    ),
    (
        "030",
        "python",
        'df_receipt.groupby("store_cd").amount.std().sort_values(ascending=False).head(5)',
        "failed",
    ),
    (
        "030",
        "sql",
        "SELECT store_cd, VARIANCE(amount) FROM receipt GROUP BY store_cd ORDER BY 2 DESC LIMIT 5",
        "passed",
    ),
    (
        "031",
        "sql",
        "SELECT store_cd, STDDEV(amount) FROM receipt GROUP BY store_cd ORDER BY 2 DESC LIMIT 5",
        "passed",
    ),
    (
        "054",
        "python",
        'df = df_customer[["customer_id", "address"]].copy()\n'
        'df["cd"] = df["address"].str[:3].map({"埼玉県": 11, "千葉県": 12, "東京都": 13, "神奈川": 14})\n'
        "df.head(10)",
        "passed",  # 数値のコードも許容
    ),
    (
        "054",
        "python",
        'df = df_customer[["customer_id", "address"]].copy()\n'
        'df["cd"] = df["address"].str[:3].map({"埼玉県": 12, "千葉県": 11, "東京都": 13, "神奈川": 14})\n'
        "df.head(10)",
        "failed",
    ),
    (
        "061",
        "python",
        'df = df_receipt[~df_receipt.customer_id.str.startswith("Z")].groupby("customer_id", as_index=False).amount.sum()\n'
        'df["log"] = np.log10(df["amount"])\n'
        "df.head(10)",
        "passed",  # +0.5 なし
    ),
    (
        "061",
        "python",
        'df = df_receipt[~df_receipt.customer_id.str.startswith("Z")].groupby("customer_id", as_index=False).amount.sum()\n'
        'df["log"] = np.log(df["amount"])\n'
        "df.head(10)",
        "failed",  # 底が違う
    ),
    ("063", "sql", "SELECT *, unit_price - unit_cost FROM product LIMIT 10", "passed"),
    ("063", "sql", "SELECT product_cd, unit_price - unit_cost FROM product LIMIT 10", "failed"),
    # ---- 日付型（深夜0時の日時と日付を同じとみなす）
    (
        "046",
        "python",
        'df = df_customer[["customer_id"]].copy()\n'
        'df["d"] = pd.to_datetime(df_customer["application_date"]).dt.date\n'
        "df.head(10)",
        "passed",
    ),
    (
        "046",
        "python",
        'df_customer[["customer_id", "application_date"]].head(10)',
        "failed",  # 文字列のまま
    ),
    (
        "046",
        "sql",
        "SELECT customer_id, CAST(application_date AS DATE) FROM customer LIMIT 10",
        "passed",
    ),
    ("046", "sql", "SELECT customer_id, application_date FROM customer LIMIT 10", "failed"),
    (
        "048",
        "sql",
        "SELECT receipt_no, receipt_sub_no, TO_TIMESTAMP(sales_epoch) FROM receipt LIMIT 10",
        "passed",
    ),
    # ---- 値・Series
    ("040", "python", "len(df_store) * len(df_product)", "passed"),
    ("064", "sql", "SELECT AVG(1 - unit_cost * 1.0 / unit_price) FROM product", "passed"),
    ("079", "python", "df_product.isna().sum()", "passed"),
    ("079", "python", "df_product.isna().sum().sort_values()", "passed"),
    ("079", "python", "df_product.notna().sum()", "failed"),
    # ---- 006 OR を含む複合条件
    (
        "006",
        "python",
        'df = df_receipt[["sales_ymd", "customer_id", "product_cd", "quantity", "amount"]]\n'
        'df[(df.customer_id == "CS018205000001") & ((df.amount >= 1000) | (df.quantity >= 5))]',
        "passed",
    ),
    (
        "006",
        "python",
        'df_receipt[["sales_ymd", "customer_id", "product_cd", "quantity", "amount"]]'
        """.query('customer_id == "CS018205000001" & amount >= 1000 & quantity >= 5')""",
        "failed",
    ),
    (
        "006",
        "sql",
        "SELECT sales_ymd, customer_id, product_cd, quantity, amount FROM receipt "
        "WHERE customer_id = 'CS018205000001' AND amount >= 1000 OR quantity >= 5",
        "failed",  # 括弧の付け忘れ
    ),
    # ---- 007 範囲
    (
        "007",
        "python",
        f"df_receipt[{COLS4}]"
        """.query('customer_id == "CS018205000001" & amount.between(1000, 2000)')""",
        "passed",
    ),
    (
        "007",
        "python",
        f"df_receipt[{COLS4}]" """.query('customer_id == "CS018205000001" & amount >= 1000')""",
        "failed",
    ),
    (
        "007",
        "sql",
        "SELECT sales_ymd, customer_id, product_cd, amount FROM receipt "
        "WHERE customer_id = 'CS018205000001' AND amount >= 1000 AND amount <= 2000",
        "passed",
    ),
    # ---- 008 否定
    (
        "008",
        "python",
        f"df = df_receipt[{COLS4}]\n"
        'df[(df.customer_id == "CS018205000001") & ~(df.product_cd == "P071401019")]',
        "passed",
    ),
    (
        "008",
        "python",
        f"df_receipt[{COLS4}]"
        """.query('customer_id == "CS018205000001" & product_cd == "P071401019"')""",
        "failed",
    ),
    (
        "008",
        "sql",
        "SELECT sales_ymd, customer_id, product_cd, amount FROM receipt "
        "WHERE customer_id = 'CS018205000001' AND product_cd <> 'P071401019'",
        "passed",
    ),
    # ---- 009 ド・モルガン（結果のみで判定。元のORの式でも正解になるのは既知の限界）
    ("009", "python", """df_store.query('prefecture_cd != "13" & floor_area <= 900')""", "passed"),
    (
        "009",
        "python",
        """df_store.query('not(prefecture_cd == "13" | floor_area > 900)')""",
        "passed",
    ),
    ("009", "python", """df_store.query('prefecture_cd != "13" | floor_area <= 900')""", "failed"),
    (
        "009",
        "sql",
        "SELECT * FROM store WHERE NOT prefecture_cd = '13' AND NOT floor_area > 900",
        "passed",
    ),
    (
        "009",
        "sql",
        "SELECT * FROM store WHERE prefecture_cd <> '13' OR floor_area <= 900",
        "failed",
    ),
    # ---- 010 前方一致 10件
    ("010", "python", 'df_store[df_store["store_cd"].str.startswith("S14")].head(10)', "passed"),
    ("010", "python", 'df_store[df_store["store_cd"].str.startswith("S13")].head(10)', "failed"),
    (
        "010",
        "sql",
        "SELECT * FROM store WHERE store_cd LIKE 'S14%' ORDER BY store_cd DESC LIMIT 10",
        "passed",
    ),
    ("010", "sql", "SELECT * FROM store WHERE store_cd LIKE '%14%' LIMIT 10", "failed"),
    # ---- 017 / 018 ソートして先頭10件（上位N件）
    ("017", "python", 'df_customer.sort_values(["birth_day", "customer_id"]).head(10)', "passed"),
    ("017", "python", 'df_customer.sort_values("birth_day", ascending=False).head(10)', "failed"),
    ("017", "python", "df_customer.head(10)", "failed"),
    (
        "017",
        "sql",
        "SELECT * FROM customer ORDER BY birth_day, customer_id DESC LIMIT 10",
        "passed",
    ),
    ("017", "sql", "SELECT * FROM customer LIMIT 10", "failed"),
    ("018", "python", 'df_customer.sort_values("birth_day", ascending=False).head(10)', "passed"),
    ("018", "python", 'df_customer.sort_values("birth_day").head(10)', "failed"),
    ("018", "sql", "SELECT * FROM customer ORDER BY birth_day DESC NULLS LAST LIMIT 10", "passed"),
    # ---- 019 同順位ありのランク（順位の値も検証）
    (
        "019",
        "python",
        'df_receipt[["customer_id", "amount"]].assign(\n'
        '    rank=df_receipt["amount"].rank(method="min", ascending=False).astype(int)\n'
        ').sort_values("rank").head(10)',
        "passed",
    ),
    (
        "019",
        "python",
        'df_receipt[["customer_id", "amount"]].assign(\n'
        '    rank=df_receipt["amount"].rank(method="min")\n'
        ').sort_values("amount", ascending=False).head(10)',
        "failed",  # 順位の向きが逆
    ),
    (
        "019",
        "sql",
        "SELECT customer_id, amount, RANK() OVER (ORDER BY amount DESC) AS r "
        "FROM receipt ORDER BY r LIMIT 10",
        "passed",
    ),
    (
        "019",
        "sql",
        "SELECT customer_id, amount, RANK() OVER (ORDER BY amount) AS r "
        "FROM receipt ORDER BY amount DESC LIMIT 10",
        "failed",  # 順位の向きが逆
    ),
    # ---- 020 / 029 自動採点しない問題（passed にしない）
    ("020", "python", "df_receipt.head(10)", "manual_review"),
    ("029", "sql", "SELECT 1", "manual_review"),
    # ---- 021 / 022 件数（値）
    ("021", "python", "df_receipt.shape[0]", "passed"),
    ("021", "python", "len(df_receipt.index)", "passed"),
    ("021", "python", "df_receipt.size", "failed"),  # セル数
    ("021", "sql", "SELECT COUNT(*) AS n FROM receipt", "passed"),
    ("021", "sql", "SELECT COUNT(DISTINCT customer_id) FROM receipt", "failed"),
    ("021", "sql", "SELECT COUNT(*), 1 FROM receipt", "failed"),
    ("022", "python", 'len(df_receipt["customer_id"].unique())', "passed"),
    ("022", "python", 'df_receipt["customer_id"].drop_duplicates().shape[0]', "passed"),
    ("022", "python", 'df_receipt["customer_id"].count()', "failed"),
    ("022", "sql", "SELECT COUNT(*) FROM (SELECT DISTINCT customer_id FROM receipt) t", "passed"),
    # ---- 023 グループ集計（列名は位置で照合）
    ("023", "python", 'df_receipt.groupby("store_cd")[["amount", "quantity"]].sum()', "passed"),
    (
        "023",
        "python",
        'df_receipt.groupby("store_cd", as_index=False)[["amount", "quantity"]].sum()',
        "passed",
    ),
    ("023", "python", 'df_receipt.groupby("store_cd")[["quantity", "amount"]].sum()', "failed"),
    ("023", "python", 'df_receipt.groupby("store_cd")[["amount", "quantity"]].mean()', "failed"),
    (
        "023",
        "sql",
        "SELECT store_cd, SUM(amount), SUM(quantity) FROM receipt GROUP BY store_cd",
        "passed",
    ),
    (
        "023",
        "sql",
        "SELECT store_cd, SUM(amount), SUM(quantity) FROM receipt GROUP BY store_cd LIMIT 10",
        "failed",
    ),
    # ---- 027 平均の上位5件（小数を含む）
    (
        "027",
        "python",
        'df_receipt.groupby("store_cd")["amount"].mean().sort_values(ascending=False).head(5)',
        "passed",
    ),
    (
        "027",
        "python",
        'df_receipt.groupby("store_cd")["amount"].mean().sort_values().head(5)',
        "failed",
    ),
    (
        "027",
        "python",
        'df_receipt.groupby("store_cd")["amount"].median().sort_values(ascending=False).head(5)',
        "failed",
    ),
    (
        "027",
        "sql",
        "SELECT store_cd, AVG(amount) FROM receipt GROUP BY store_cd ORDER BY 2 DESC LIMIT 5",
        "passed",
    ),
    (
        "027",
        "sql",
        "SELECT store_cd, ROUND(AVG(amount), 1) FROM receipt GROUP BY store_cd ORDER BY 2 DESC LIMIT 5",
        "failed",  # 丸めると値が変わる
    ),
]


@pytest.mark.parametrize(("exercise_id", "language", "code", "expected"), CASES)
def test_grading_case(exercise_id, language, code, expected):
    result = grade_code(exercise_id, language, code)
    assert result.status == expected, result.feedback


AUTO_GRADED = [
    (e.id, lang)
    for e in load_exercises()
    for lang in ("python", "sql")
    if e.grading[lang].strategy != "manual_review"
]
# 上流の解答セルのうち、単独では完全な解答にならないもの（理由つきで対象外）
NOT_STANDALONE_ANSWERS = {
    ("055", "python", 1): "確認用コード（前のセルの変数を表示するだけ）",
    ("055", "python", 2): "コード例2（前のセルで作った変数を使う）",
    ("055", "python", 3): "参考コード（上流Notebookが「題意を満たさない」と明記）",
    (
        "069",
        "python",
        1,
    ): "参考コード（全カテゴリの列を含む横持ち。画面の採点基準で4列構成を求めている）",
}
MODEL_ANSWERS = [
    (eid, lang, i, code)
    for eid, lang in AUTO_GRADED
    for i, code in enumerate(load_answers()[eid][lang])
    if (eid, lang, i) not in NOT_STANDALONE_ANSWERS
]


@pytest.mark.parametrize(("exercise_id", "language", "index", "code"), MODEL_ANSWERS)
def test_upstream_model_answers_pass(exercise_id, language, index, code):
    result = grade_code(exercise_id, language, code)
    assert result.status == "passed", result.feedback
