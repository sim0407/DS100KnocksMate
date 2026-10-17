"""worker/sandbox.py: fork した子プロセスでの隔離実行のテスト（Linuxのみ。Windowsではskip）。

Docker上では `docker compose run --rm worker-test` 等で実行する（README参照）。
"""

import os
import time
from importlib.util import find_spec

import pandas as pd
import pytest

# fork はスレッドのないプロセスで行う前提（本番のワーカーは単一スレッド）。pyarrow がある開発環境
# では pandas の読み込みでスレッドが生じ、本番と条件が違う上に子プロセスがデッドロックしうるため、
# 本番と同じワーカーのコンテナ（CI の worker ジョブ）で実行する。
FORK_TESTABLE = hasattr(os, "fork") and find_spec("pyarrow") is None
pytestmark = pytest.mark.skipif(
    not FORK_TESTABLE,
    reason="fork のテストはワーカーのコンテナ内で実行（Windows には fork がなく、pyarrow のある環境はスレッドが生じるため）",
)

if hasattr(os, "fork"):
    from worker.sandbox import Limits, run_in_sandbox


@pytest.fixture
def base():
    return {"df": pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})}


def run(code, base, **limits):
    return run_in_sandbox(code, base, limits=Limits(**limits))


def test_normal_execution(base):
    r = run("df.head(2)", base)
    assert r["status"] == "ok"
    assert r["result"]["rows"] == [[1, "x"], [2, "y"]]


def test_child_mutation_does_not_leak_to_parent(base):
    r = run("df.drop(columns=['a'], inplace=True)\nleak = 1\ndf", base)
    assert r["result"]["columns"] == ["b"]
    assert list(base["df"].columns) == ["a", "b"]
    assert "leak" not in base
    assert run("df", base)["result"]["columns"] == ["a", "b"]


def test_infinite_loop_times_out(base):
    started = time.monotonic()
    r = run("while True:\n    pass", base, timeout_sec=1)
    assert r["status"] == "timeout"
    assert time.monotonic() - started < 5


def test_sleep_times_out(base):
    r = run("import time\ntime.sleep(30)", base, timeout_sec=1)
    assert r["status"] == "timeout"


def test_output_limit(base):
    code = "import pandas as pd\npd.DataFrame({'a': range(200_000)})"
    r = run(code, base, max_rows=200_000, max_output_bytes=100_000)
    assert r["status"] == "output_limit"


def test_hard_exit_is_reported_as_crash(base):
    r = run("import os\nos._exit(3)", base)
    assert r["status"] == "crashed"


def test_file_size_limit(base):
    r = run("open('big.bin', 'wb').write(b'0' * 5_000_000)", base, max_file_bytes=1_000_000)
    assert r["status"] == "error"
    assert r["error"]["type"] in ("OSError", "IOError")


def test_runs_in_fresh_temp_directory(base):
    run("open('marker.txt', 'w').write('1')", base)
    r = run("import os\nos.path.exists('marker.txt')", base)
    assert r["result"]["value"] is False


def test_low_level_stdout_write_does_not_break_protocol(base):
    r = run("import os\nos.write(1, b'raw')\n42", base)
    assert r["status"] == "ok"
    assert r["result"]["value"] == 42


def _alive(pid: int) -> bool:
    """プロセスが生きているか。ゾンビ（終了済みで回収待ち）は死んでいるとみなす。

    コンテナで init なしに実行すると、kill された孫プロセスがゾンビとして残るため。
    """
    try:
        with open(f"/proc/{pid}/stat") as f:
            state = f.read().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    return state not in ("Z", "X")


def test_subprocesses_are_killed_on_timeout(base, tmp_path):
    pid_file = tmp_path / "child_pid"
    code = (
        "import subprocess, sys\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
        "p.wait()"
    )
    r = run(code, base, timeout_sec=2)
    assert r["status"] == "timeout"
    pid = int(pid_file.read_text())
    time.sleep(0.2)
    assert not _alive(pid)


def test_data_directory_is_reachable_as_dot_and_parent(base):
    code = (
        "open('data/a.csv', 'w').write('x,y\\n1,2\\n')\n"
        "open('../data/b.tsv', 'w').write('x\\ty\\n')\n"
        "sorted(__import__('os').listdir('data'))"
    )
    r = run_in_sandbox(code, base, limits=Limits(), collect_files=True)
    assert r["status"] == "ok"
    files = {f["path"]: f for f in r["files"]}
    assert set(files) == {"data/a.csv", "data/b.tsv"}
    import base64

    assert base64.b64decode(files["data/a.csv"]["content_b64"]) == b"x,y\n1,2\n"


def test_files_not_collected_by_default(base):
    r = run("open('data/a.csv', 'w').write('x')\n1", base)
    assert "files" not in r or r["files"] == []


def test_setup_through_sandbox(base):
    r = run_in_sandbox("y + 1", base, limits=Limits(), setup="y = 41")
    assert r["result"]["value"] == 42


def test_server_parent_process_is_single_threaded():
    """ワーカーの親プロセスは、ライブラリと教材データを読み込んだ後もスレッド1本（fork の前提）。"""
    from worker.server import build_base_namespace

    build_base_namespace()
    assert len(os.listdir("/proc/self/task")) == 1
