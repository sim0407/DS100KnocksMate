"""問題カタログ（上流から抽出した問題文）と採点定義（手書きのTOML）を読み込む。

- exercises/catalog/problems.json : tools/extract_problems.py の生成物（問題文・注記・依存）
- exercises/catalog/answers.json  : 模範解答（学習UIには初期表示しない）
- exercises/problems/<id>.toml    : 採点定義。無い問題・言語は「自動採点未対応（manual_review）」

採点定義の書式は exercises/problems/001.toml などを参照。
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal

from core.grading.compare import SortKey, TableSpec

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = PROJECT_ROOT / "exercises" / "catalog"
PROBLEMS_DIR = PROJECT_ROOT / "exercises" / "problems"

LANGUAGES = ("python", "sql")
Strategy = Literal["table", "scalar", "manual_review"]

UNSUPPORTED_REASON = (
    "この問題の自動採点は未対応です（今後対応予定）。実行結果を見て自己確認してください。"
)

_SPEC_TOP_KEYS = {"id", "status", *LANGUAGES}
_SPEC_LANG_KEYS = {
    "strategy",
    "reference",
    "rows",
    "n",
    "sort_keys",
    "column_order",
    "float_decimals",
    "reason",
}
_ROW_MODES = ("unordered", "ordered", "sorted", "subset_n", "top_n")


@dataclass(frozen=True)
class GradingSpec:
    strategy: Strategy
    reference: str | None = (
        None  # 採点基準を生成するコード（subset_n/top_n では件数制限なしの全結果）
    )
    table: TableSpec | None = None
    float_decimals: int = 6
    reason: str = ""


UNSUPPORTED = GradingSpec("manual_review", reason=UNSUPPORTED_REASON)


@dataclass(frozen=True)
class Exercise:
    id: str
    statements: dict[str, str]
    notes: dict[str, list[str]]
    depends_on: tuple[str, ...]
    grading: dict[str, GradingSpec]
    status: str  # verified | draft | unsupported（採点定義なし）
    source_ids: dict[str, str] = field(default_factory=dict)

    def title(self, language: str, width: int = 40) -> str:
        first = self.statements[language].splitlines()[0]
        return first if len(first) <= width else first[:width] + "…"


def _parse_language(lang: str, data: dict[str, Any]) -> GradingSpec:
    unknown = set(data) - _SPEC_LANG_KEYS
    if unknown:
        raise ValueError(f"[{lang}] 不明なキー: {', '.join(sorted(unknown))}")
    strategy = data.get("strategy")
    if strategy == "manual_review":
        return GradingSpec("manual_review", reason=data.get("reason", UNSUPPORTED_REASON))
    if strategy not in ("table", "scalar"):
        raise ValueError(f"[{lang}] strategy の値が不正: {strategy!r}")
    reference = data.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError(f"[{lang}] reference（参照結果を作るコード）が必要")
    float_decimals = int(data.get("float_decimals", 6))
    if strategy == "scalar":
        return GradingSpec("scalar", reference=reference.strip(), float_decimals=float_decimals)

    rows = data.get("rows", "unordered")
    if rows not in _ROW_MODES:
        raise ValueError(f"[{lang}] rows の値が不正: {rows!r}")
    sort_keys = tuple(
        SortKey(k["column"], bool(k.get("descending", False))) for k in data.get("sort_keys", [])
    )
    table = TableSpec(
        rows=rows,
        sort_keys=sort_keys,
        n=data.get("n"),
        column_order=bool(data.get("column_order", True)),
        float_decimals=float_decimals,
    )
    return GradingSpec(
        "table", reference=reference.strip(), table=table, float_decimals=float_decimals
    )


def parse_spec(data: dict[str, Any], expected_id: str) -> tuple[str, dict[str, GradingSpec]]:
    """TOMLの内容を検証して (status, {language: GradingSpec}) を返す。"""
    unknown = set(data) - _SPEC_TOP_KEYS
    if unknown:
        raise ValueError(f"不明なキーまたは言語: {', '.join(sorted(unknown))}")
    if data.get("id") != expected_id:
        raise ValueError(f"id がファイル名と一致しない: {data.get('id')!r} != {expected_id!r}")
    status = data.get("status")
    if status not in ("verified", "draft"):
        raise ValueError(f"status は verified / draft のいずれか: {status!r}")
    grading = {
        lang: _parse_language(lang, data[lang]) if lang in data else UNSUPPORTED
        for lang in LANGUAGES
    }
    return status, grading


def load_exercises(
    catalog_dir: Path = CATALOG_DIR, problems_dir: Path = PROBLEMS_DIR
) -> list[Exercise]:
    problems = json.loads((catalog_dir / "problems.json").read_text(encoding="utf-8"))
    exercises = []
    for p in problems["problems"]:
        spec_path = problems_dir / f"{p['id']}.toml"
        if spec_path.exists():
            try:
                status, grading = parse_spec(
                    tomllib.loads(spec_path.read_text(encoding="utf-8")), p["id"]
                )
            except ValueError as exc:
                raise ValueError(f"{spec_path.name}: {exc}") from exc
        else:
            status, grading = "unsupported", dict.fromkeys(LANGUAGES, UNSUPPORTED)
        exercises.append(
            Exercise(
                id=p["id"],
                statements={lang: p[lang]["statement"] for lang in LANGUAGES},
                notes={lang: p[lang]["notes"] for lang in LANGUAGES},
                depends_on=tuple(p["depends_on"]),
                grading=grading,
                status=status,
                source_ids={lang: p[lang]["source_id"] for lang in LANGUAGES},
            )
        )
    return exercises


@cache
def _default_index() -> dict[str, Exercise]:
    return {e.id: e for e in load_exercises()}


def get_exercise(exercise_id: str) -> Exercise:
    return _default_index()[exercise_id]


def load_answers(catalog_dir: Path = CATALOG_DIR) -> dict[str, dict[str, list[str]]]:
    """{問題ID: {言語: 模範解答コードのリスト}}。学習UIでは明示的な操作があるまで表示しない。"""
    answers = json.loads((catalog_dir / "answers.json").read_text(encoding="utf-8"))
    return {
        a["id"]: {lang: a[lang]["code_cells"] for lang in LANGUAGES} for a in answers["answers"]
    }
