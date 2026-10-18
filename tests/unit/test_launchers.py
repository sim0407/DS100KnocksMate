"""起動用ファイルの形式。

日本語を含む .bat は cmd.exe が行を読み違えることがあり、別の PC で
「'README' is not recognized ...」と表示された（2026-10-18）。.bat は英数字だけにして
処理は PowerShell に任せ、PowerShell 5.1 が日本語を読めるよう .ps1 は BOM 付きにする。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BAT_FILES = sorted(ROOT.glob("*.bat"))
PS1_FILES = sorted((ROOT / "scripts" / "windows").glob("*.ps1"))
COMMAND_FILES = sorted(ROOT.glob("*.command"))


def test_launchers_exist():
    assert {p.name for p in BAT_FILES} == {"start.bat", "stop.bat"}
    assert {p.name for p in COMMAND_FILES} == {"start.command", "stop.command"}
    assert {p.name for p in PS1_FILES} >= {"common.ps1", "start.ps1", "stop.ps1"}


@pytest.mark.parametrize("path", BAT_FILES, ids=lambda p: p.name)
def test_bat_files_are_ascii_wrappers(path):
    data = path.read_bytes()
    assert data.isascii(), "日本語などの非 ASCII 文字を含めない"
    assert b"powershell" in data
    target = data.decode().split("%~dp0", 1)[1].split('"', 1)[0].replace("\\", "/")
    assert (ROOT / target).is_file(), f"呼び出し先がない: {target}"


@pytest.mark.parametrize("path", PS1_FILES, ids=lambda p: p.name)
def test_ps1_files_have_utf8_bom(path):
    data = path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf"), "Windows PowerShell 5.1 向けに BOM 付き UTF-8 にする"
    data.decode("utf-8-sig")


@pytest.mark.parametrize("path", COMMAND_FILES, ids=lambda p: p.name)
def test_command_files_use_lf(path):
    data = path.read_bytes()
    assert data.startswith(b"#!/bin/bash\n")
    assert b"\r\n" not in data, "macOS の bash は CRLF を読めない"
