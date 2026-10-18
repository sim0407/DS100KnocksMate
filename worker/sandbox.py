"""学習者コードを fork した子プロセスで実行する（Linux専用）。

親プロセス（ワーカーサーバ）はライブラリと教材データを読み込み済みで待機し、実行ごとに fork する。
子は親のメモリをコピーオンライトで共有するため起動が速く、子での変更（df の上書き等）は
親や次の実行に影響しない。

子プロセスでの制限:
- 実時間タイムアウト（親がプロセスグループごと SIGKILL）と、予備としてのCPU時間制限
- 書き込みファイルサイズ制限（RLIMIT_FSIZE）、毎回新しい一時作業ディレクトリ
  （カレントは work/、出力先 ./data と ../data は同じ data/ フォルダ。collect_files で回収）
- 結果JSONのバイト数上限（超えたら kill）
- OOM時に子が優先して kill されるよう oom_score_adj=1000
- 標準入出力のfdは /dev/null へ（サーバのログやプロトコルを汚さない）
メモリ総量・PID数・ネットワークはコンテナ側（docker-compose.yml）で制限する。
"""

from __future__ import annotations

import base64
import json
import math
import os
import select
import shutil
import signal
import tempfile
import time
from dataclasses import dataclass
from typing import Any

from worker.executor import execute


@dataclass(frozen=True)
class Limits:
    timeout_sec: float = 10.0
    max_output_bytes: int = 64 * 1024 * 1024
    max_file_bytes: int = 10 * 1024 * 1024
    max_rows: int = 200
    max_stdout_chars: int = 20000
    max_collected_files: int = 10
    max_collected_bytes: int = 16 * 1024 * 1024


def _failure(status: str, message: str, elapsed_ms: int) -> dict:
    return {
        "status": status,
        "result": None,
        "stdout": "",
        "stdout_truncated": False,
        "stderr": "",
        "stderr_truncated": False,
        "error": {"type": status, "message": message, "traceback": "", "lineno": None},
        "elapsed_ms": elapsed_ms,
    }


def _harden_child(limits: Limits, workdir: str) -> None:
    import resource  # Unix専用（Windowsでもこのモジュールをimportできるよう遅延import）

    os.setsid()  # 子孫プロセスもまとめて kill できるよう新しいプロセスグループに
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    try:
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write("1000")
    except OSError:
        pass
    cpu = math.ceil(limits.timeout_sec) + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits.max_file_bytes, limits.max_file_bytes))
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)  # 超過時はシグナル終了ではなく OSError に
    os.chdir(os.path.join(workdir, "work"))


def _prepare_workdir(workdir: str) -> None:
    """workdir/work（カレント）と workdir/data を作り、work/data → ../data のリンクを張る。

    問題文の出力先「./data」と、上流解答の「../data」のどちらでも同じフォルダになる。
    """
    os.makedirs(os.path.join(workdir, "work"))
    os.makedirs(os.path.join(workdir, "data"))
    os.symlink(os.path.join("..", "data"), os.path.join(workdir, "work", "data"))


def _collect_files(workdir: str, limits: Limits) -> list[dict]:
    """data フォルダに書かれたファイルを（件数・サイズ上限つきで）base64 で返す。"""
    data_dir = os.path.join(workdir, "data")
    files, total = [], 0
    for dirpath, _, names in sorted(os.walk(data_dir)):
        for name in sorted(names):
            if len(files) >= limits.max_collected_files:
                return files
            path = os.path.join(dirpath, name)
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            size = os.path.getsize(path)
            budget = max(limits.max_collected_bytes - total, 0)
            with open(path, "rb") as f:
                content = f.read(budget)
            total += len(content)
            files.append(
                {
                    "path": os.path.relpath(path, workdir).replace(os.sep, "/"),
                    "size": size,
                    "content_b64": base64.b64encode(content).decode("ascii"),
                    "truncated": len(content) < size,
                }
            )
    return files


def _child_main(
    code: str,
    base_namespace: dict[str, Any],
    limits: Limits,
    wfd: int,
    workdir: str,
    setup: str,
    collect_files: bool,
    artifacts: tuple[str, ...],
):
    try:
        _harden_child(limits, workdir)
        result = execute(
            code,
            dict(base_namespace),
            setup=setup,
            max_rows=limits.max_rows,
            max_stdout_chars=limits.max_stdout_chars,
            artifacts=artifacts,
        )
        if collect_files:
            result["files"] = _collect_files(workdir, limits)
        data = json.dumps(result, ensure_ascii=False).encode("utf-8")
        view = memoryview(data)
        while view:
            written = os.write(wfd, view)
            view = view[written:]
    finally:
        os._exit(0)


def _kill_group(pid: int) -> None:
    for target in (lambda: os.killpg(pid, signal.SIGKILL), lambda: os.kill(pid, signal.SIGKILL)):
        try:
            target()
        except (ProcessLookupError, PermissionError):
            pass


def run_in_sandbox(
    code: str,
    base_namespace: dict[str, Any],
    *,
    limits: Limits,
    setup: str = "",
    collect_files: bool = False,
    artifacts: tuple[str, ...] = (),
) -> dict:
    started = time.monotonic()
    workdir = tempfile.mkdtemp(prefix="knocks-run-")
    _prepare_workdir(workdir)
    rfd, wfd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(rfd)
        _child_main(
            code, base_namespace, limits, wfd, workdir, setup, collect_files, tuple(artifacts)
        )
    os.close(wfd)

    def elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    buf = bytearray()
    outcome: dict | None = None
    deadline = started + limits.timeout_sec
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_group(pid)
                outcome = _failure(
                    "timeout", f"制限時間（{limits.timeout_sec:g}秒）を超えました", elapsed_ms()
                )
                break
            ready, _, _ = select.select([rfd], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(rfd, 1 << 20)
            if not chunk:
                break
            buf += chunk
            if len(buf) > limits.max_output_bytes:
                _kill_group(pid)
                outcome = _failure("output_limit", "結果が大きすぎます", elapsed_ms())
                break
    finally:
        os.close(rfd)
        _kill_group(pid)  # 正常終了時も、残った子孫プロセスを片付ける
        _, status = os.waitpid(pid, 0)
        shutil.rmtree(workdir, ignore_errors=True)

    if outcome is not None:
        return outcome
    if not buf:
        if os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGXCPU:
            return _failure("timeout", "CPU時間の上限を超えました", elapsed_ms())
        return _failure(
            "crashed",
            "実行プロセスが異常終了しました（メモリ不足、os._exit 等の可能性）",
            elapsed_ms(),
        )
    return json.loads(buf)
