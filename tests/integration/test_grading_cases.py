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
        return lambda code, rows, timeout, options: run_python(
            code,
            url=WORKER_URL,
            max_rows=rows,
            timeout_sec=timeout,
            setup=options.setup,
            collect_files=options.collect_files,
            artifacts=options.artifacts,
        )
    return lambda code, rows, timeout, options: run_sql(
        code,
        dsn=DB_DSN,
        max_rows=rows,
        timeout_sec=timeout,
        writable=options.writable,
        setup=options.setup,
        stdin_query=options.stdin_query,
        artifacts=options.artifacts,
    )


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
    # ---- Phase 3: 作成したデータ（artifact）
    ("080", "python", "df_product_1 = df_product.dropna(how='any')", "passed"),
    ("080", "python", "df_product_1 = df_product.copy()", "failed"),
    ("080", "python", "df_x = df_product.dropna()", "failed"),  # 指定の変数名がない
    (
        "080",
        "sql",
        "CREATE TABLE product_1 AS SELECT * FROM product WHERE unit_price IS NOT NULL AND unit_cost IS NOT NULL;\n"
        "SELECT COUNT(*) FROM product_1;",
        "passed",
    ),
    ("080", "sql", "CREATE TABLE product_1 AS SELECT * FROM product;", "failed"),
    (
        "080",
        "sql",
        "SELECT * FROM product WHERE unit_price IS NOT NULL",
        "failed",
    ),  # テーブルを作っていない
    (
        "043",
        "python",
        'df = df_receipt.merge(df_customer, on="customer_id")\n'
        'df["era"] = df["age"] // 10 * 10\n'
        'df_sales_summary = df.pivot_table(index="era", columns="gender_cd", values="amount", aggfunc="sum", fill_value=0)'
        '[["1", "0", "9"]].reset_index()',
        "passed",  # 女性・男性・不明の順、欠損は0
    ),
    (
        "043",
        "python",
        'df = df_receipt.merge(df_customer, on="customer_id")\n'
        'df["era"] = df["age"] // 10 * 10\n'
        'df_sales_summary = df.pivot_table(index="era", columns="gender_cd", values="amount", aggfunc="mean").reset_index()',
        "failed",  # 合計ではなく平均
    ),
    (
        "044",
        "python",
        'df_sales_summary.melt(id_vars="era").replace({"male": "00", "female": "01", "unknown": "99"})',
        "passed",
    ),
    ("044", "python", 'df_sales_summary.melt(id_vars="era")', "failed"),  # コード値に変換していない
    # ---- 前提データ・書き込み可能モード
    (
        "086",
        "sql",
        "SELECT c.customer_id, c.address, s.address,\n"
        "  6371 * ACOS(SIN(RADIANS(c.m_latitude)) * SIN(RADIANS(s.latitude)) + COS(RADIANS(c.m_latitude)) * COS(RADIANS(s.latitude)) * COS(RADIANS(c.m_longitude - s.longitude)))\n"
        "FROM customer_1 c JOIN store s ON c.application_store_cd = s.store_cd LIMIT 10",
        "passed",
    ),
    # ---- ファイル出力
    ("094", "python", 'df_product_full.to_csv("./data/out.csv", index=False)', "passed"),
    (
        "094",
        "python",
        'df_product_full.to_csv("../data/out.csv", index=False, encoding="utf_8_sig")',
        "passed",
    ),
    ("094", "python", 'df_product_full.to_csv("data/out.csv")', "failed"),  # インデックスを出力
    (
        "094",
        "python",
        'df_product_full.to_csv("data/out.csv", index=False, encoding="cp932")',
        "failed",
    ),
    ("094", "python", 'df_product_full.to_csv("out.csv", index=False)', "failed"),  # 出力先が違う
    ("094", "sql", "COPY product_full TO STDOUT WITH (FORMAT csv, HEADER true)", "passed"),
    ("094", "sql", "COPY product_full TO STDOUT WITH CSV", "failed"),  # ヘッダなし
    (
        "095",
        "python",
        'df_product_full.to_csv("data/out.csv", index=False, encoding="shift_jis", errors="replace")',
        "passed",
    ),
    ("095", "python", 'df_product_full.to_csv("data/out.csv", index=False)', "failed"),  # UTF-8
    (
        "096",
        "python",
        'df_product_full.to_csv("data/out.csv", index=False, header=False)',
        "passed",
    ),
    ("099", "python", 'df_product_full.to_csv("data/out.tsv", index=False, sep="\\t")', "passed"),
    (
        "099",
        "python",
        'df_product_full.to_csv("data/out.tsv", index=False)',
        "failed",
    ),  # カンマ区切り
    # ---- ファイル読み込み
    (
        "097",
        "python",
        'pd.read_csv("../data/P_df_product_full_UTF-8_header.csv", dtype={"category_major_cd": str, "category_medium_cd": str, "category_small_cd": str}).head(3)',
        "passed",
    ),
    (
        "097",
        "python",
        'pd.read_csv("data/P_df_product_full_UTF-8_header.csv").head(3)',
        "failed",
    ),  # ゼロ埋めが消える
    (
        "097",
        "python",
        "df_product_full.head(3)",
        "error",
    ),  # 用意済みのファイルを読む問題（変数は消してある）
    (
        "097",
        "sql",
        "CREATE TABLE product_full (product_cd VARCHAR(10), category_major_cd VARCHAR(2), category_major_name VARCHAR(20),\n"
        "  category_medium_cd VARCHAR(4), category_medium_name VARCHAR(20), category_small_cd VARCHAR(6),\n"
        "  category_small_name VARCHAR(20), unit_price INTEGER, unit_cost INTEGER);\n"
        "COPY product_full FROM STDIN WITH CSV HEADER;\n"
        "SELECT * FROM product_full LIMIT 3;",
        "passed",
    ),
    (
        "098",
        "python",
        'df = pd.read_csv("data/P_df_product_full_UTF-8_noh.csv", header=None, dtype=str)\n'
        "df[[4, 5]] = df[[4, 5]].astype(float)\n"
        "df.head(3)",
        "passed",
    ),
    # ---- 性質による採点（乱数）
    (
        "089",
        "python",
        'ids = df_receipt.groupby("customer_id").amount.sum().loc[lambda s: s > 0].index\n'
        "df_all = df_customer[df_customer.customer_id.isin(ids)]\n"
        "df_train, df_test = train_test_split(df_all, test_size=0.2, random_state=0)",
        "passed",
    ),
    (
        "089",
        "python",
        'ids = df_receipt.groupby("customer_id").amount.sum().loc[lambda s: s > 0].index\n'
        "df_all = df_customer[df_customer.customer_id.isin(ids)]\n"
        "df_train, df_test = train_test_split(df_all, test_size=0.5, random_state=0)",
        "failed",
    ),
    (
        "089",
        "python",
        'ids = df_receipt.groupby("customer_id").amount.sum().loc[lambda s: s > 0].index\n'
        "df_all = df_customer[df_customer.customer_id.isin(ids)]\n"
        "df_train, df_test = train_test_split(df_all, test_size=0.2)",
        "passed",  # 乱数のシードを固定しなくても正解（1回の実行から両方を取り出す）
    ),
    (
        "089",
        "sql",
        "CREATE TABLE sales_customer AS SELECT * FROM customer WHERE customer_id IN\n"
        "  (SELECT customer_id FROM receipt GROUP BY customer_id HAVING SUM(amount) > 0);\n"
        "CREATE TABLE customer_test AS SELECT * FROM sales_customer ORDER BY random()\n"
        "  LIMIT (SELECT ROUND(COUNT(*) * 0.2) FROM sales_customer);\n"
        "CREATE TABLE customer_train AS SELECT * FROM sales_customer EXCEPT SELECT * FROM customer_test;",
        "passed",  # setseed なしでも正解
    ),
    (
        "089",
        "sql",
        "CREATE TABLE customer_train AS SELECT * FROM customer LIMIT 10;",
        "failed",  # customer_test がない
    ),
    (
        "091",
        "python",
        "buy = df_customer.customer_id.isin(df_receipt.customer_id)\n"
        "df_down_sampling = pd.concat([df_customer[buy], df_customer[~buy].sample(int(buy.sum()), random_state=1)])",
        "passed",
    ),
    (
        "091",
        "python",
        "buy = df_customer.customer_id.isin(df_receipt.customer_id)\n"
        "df_down_sampling = pd.concat([df_customer[buy].sample(100), df_customer[~buy].sample(100)])",
        "failed",  # 少ない方を全件残していない
    ),
    # ---- その他
    ("032", "python", 'df_receipt["amount"].quantile([0.25, 0.5, 0.75, 1.0]).values', "passed"),
    ("032", "python", 'df_receipt["amount"].quantile([0.25, 0.5, 0.75])', "failed"),
    (
        "077",
        "python",
        'df = df_receipt.groupby("customer_id", as_index=False).amount.sum()\n'
        "z = np.log10(df.amount)\n"
        "df[((z - z.mean()) / z.std()).abs() > 3].head(10)",
        "passed",  # 常用対数・+0.5なし・不偏標準偏差
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
    ("071", "python", 0): "上流の解答は pandas 3 で動かない（Series[0] の位置指定）",
    ("072", "python", 0): "上流の解答は pandas 3 で動かない（Series[0] の位置指定）",
    ("073", "python", 0): "上流の解答は pandas 3 で動かない（Series.view の削除）",
    ("083", "python", 0): "上流の解答は pandas 3 で動かない（Series[0] の位置指定）",
    ("084", "python", 0): "上流の解答は pandas 3 で動かない（Series[0] の位置指定）",
    ("084", "python", 1): "確認用コード（前のセルの変数を表示するだけ）",
    ("086", "python", 0): "上流の解答は pandas 3 で動かない（Series[0] の位置指定）",
    ("090", "python", 1): "確認用コード（前のセルの変数を表示するだけ）",
    ("090", "python", 2): "確認用コード（前のセルの変数を表示するだけ）",
    ("090", "python", 3): "コード例2（前のセルで作った変数を使う）",
    ("090", "python", 4): "確認用コード（前のセルの変数を表示するだけ）",
    ("090", "python", 5): "確認用コード（前のセルの変数を表示するだけ）",
    ("092", "python", 1): "確認用コード（前のセルの変数を表示するだけ）",
    ("092", "python", 2): "確認用コード（前のセルの変数を表示するだけ）",
}

