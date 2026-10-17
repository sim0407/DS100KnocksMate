"""隔離ワーカー（worker/server.py）に学習者のPythonコードを送って実行するクライアント。

アプリ（Streamlit）プロセスでは学習者のコードを実行しない。戻り値はワーカーの応答
（status / result / stdout / error / elapsed_ms 等）で、通信できない場合は status="unavailable"。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

# ワーカー側のタイムアウト後に応答を受け取るための余裕
_HTTP_MARGIN_SEC = 15.0


def _unavailable(message: str, started: float) -> dict:
    return {
        "status": "unavailable",
        "result": None,
        "stdout": "",
        "stdout_truncated": False,
        "stderr": "",
        "stderr_truncated": False,
        "error": {"type": "WorkerUnavailable", "message": message, "traceback": "", "lineno": None},
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def run_python(code: str, *, url: str, max_rows: int = 200, timeout_sec: float = 10.0) -> dict:
    started = time.monotonic()
    body = json.dumps({"code": code, "max_rows": max_rows, "timeout_sec": timeout_sec}).encode()
    request = urllib.request.Request(
        url.rstrip("/") + "/execute",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec + _HTTP_MARGIN_SEC) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        return _unavailable(
            f"実行ワーカーがエラーを返しました（HTTP {exc.code}）: {detail}", started
        )
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return _unavailable(
            f"実行ワーカーに接続できません（起動中の可能性があります）: {exc}", started
        )
