"""core/execution/sql_runner.py の統合テスト（教材用PostgreSQLが必要）。

実行: docker compose --profile test run --rm --build tests
"""

import os

import pytest

from core.execution.sql_runner import normalize_sql, run_sql

DSN = os.environ.get("KNOCKS_DB_DSN")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DSN, reason="KNOCKS_DB_DSN が未設定（compose の tests サービスで実行）"),
]


def run(sql, **kwargs):
    return run_sql(sql, dsn=DSN, **kwargs)


def count(table):
    return run(f"SELECT count(*) AS n FROM {table}")["result"]["rows"][0][0]


# ---------------------------------------------------------------- 正常系


def test_s001_reference_answer():
    r = run("SELECT\n    *\nFROM receipt\nLIMIT 10\n;")
    assert r["status"] == "ok"
    assert r["result"]["columns"][:3] == ["sales_ymd", "sales_epoch", "store_cd"]
    assert len(r["result"]["rows"]) == 10
    assert r["result"]["row_count"] == 10
    assert r["result"]["truncated"] is False


@pytest.mark.parametrize(
    ("table", "n"),
    [
        ("customer", 21971),
        ("category", 228),
        ("product", 10030),
        ("receipt", 104681),
        ("store", 53),
        ("geocode", 127252),
    ],
)
def test_all_tables_loaded(table, n):
    assert count(table) == n


def test_row_limit_and_exact_total_count():
    r = run("SELECT * FROM receipt", max_rows=5)
    assert len(r["result"]["rows"]) == 5
    assert r["result"]["row_count"] == 104681
    assert r["result"]["truncated"] is True


def test_zero_rows_keeps_columns():
    r = run("SELECT store_cd, store_name FROM store WHERE false")
    assert r["result"]["columns"] == ["store_cd", "store_name"]
    assert r["result"]["rows"] == []
    assert r["result"]["row_count"] == 0


def test_percent_in_like_pattern():
    r = run("SELECT store_cd FROM store WHERE store_cd LIKE 'S14%' ORDER BY store_cd")
    assert r["status"] == "ok"
    assert all(row[0].startswith("S14") for row in r["result"]["rows"])


def test_kinds_and_values():
    r = run(
        "SELECT c.birth_day, c.age, s.floor_area, c.customer_id, true AS flag, "
        "cat.category_major_cd "
        "FROM customer c, store s, category cat "
        "WHERE c.customer_id = 'CS021313000114' AND s.store_cd = 'S12014' LIMIT 1"
    )
    result = r["result"]
    assert result["kinds"] == ["datetime", "integer", "float", "string", "boolean", "string"]
    birth_day, age, floor_area, customer_id, flag, major_cd = result["rows"][0]
    assert birth_day == "1981-04-29"
    assert age == 37 and isinstance(age, int)
    assert floor_area == 1698.0
    assert customer_id == "CS021313000114"
    assert flag is True
    assert len(major_cd) == 2 and major_cd.startswith("0")  # ゼロ埋めが保たれる


def test_numeric_null_is_none():
    r = run("SELECT unit_price FROM product WHERE unit_price IS NULL LIMIT 1")
    assert r["result"]["rows"] == [[None]]


def test_cte_is_allowed():
    r = run("WITH s AS (SELECT store_cd FROM store) SELECT count(*) FROM s")
    assert r["result"]["rows"] == [[53]]


@pytest.mark.parametrize(
    "sql", ["%%sql\nSELECT 1 AS a;", "  SELECT 1 AS a ;  ", "SELECT 1 AS a -- c"]
)
def test_notebook_style_input_is_accepted(sql):
    r = run(sql)
    assert r["status"] == "ok"
    assert r["result"]["rows"] == [[1]]


def test_normalize_sql():
    assert normalize_sql("%%sql\n\nSELECT 1;\n") == "SELECT 1;"


