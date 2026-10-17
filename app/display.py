"""実行結果（JSON安全な辞書）を画面表示用に変換する。採点には使わない。"""

from __future__ import annotations

import pandas as pd


def unique_columns(columns: list[str]) -> list[str]:
    """表示ライブラリは列名の重複を扱えないため、2つ目以降に (2), (3)… を付ける。"""
    seen: dict[str, int] = {}
    result = []
    for name in columns:
        seen[name] = seen.get(name, 0) + 1
        result.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    return result


def to_dataframe(result: dict) -> pd.DataFrame:
    columns = unique_columns([str(c) for c in result["columns"]])
    df = pd.DataFrame(result["rows"], columns=columns)
    for name, kind in zip(columns, result["kinds"], strict=True):
        if kind == "integer" and df[name].isna().any():
            df[name] = df[name].astype("Int64")  # 欠損を含む整数を 1.0 のように見せない
        elif kind in ("other", "string", "datetime"):
            # pandas 3 では None が NaN になるため pd.isna で判定する（'nan' 文字列にしない）
            df[name] = df[name].map(lambda v: None if pd.isna(v) else str(v)).astype(object)
    return df


def row_summary(result: dict, shown: int) -> str:
    total = int(result["row_count"])
    cols = len(result["columns"])
    if result.get("truncated"):
        return f"{total:,}行 × {cols}列（先頭{shown:,}行を表示）"
    return f"{total:,}行 × {cols}列"


def file_preview(content: bytes, max_lines: int = 15) -> tuple[str, str]:
    """(文字コードの推定, 先頭 max_lines 行)。UTF-8 → CP932 の順に試す。"""
    candidates = (("utf-8", "UTF-8"), ("cp932", "CP932（Shift_JIS）"))
    for encoding, label in candidates:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if encoding == "utf-8" and text.startswith("\ufeff"):
            text, label = text[1:], "UTF-8（BOM付き）"
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = [*lines[:max_lines], "…"]
        return label, "\n".join(lines)
    return "不明（UTF-8/CP932 として読めません）", ""


def file_label(path: str) -> str:
    if path.startswith("COPY_TO_STDOUT_"):
        return f"COPY ... TO STDOUT の出力（{path.rsplit('_', 1)[1]}）"
    return path
