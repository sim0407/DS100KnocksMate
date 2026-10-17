"""core/execution/python_runner.py と compose 上のワーカー隔離の統合テスト。

実行: docker compose --profile test run --rm --build tests
"""

import os

import pytest

from core.execution.python_runner import run_python

URL = os.environ.get("KNOCKS_WORKER_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not URL, reason="KNOCKS_WORKER_URL が未設定（compose の tests サービスで実行）"
    ),
]


def run(code, **kwargs):
    return run_python(code, url=URL, **kwargs)


def test_p001_reference_answer():
    r = run("df_receipt.head(10)")
    assert r["status"] == "ok"
    assert len(r["result"]["rows"]) == 10
    assert r["result"]["columns"][0] == "sales_ymd"


def test_official_setup_names_are_available():
    r = run("[type(x).__name__ for x in (pd, np, preprocessing, relativedelta, df_geocode)]")
    assert r["status"] == "ok"


def test_worker_cannot_reach_database():
    r = run("import socket\nsocket.create_connection(('db', 5432), 3)")
    assert r["status"] == "error"


def test_worker_cannot_reach_internet():
    r = run("import urllib.request\nurllib.request.urlopen('http://example.com', timeout=3)")
    assert r["status"] == "error"


def test_worker_has_no_database_credentials():
    # 注: 公式Pythonイメージの GPG_KEY（配布物の署名検証用の公開鍵ID）は秘密情報ではない
    r = run(
        "import os\nsorted(k for k in os.environ if k.startswith(('PG', 'KNOCKS_DB'))"
        " or 'DSN' in k or 'PASSWORD' in k)"
    )
    assert r["result"]["text"] == "[]"


def test_timeout_and_recovery():
    assert run("while True: pass", timeout_sec=1)["status"] == "timeout"
    assert run("len(df_store)")["result"]["value"] == 53


def test_root_filesystem_is_read_only():
    r = run("open('/opt/knocks/data/store.csv', 'a').write('x')")
    assert r["status"] == "error"


def test_unavailable_worker():
    r = run_python("1", url="http://127.0.0.1:1", timeout_sec=1)
    assert r["status"] == "unavailable"
