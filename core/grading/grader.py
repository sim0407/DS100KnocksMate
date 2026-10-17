"""採点: 学習者コードの実行 → 参照結果の取得 → 比較 → passed / failed / manual_review / error。

「実行」と「採点」は別操作（実行だけでは正解にならない）。採点時は表示用より大きな行数上限で
実行し、参照結果は模範解答（採点定義の reference）を同じランナーで実行して得る。
参照結果を作れない・比較できない場合は passed にせず manual_review を返す。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from core.execution.results import ScalarResult, TableResult
from core.exercises.catalog import Exercise
from core.grading.compare import compare_scalars, compare_tables

GRADE_MAX_ROWS = 300_000
GRADE_TIMEOUT_SEC = 20.0

GradeStatus = Literal["passed", "failed", "manual_review", "error"]
# (code, max_rows, timeout_sec) -> ランナーの応答辞書（core.execution.*_runner と同じ形）
Runner = Callable[[str, int, float], dict]

NO_RESULT_MESSAGE = "採点する結果がありません。コードの最後の行に、結果を返す式（例: df_receipt.head(10)）を書いてください。"
_RESULT_LABEL = {
    "table": "表",
    "scalar": "1つの値",
    "text": "表でも値でもないオブジェクト",
    "none": "None",
}


@dataclass(frozen=True)
class GradeResult:
    status: GradeStatus
    feedback: list[str] = field(default_factory=list)


class ReferenceCache:
    """参照結果のキャッシュ（言語・問題・参照コードごと）。アプリのプロセス内で共有する。"""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str, str], dict] = {}

    def get_or_run(self, key: tuple[str, str, str], run: Callable[[], dict | None]) -> dict | None:
        if key not in self._data:
            value = run()
            if value is None:
                return None
            self._data[key] = value
        return self._data[key]


def describe_error(response: dict) -> str:
    error = response.get("error") or {}
    message = error.get("message") or "不明なエラー"
    if response.get("status") == "error":
        where = f"（{error['lineno']}行目）" if error.get("lineno") else ""
        return f"{error.get('type', 'Error')}{where}: {message}"
    return message


def _table(result: dict) -> TableResult:
    return TableResult(
        columns=list(result["columns"]),
        rows=result["rows"],
        kinds=list(result["kinds"]),
        row_count=int(result["row_count"]),
        truncated=bool(result["truncated"]),
    )


def grade(
    exercise: Exercise, language: str, code: str, runner: Runner, cache: ReferenceCache
) -> GradeResult:
    spec = exercise.grading[language]
    if spec.strategy == "manual_review":
        return GradeResult("manual_review", [spec.reason])

    learner = runner(code, GRADE_MAX_ROWS, GRADE_TIMEOUT_SEC)
    if learner.get("status") != "ok":
        return GradeResult("error", [describe_error(learner)])
    result = learner.get("result")
    if result is None:
        return GradeResult("error", [NO_RESULT_MESSAGE])

    def run_reference() -> dict | None:
        response = runner(spec.reference or "", GRADE_MAX_ROWS, GRADE_TIMEOUT_SEC)
        ref = response.get("result")
        if response.get("status") != "ok" or ref is None or ref.get("truncated"):
            return None
        return ref

    reference = cache.get_or_run((language, exercise.id, spec.reference or ""), run_reference)
    if reference is None:
        return GradeResult(
            "manual_review",
            [
                "参照結果を生成できなかったため自動採点できません（アプリ側の問題の可能性があります）。"
            ],
        )

    expected_type = "table" if spec.strategy == "table" else "scalar"
    if result.get("type") != expected_type or reference.get("type") != expected_type:
        want = _RESULT_LABEL[expected_type]
        got = _RESULT_LABEL.get(result.get("type", ""), "不明")
        return GradeResult("failed", [f"{want}の形で結果を返してください（実際: {got}）"])

    if spec.strategy == "table":
        actual = _table(result)
        if actual.truncated:
            return GradeResult(
                "failed", [f"結果の行数が多すぎます（実際: {actual.row_count:,}行）"]
            )
        comparison = compare_tables(_table(reference), actual, spec.table)
    else:
        comparison = compare_scalars(
            ScalarResult(reference["value"], reference["kind"]),
            ScalarResult(result["value"], result["kind"]),
            spec.float_decimals,
        )

    if not comparison.gradable:
        return GradeResult("manual_review", comparison.reasons)
    if comparison.passed:
        return GradeResult("passed", ["正解です！"])
    return GradeResult("failed", comparison.reasons)
