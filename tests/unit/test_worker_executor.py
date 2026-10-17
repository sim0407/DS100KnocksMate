"""worker/executor.py: 学習者コードの実行（最後の式の取得・標準出力・例外）のテスト。

ここではプロセス隔離は扱わない（worker/sandbox.py の統合テストで検証）。
"""

import pandas as pd

from worker.executor import execute


def run(code, namespace=None, **kwargs):
    return execute(code, dict(namespace or {}), **kwargs)


def test_last_expression_value_is_result():
    r = run("x = 1\nx + 1")
    assert r["status"] == "ok"
    assert r["result"] == {"type": "scalar", "value": 2, "kind": "integer"}


def test_dataframe_last_expression():
    ns = {"df_receipt": pd.DataFrame({"a": [1, 2, 3]})}
    r = run("df_receipt.head(2)", ns)
    assert r["result"]["type"] == "table"
    assert r["result"]["rows"] == [[1], [2]]


def test_no_last_expression_gives_null_result():
    r = run("x = 1")
    assert r["status"] == "ok"
    assert r["result"] is None


def test_last_expression_evaluating_to_none():
    r = run("print('hi')")
    assert r["result"] == {"type": "none"}
    assert r["stdout"] == "hi\n"


def test_stdout_is_captured_and_capped():
    r = run("for i in range(1000):\n    print('x' * 100)", max_stdout_chars=500)
    assert len(r["stdout"]) == 500
    assert r["stdout_truncated"] is True


def test_syntax_error_reports_line():
    r = run("x = 1\nx +")
    assert r["status"] == "error"
    assert r["error"]["type"] == "SyntaxError"
    assert r["error"]["lineno"] == 2


def test_runtime_error_traceback_shows_only_user_code():
    r = run("a = 1\nb = a / 0")
    assert r["status"] == "error"
    assert r["error"]["type"] == "ZeroDivisionError"
    assert r["error"]["lineno"] == 2
    assert "worker" not in r["error"]["traceback"]
    assert "b = a / 0" in r["error"]["traceback"]


def test_error_in_last_expression():
    r = run("undefined_name")
    assert r["error"]["type"] == "NameError"
    assert r["error"]["lineno"] == 1


def test_stdout_before_error_is_kept():
    r = run("print('before')\n1/0")
    assert r["stdout"] == "before\n"


def test_system_exit_is_reported_as_error():
    r = run("raise SystemExit(3)")
    assert r["status"] == "error"
    assert r["error"]["type"] == "SystemExit"


def test_display_writes_to_stdout():
    r = run("display(1)\n2")
    assert r["stdout"] == "1\n"
    assert r["result"]["value"] == 2


def test_result_row_limit_is_passed_through():
    ns = {"df": pd.DataFrame({"a": range(100)})}
    r = run("df", ns, max_rows=5)
    assert r["result"]["row_count"] == 100
    assert len(r["result"]["rows"]) == 5


def test_serialization_failure_is_error_not_crash():
    class Weird:
        def __repr__(self):
            raise RuntimeError("boom")

    r = run("w", {"w": Weird()})
    assert r["status"] == "error"
    assert "表示" in r["error"]["message"]


def test_elapsed_ms_reported():
    assert run("1")["elapsed_ms"] >= 0