# ---------------------------------------------------------------- 教材DBを壊せない


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM store",
        "UPDATE store SET store_name = 'x'",
        "INSERT INTO store (store_cd) VALUES ('X')",
        "DROP TABLE store",
        "TRUNCATE store",
        "CREATE TABLE t (a int)",
        "CREATE TEMP TABLE t (a int)",
        "SELECT * INTO t FROM store",
        "ALTER TABLE store ADD COLUMN x int",
        "GRANT ALL ON store TO PUBLIC",
        "SELECT 1; DELETE FROM store",
        "SET TRANSACTION READ WRITE; DELETE FROM store",
        "COMMIT; DELETE FROM store",
        "COPY store TO PROGRAM 'id'",
        "SELECT pg_read_file('/etc/passwd')",
        "WITH d AS (DELETE FROM store RETURNING *) SELECT * FROM d",
    ],
)
def test_destructive_sql_is_rejected_and_data_unchanged(sql):
    r = run(sql)
    assert r["status"] == "error"
    assert count("store") == 53


def test_select_only_message():
    r = run("DELETE FROM store")
    assert "SELECT" in r["error"]["message"]


def test_multiple_statements_message():
    r = run("SELECT 1; SELECT 2")
    assert r["status"] == "error"
    assert "1文" in r["error"]["message"]


# ---------------------------------------------------------------- エラー・制限


def test_syntax_error_reports_learner_line():
    r = run("SELECT\n  *\nFROM receipt\nWHER x")
    assert r["status"] == "error"
    assert r["error"]["type"] == "SyntaxError"
    assert r["error"]["lineno"] == 4


def test_undefined_column_message_is_shown():
    r = run("SELECT no_such_column FROM store")
    assert r["status"] == "error"
    assert "no_such_column" in r["error"]["message"]


def test_timeout():
    r = run("SELECT pg_sleep(5)", timeout_sec=1)
    assert r["status"] == "timeout"


def test_huge_result_does_not_exhaust_memory():
    r = run("SELECT * FROM receipt r, store s", max_rows=10, timeout_sec=3)
    assert r["status"] in ("ok", "timeout")
    if r["status"] == "ok":
        assert len(r["result"]["rows"]) == 10


def test_empty_sql():
    assert run("   ")["status"] == "error"


def test_unavailable_database():
    r = run_sql("SELECT 1", dsn="host=127.0.0.1 port=1 dbname=x user=x connect_timeout=1")
    assert r["status"] == "unavailable"


# ---------------------------------------------------------------- 書き込み可能モード（テーブル作成、必ずロールバック）


def write(sql, **kwargs):
    return run_sql(sql, dsn=DSN, writable=True, **kwargs)


def test_writable_create_table_and_select():
    r = write(
        "DROP TABLE IF EXISTS product_1;\n"
        "CREATE TABLE product_1 AS (SELECT * FROM product WHERE unit_price IS NOT NULL);\n"
        "SELECT COUNT(*) AS n FROM product_1;"
    )
    assert r["status"] == "ok", r["error"]
    assert r["result"]["rows"] == [[10023]]


def test_writable_changes_are_rolled_back():
    write("CREATE TABLE leftover AS SELECT 1 AS a; SELECT 1")
    r = run("SELECT * FROM leftover")
    assert r["status"] == "error"
    assert "leftover" in r["error"]["message"]


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM product",
        "UPDATE product SET unit_price = 0",
        "DROP TABLE product",
        "ALTER TABLE product ADD COLUMN x int",
        "TRUNCATE product",
        "CREATE TABLE public.evil AS SELECT 1",
        "SET ROLE postgres",
    ],
)
def test_writable_cannot_touch_teaching_tables(sql):
    r = write(sql + "; SELECT 1")
    assert r["status"] == "error"
    assert count("product") == 10030


def test_writable_temp_table_and_multiple_selects_returns_last():
    r = write("CREATE TEMP TABLE t AS SELECT 1 AS a;\nSELECT 'first';\nSELECT a + 1 AS b FROM t;")
    assert r["result"]["columns"] == ["b"]
    assert r["result"]["rows"] == [[2]]


def test_writable_script_without_select_has_no_result():
    r = write("CREATE TABLE t AS SELECT 1 AS a;")
    assert r["status"] == "ok"
    assert r["result"] is None


def test_writable_error_line_number_in_later_statement():
    r = write("CREATE TABLE t AS SELECT 1 AS a;\n\nSELECT\n  no_such_col\nFROM t;")
    assert r["status"] == "error"
    assert r["error"]["lineno"] == 4


def test_setup_runs_before_learner_sql():
    r = write(
        "SELECT era FROM sales_summary ORDER BY era",
        setup="CREATE TABLE sales_summary AS SELECT 10 AS era UNION ALL SELECT 20",
    )
    assert r["result"]["rows"] == [[10], [20]]


