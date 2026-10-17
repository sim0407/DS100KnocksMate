"""リポジトリの健全性: ソースコードが .gitignore で除外されていないこと。

過去に .gitignore の `progress/` が core/progress/ まで除外し、学習履歴のコードが
コミットされていなかった（2026-10-18 に発見）。その再発防止。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRS = ("app", "core", "worker", "tools", "tests", "docker", "exercises", "upstream")

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(),
    reason="git リポジトリ内でのみ確認できる",
)


def test_no_source_file_is_git_ignored():
    sources = [
        p.relative_to(ROOT).as_posix()
        for d in SOURCE_DIRS
        for p in (ROOT / d).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "--no-index"],
        cwd=ROOT,
        input="\n".join(sources),
        capture_output=True,
        text=True,
    )
    ignored = [line for line in result.stdout.splitlines() if line]
    assert ignored == [], f".gitignore で除外されているソース: {ignored}"
