"""worker/server.py のテスト。リクエスト検証はどこでも、HTTP経由の実行はLinuxのみ。"""

import json
import os
import threading
import urllib.error
import urllib.request

import pandas as pd
import pytest

from worker.sandbox import Limits
from worker.server import MAX_ROWS_LIMIT, BadRequest, make_server, parse_request


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"code": 1}',
        b'{"code": "1", "max_rows": 0}',
        json.dumps({"code": "1", "max_rows": MAX_ROWS_LIMIT + 1}).encode(),
        b'{"code": "1", "max_rows": true}',
        b'{"code": "1", "timeout_sec": 0}',
        b'{"code": "1", "timeout_sec": 600}',
        json.dumps({"code": "x" * 100_001}).encode(),
    ],
    ids=[
        "not-json",
        "not-object",
        "code-not-str",
        "rows-zero",
        "rows-too-many",
        "rows-bool",
        "timeout-zero",
        "timeout-too-long",
        "code-too-long",
    ],
)
def test_parse_request_rejects_invalid(body):
    with pytest.raises(BadRequest):
        parse_request(body, Limits())


def test_parse_request_applies_values():
    code, limits = parse_request(b'{"code": "1", "max_rows": 50, "timeout_sec": 3}', Limits())
    assert code == "1"
    assert limits.max_rows == 50
    assert limits.timeout_sec == 3.0


needs_fork = pytest.mark.skipif(not hasattr(os, "fork"), reason="fork が使えない環境（Windows）")

# テストではサーバを別スレッドで動かすため fork 時に警告が出る（本番はシングルスレッドで出ない）
pytestmark = pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded:DeprecationWarning"
)


@pytest.fixture
def server_url():
    server = make_server("127.0.0.1", 0, {"df": pd.DataFrame({"a": [1, 2]})})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def post(url, payload):
    req = urllib.request.Request(
        url + "/execute",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.status, json.loads(res.read())


@needs_fork
def test_health(server_url):
    with urllib.request.urlopen(server_url + "/health", timeout=5) as res:
        assert json.loads(res.read()) == {"status": "ok"}


@needs_fork
def test_execute_over_http(server_url):
    status, body = post(server_url, {"code": "df"})
    assert status == 200
    assert body["status"] == "ok"
    assert body["result"]["rows"] == [[1], [2]]


@needs_fork
def test_bad_request_over_http(server_url):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(server_url, {"code": 123})
    assert exc.value.code == 400


def test_parse_request_accepts_setup_and_collect_files():
    code, limits, options = parse_request(
        b'{"code": "1", "setup": "x = 1", "collect_files": true}', Limits(), with_options=True
    )
    assert options == {"setup": "x = 1", "collect_files": True}


def test_parse_request_rejects_bad_setup():
    with pytest.raises(BadRequest):
        parse_request(b'{"code": "1", "setup": 3}', Limits())