# SQL でテーブルを作る問題は、上流のセルが「作成→表示」の順に実行する手順になっているため、
# セルをつなげた1つのスクリプトとして試す。次のものは理由つきで対象外。
SQL_SCRIPT_EXCLUDED = {
    "092": "上流の解答は customer_std から address 列を落としている（正規化として誤り。本アプリは全項目を残す形を正とする）",
    **{
        pid: "上流の解答は DB サーバー上のファイルに入出力する（本アプリは安全のため COPY ... TO STDOUT / FROM STDIN を使う）"
        for pid in ("094", "095", "096", "097", "098", "099", "100")
    },
}
MODEL_ANSWERS = [
    (eid, lang, i, code)
    for eid, lang in AUTO_GRADED
    if not (lang == "sql" and get_exercise(eid).grading[lang].writable)
    for i, code in enumerate(load_answers()[eid][lang])
    if (eid, lang, i) not in NOT_STANDALONE_ANSWERS
]
SQL_SCRIPTS = [
    (eid, ";\n".join(c.rstrip().rstrip(";") for c in load_answers()[eid]["sql"]))
    for eid, lang in AUTO_GRADED
    if lang == "sql" and get_exercise(eid).grading[lang].writable and eid not in SQL_SCRIPT_EXCLUDED
]


@pytest.mark.parametrize(("exercise_id", "language", "index", "code"), MODEL_ANSWERS)
def test_upstream_model_answers_pass(exercise_id, language, index, code):
    result = grade_code(exercise_id, language, code)
    assert result.status == "passed", result.feedback


@pytest.mark.parametrize(("exercise_id", "script"), SQL_SCRIPTS)
def test_upstream_sql_scripts_pass(exercise_id, script):
    """テーブルを作る問題の上流SQL解答（全セルをつなげたもの）が正解になる。"""
    result = grade_code(exercise_id, "sql", script)
    assert result.status == "passed", result.feedback
