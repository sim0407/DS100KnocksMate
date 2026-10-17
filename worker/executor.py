"""学習者のPythonコードを与えられた名前空間で実行し、結果をJSON安全な辞書で返す。

Jupyterと同様に「最後の式の値」を結果とする。print は stdout、警告等は stderr として
文字数上限付きで捕捉する。プロセス隔離・タイムアウト・資源制限はここでは扱わない
（worker/sandbox.py が子プロセス内でこの関数を呼ぶ）。
"""

from __future__ import annotations

import ast
import io
import linecache
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from worker.serialize import serialize_value

USER_FILENAME = "<学習者コード>"


class CappedWriter(io.TextIOBase):
    """上限文字数を超えた出力を捨てるstdout代替。"""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.parts: list[str] = []
        self.size = 0
        self.truncated = False

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        remaining = self.limit - self.size
        if len(s) > remaining:
            self.truncated = True
            s = s[: max(remaining, 0)]
        if s:
            self.parts.append(s)
            self.size += len(s)
        return len(s)

    def getvalue(self) -> str:
        return "".join(self.parts)


def _display(*objects: Any, **_: Any) -> None:
    for obj in objects:
        print(obj)


def _error(exc: BaseException, *, user_only: bool = True) -> dict:
    frames = traceback.extract_tb(exc.__traceback__)
    if user_only:
        frames = traceback.StackSummary.from_list(
            [f for f in frames if f.filename == USER_FILENAME]
        )
    lineno = frames[-1].lineno if frames else getattr(exc, "lineno", None)
    text = ""
    if frames:
        text = "Traceback (most recent call last):\n" + "".join(frames.format())
    text += "".join(traceback.format_exception_only(type(exc), exc))
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": text,
        "lineno": lineno,
    }


def execute(
    code: str,
    namespace: dict[str, Any],
    *,
    max_rows: int = 200,
    max_stdout_chars: int = 20000,
    max_text_chars: int = 20000,
) -> dict:
    started = time.perf_counter()
    stdout = CappedWriter(max_stdout_chars)
    stderr = CappedWriter(max_stdout_chars)
    namespace.setdefault("display", _display)
    linecache.cache[USER_FILENAME] = (len(code), None, code.splitlines(True), USER_FILENAME)

    status, result, error = "ok", None, None
    try:
        tree = ast.parse(code, filename=USER_FILENAME)
        last_expr = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr = ast.Expression(tree.body.pop().value)
        body = compile(tree, USER_FILENAME, "exec")
        expr = compile(last_expr, USER_FILENAME, "eval") if last_expr else None

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(body, namespace)
            if expr is not None:
                value = eval(expr, namespace)
                try:
                    result = serialize_value(
                        value, max_rows=max_rows, max_text_chars=max_text_chars
                    )
                except Exception as exc:  # 結果のreprが壊れている等
                    status = "error"
                    error = _error(exc, user_only=False)
                    error["type"] = "ResultError"
                    error["message"] = f"結果の表示に失敗しました: {exc!r}"
    except SyntaxError as exc:
        status, error = "error", _error(exc)
    except BaseException as exc:  # SystemExit等も学習者のエラーとして返す
        status, error = "error", _error(exc)

    return {
        "status": status,
        "result": result,
        "stdout": stdout.getvalue(),
        "stdout_truncated": stdout.truncated,
        "stderr": stderr.getvalue(),
        "stderr_truncated": stderr.truncated,
        "error": error,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
