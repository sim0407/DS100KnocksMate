"""Pythonワーカーの HTTP サーバ（標準ライブラリのみ）。内部Dockerネットワーク専用で、ホストへは公開しない。

    GET  /health   -> {"status": "ok"}
    POST /execute  {"code": str, "max_rows"?: int, "timeout_sec"?: float} -> 実行結果JSON

起動時にライブラリと教材データを読み込み、実行ごとに worker.sandbox で fork して実行する。
マルチスレッドのプロセスからの fork は子でデッドロックしうるため、サーバはシングルスレッド
（実行は同時に1件、実行中は他のリクエストが待つ）。学習者のコードはログに出さない。
コンテナはゾンビ回収のため init 付き（compose の `init: true`）で起動する。
"""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from worker.datasets import load_tables
from worker.sandbox import Limits, run_in_sandbox

log = logging.getLogger("knocks.worker")

MAX_BODY_BYTES = 1_000_000
MAX_CODE_CHARS = 100_000
MAX_ROWS_LIMIT = 500_000
MAX_TIMEOUT_SEC = 60.0

# 公式Python解答Notebookの共通セットアップのうち、DB接続とIPython依存を除いたもの
SETUP_CODE = """\
import math
import os

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from imblearn.under_sampling import RandomUnderSampler
from sklearn import preprocessing
from sklearn.impute import SimpleImputer
from sklearn.model_selection import TimeSeriesSplit
from sklearn.model_selection import train_test_split
"""


def build_base_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    exec(SETUP_CODE, namespace)
    namespace.update(load_tables())
    return namespace


class BadRequest(ValueError):
    pass


def parse_request(body: bytes, defaults: Limits) -> tuple[str, Limits]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadRequest("JSONとして解釈できません") from exc
    if not isinstance(payload, dict):
        raise BadRequest("オブジェクトを送ってください")
    code = payload.get("code")
    if not isinstance(code, str):
        raise BadRequest("code は文字列が必要です")
    if len(code) > MAX_CODE_CHARS:
        raise BadRequest(f"コードが長すぎます（上限 {MAX_CODE_CHARS} 文字）")

    max_rows = payload.get("max_rows", defaults.max_rows)
    if (
        not isinstance(max_rows, int)
        or isinstance(max_rows, bool)
        or not 1 <= max_rows <= MAX_ROWS_LIMIT
    ):
        raise BadRequest(f"max_rows は 1〜{MAX_ROWS_LIMIT} の整数")
    timeout = payload.get("timeout_sec", defaults.timeout_sec)
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 0 < timeout <= MAX_TIMEOUT_SEC
    ):
        raise BadRequest(f"timeout_sec は 0〜{MAX_TIMEOUT_SEC:g} 秒")

    return code, Limits(
        timeout_sec=float(timeout),
        max_output_bytes=defaults.max_output_bytes,
        max_file_bytes=defaults.max_file_bytes,
        max_rows=max_rows,
        max_stdout_chars=defaults.max_stdout_chars,
    )


def make_server(
    host: str, port: int, base_namespace: dict[str, Any], defaults: Limits | None = None
) -> HTTPServer:
    defaults = defaults or Limits()

    class Handler(BaseHTTPRequestHandler):
        server_version = "knocks-worker"

        def log_message(self, format: str, *args: Any) -> None:  # コード本文は記録しない
            log.info("%s %s", self.command, self.path)

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {"status": "ok"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/execute":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._send(413, {"error": "リクエストが大きすぎます"})
                return
            try:
                code, limits = parse_request(self.rfile.read(length), defaults)
            except BadRequest as exc:
                self._send(400, {"error": str(exc)})
                return
            result = run_in_sandbox(code, base_namespace, limits=limits)
            self._send(200, result)

    return HTTPServer((host, port), Handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("KNOCKS_WORKER_HOST", "0.0.0.0")
    port = int(os.environ.get("KNOCKS_WORKER_PORT", "8000"))
    log.info("loading libraries and datasets...")
    namespace = build_base_namespace()
    server = make_server(host, port, namespace)
    log.info("worker listening on %s:%d", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
