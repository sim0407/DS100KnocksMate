"""出力ファイル（CSV/TSV）の採点: 文字コード・区切り文字・ヘッダの有無と内容を比べる。

- 期待ファイル（模範解答が出力したもの）と学習者のファイルを、指定の文字コードで読み、
  指定の区切り文字で分けて比較する。UTF-8 指定では BOM 付きも許容する
- 行の順序は問わない（重複は数える）。数値は表記の違い（198 と 198.0）を同一視する
- コード値のゼロ埋め（"04"）は文字列のまま比べ、4 とは区別する
- 学習者のファイルがCSVとして読めない（巨大な項目・引用符の崩れ等）ときは不正解として理由を返す。
  期待ファイルが読めないときは採点不可（gradable=False）
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass

from core.grading.compare import Comparison

_NUMBER_RE = re.compile(r"^-?(0|[1-9]\d*)(\.\d+)?$")
_DELIMITER_LABEL = {",": "カンマ", "\t": "タブ"}
_MAX_EXAMPLES = 3


@dataclass(frozen=True)
class FileFormat:
    delimiter: str = ","
    header: bool = True
    encoding: str = "utf-8"


def _decode(data: bytes, encoding: str) -> str:
    if encoding.lower().replace("_", "-") in ("utf-8", "utf8"):
        return data.decode("utf-8-sig")  # BOM 付きも許容
    return data.decode(encoding)


def _rows(text: str, delimiter: str) -> list[list[str]]:
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if row]


def _cell(value: str) -> tuple:
    if value == "":
        return ("null",)
    if _NUMBER_RE.match(value):
        return ("n", round(float(value), 6))
    return ("s", value)


def _canon(row: list[str]) -> tuple:
    return tuple(_cell(v) for v in row)


def compare_files(expected: bytes, actual: bytes, fmt: FileFormat) -> Comparison:
    """expected は模範解答が出力したファイルの中身。"""
    try:
        expected_rows = _rows(_decode(expected, fmt.encoding), fmt.delimiter)
    except (UnicodeDecodeError, csv.Error):
        return Comparison(
            False, ["期待するファイルを読み取れないため自動採点できません"], gradable=False
        )
    try:
        actual_text = _decode(actual, fmt.encoding)
    except UnicodeDecodeError:
        return Comparison(False, [f"文字コードが {fmt.encoding.upper()} ではないようです"])
    try:
        actual_rows = _rows(actual_text, fmt.delimiter)
    except csv.Error as exc:
        return Comparison(
            False,
            [
                f"ファイルをCSVとして読み取れません（{exc}）。"
                '1つの項目が大きすぎるか、引用符（"）の対応が崩れていないか確認してください'
            ],
        )
    if not actual_rows:
        return Comparison(False, ["ファイルが空です"])

    reasons: list[str] = []
    if expected_rows and len(expected_rows[0]) > 1 and all(len(r) == 1 for r in actual_rows[:5]):
        label = _DELIMITER_LABEL.get(fmt.delimiter, repr(fmt.delimiter))
        reasons.append(f"区切り文字が違うようです（期待: {label}区切り）")
        return Comparison(False, reasons)

    if fmt.header:
        expected_header, actual_header = expected_rows[0], actual_rows[0]
        if actual_header != expected_header:
            return Comparison(
                False,
                [
                    f"ヘッダ行が違います（期待: {','.join(expected_header)} / "
                    f"実際: {','.join(actual_header)[:200]}）。インデックスを出力していないかも確認してください"
                ],
            )
        expected_rows, actual_rows = expected_rows[1:], actual_rows[1:]

    if len(actual_rows) != len(expected_rows):
        hint = (
            "（ヘッダの有無を確認してください）"
            if abs(len(actual_rows) - len(expected_rows)) == 1
            else ""
        )
        return Comparison(
            False,
            [
                f"データの行数が違います（期待: {len(expected_rows)}行 / 実際: {len(actual_rows)}行）{hint}"
            ],
        )
    surplus = Counter(_canon(r) for r in actual_rows) - Counter(_canon(r) for r in expected_rows)
    if surplus:
        bad = [r for r in actual_rows if _canon(r) in surplus][:_MAX_EXAMPLES]
        examples = " / ".join(",".join(r)[:120] for r in bad)
        return Comparison(
            False,
            [
                f"内容が一致しない行が{sum(surplus.values())}行あります（例: {examples}）。"
                "文字化けやコード値のゼロ埋めの欠落がないか確認してください"
            ],
        )
    return Comparison(True)
