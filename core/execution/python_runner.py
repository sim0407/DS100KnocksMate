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


def run_python(
    code: str,
    *,
    url: str,
    max_rows: int = 200,
    timeout_sec: float = 10.0,
    setup: str = "",
    collect_files: bool = False,
    artifacts: tuple[str, ...] = (),
) -> dict:
    """setup: 学習者コードの前に同じ名前空間で実行する準備コード（前の問題のデータ作成など）。
    collect_files: 出力先 data フォルダのファイルを応答の files に含める。
    artifacts: 実行後に取り出す変数名（応答の artifacts に {名前: 値} で返す。採点用）。
    """
    started = time.monotonic()
    payload = {"code": code, "max_rows": max_rows, "timeout_sec": timeout_sec}
    if setup:
        payload["setup"] = setup
    if collect_files:
        payload["collect_files"] = True
    if artifacts:
        payload["artifacts"] = list(artifacts)
    body = json.dumps(payload).encode()
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