def test_copy_to_stdout_is_captured_as_file():
    import base64

    r = write("COPY (SELECT 'a' AS x, 1 AS n) TO STDOUT WITH CSV HEADER;")
    assert r["status"] == "ok"
    (f,) = r["files"]
    assert base64.b64decode(f["content_b64"]) == b"x,n\na,1\n"


def test_copy_to_server_file_is_rejected_with_hint():
    r = write("COPY product TO '/tmp/x.csv' WITH CSV;")
    assert r["status"] == "error"
    assert "STDOUT" in r["error"]["message"]


def test_copy_from_stdin_reads_prepared_data():
    r = write(
        "CREATE TABLE t (x text, n int);\nCOPY t FROM STDIN WITH CSV HEADER;\nSELECT * FROM t;",
        stdin_query="COPY (SELECT 'a' AS x, 1 AS n) TO STDOUT WITH CSV HEADER",
    )
    assert r["status"] == "ok", r["error"]
    assert r["result"]["rows"] == [["a", 1]]


def test_copy_from_stdin_without_prepared_data_is_error():
    r = write("CREATE TABLE t (x text); COPY t FROM STDIN;")
    assert r["status"] == "error"


def test_read_only_mode_still_rejects_multiple_statements():
    r = run("CREATE TABLE t AS SELECT 1; SELECT 1")
    assert r["status"] == "error"


# ---------------------------------------------------------------- 実行全体の制限時間・結果の大きさ


def test_timeout_covers_whole_script_not_each_statement():
    """1文ずつは制限内でも、合計が制限時間を超えたら打ち切る。"""
    sql = ";\n".join(["SELECT pg_sleep(0.6)"] * 5)
    r = run(sql, timeout_sec=1.5, writable=True)
    assert r["status"] == "timeout"
    assert r["elapsed_ms"] < 2500


def test_learner_cannot_disable_statement_timeout():
    r = run("SET statement_timeout = 0;\nSELECT pg_sleep(30)", timeout_sec=1, writable=True)
    assert r["status"] == "timeout"
    assert r["elapsed_ms"] < 2500


def test_learner_set_config_in_read_only_mode_does_not_extend_timeout():
    r = run("SELECT set_config('statement_timeout', '0', false), pg_sleep(30)", timeout_sec=1)
    assert r["status"] == "timeout"


@pytest.mark.parametrize("writable", [False, True])
def test_huge_values_are_rejected_before_exhausting_memory(writable):
    """行数は少なくても、値が巨大な結果は上限で打ち切る（UIのプロセスのメモリを守る）。"""
    sql = "SELECT repeat('x', 10 * 1024 * 1024) AS s FROM generate_series(1, 20)"
    r = run(sql, max_rows=300_000, writable=writable)
    assert r["status"] == "error"
    assert "大きすぎます" in r["error"]["message"]


def test_large_but_allowed_result_is_fetched_completely():
    r = run("SELECT * FROM receipt", max_rows=300_000, timeout_sec=20)
    assert r["status"] == "ok"
    assert len(r["result"]["rows"]) == 104681
    assert r["result"]["truncated"] is False


# ---------------------------------------------------------------- 作成したテーブルの取り出し（採点用）


def test_artifacts_come_from_the_same_run():
    """乱数で分けた2つのテーブルを、同じ1回の実行から取り出す（重なりがない）。"""
    sql = (
        "CREATE TABLE t AS SELECT g AS id, random() AS r FROM generate_series(1, 1000) g;\n"
        "CREATE TABLE tr AS SELECT id FROM t WHERE r < 0.5;\n"
        "CREATE TABLE te AS SELECT id FROM t WHERE r >= 0.5;"
    )
    r = run(sql, artifacts=("tr", "te"), max_rows=5000)
    assert r["status"] == "ok"
    train = {row[0] for row in r["artifacts"]["tr"]["rows"]}
    test = {row[0] for row in r["artifacts"]["te"]["rows"]}
    assert not train & test
    assert len(train | test) == 1000


def test_missing_artifact_table_is_undefined_table_error():
    r = run("CREATE TABLE tr AS SELECT 1 AS id", artifacts=("tr", "te"))
    assert r["status"] == "error"
    assert r["error"]["type"] == "UndefinedTable"
    assert '"te"' in r["error"]["message"]
