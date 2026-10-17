"""採点: 学習者コードの実行 → 参照結果の取得 → 比較 → passed / failed / manual_review / error。

「実行」と「採点」は別操作（実行だけでは正解にならない）。採点時は表示用より大きな行数上限で
実行し、参照結果は模範解答（採点定義の reference）を同じランナーで実行して得る。
参照結果を作れない・比較できない場合は passed にせず manual_review を返す。

採点対象:
- 既定: 最後の式（Python）/ 最後の SELECT（SQL）の結果
- artifacts: 作成した変数（Python）/ テーブル（SQL）。コードの末尾に名前 / SELECT * FROM 名前 を足して取り出す
- strategy="file": data フォルダ（Python）/ COPY ... TO STDOUT（SQL）に出力したファイル
- strategy="custom": 性質による採点（乱数を使う問題。core.grading.validators）
"""

from __future__ import annotations

import base64
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from core.execution.results import ScalarResult, TableResult
from core.exercises.catalog import Exercise, GradingSpec
from core.grading.compare import compare_scalars, compare_tables
from core.grading.files import compare_files
from core.grading.validators import VALIDATOR_ROLES, VALIDATORS

GRADE_MAX_ROWS = 300_000
GRADE_TIMEOUT_SEC = 20.0

GradeStatus = Literal["passed", "failed", "manual_review", "error"]


@dataclass(frozen=True)
class ExecOptions:
    """ランナーへの追加指定（採点定義から作る）。"""

    setup: str = ""
    writable: bool = False  # SQL のみ
    stdin_query: str = ""  # SQL のみ
    collect_files: bool = False  # Python のみ（data フォルダのファイルを返す）


# (code, max_rows, timeout_sec, options) -> ランナーの応答辞書（core.execution.*_runner と同じ形）
Runner = Callable[[str, int, float, ExecOptions], dict]

NO_RESULT_MESSAGE = "採点する結果がありません。コードの最後の行に、結果を返す式（例: df_receipt.head(10)）を書いてください。"
_RESULT_LABEL = {
    "table": "表",
    "scalar": "1つの値",
    "text": "表でも値でもないオブジェクト",
    "none": "None",
}
_REFERENCE_FAILED = (
    "参照結果を生成できなかったため自動採点できません（アプリ側の問題の可能性があります）。"
)


@dataclass(frozen=True)
class GradeResult:
    status: GradeStatus
    feedback: list[str] = field(default_factory=list)


class ReferenceCache:
    """参照結果のキャッシュ（言語・問題・参照コードごと）。アプリのプロセス内で共有する。

    参照結果は10万行規模になることがあるため、件数に上限を設け、古いものから捨てる（LRU）。
    """

    def __init__(self, max_entries: int = 4) -> None:
        self.max_entries = max_entries
        self._data: OrderedDict[tuple[str, str, str], dict] = OrderedDict()

    def __len__(self) -> int:
        return len(self._data)

    def get_or_run(self, key: tuple[str, str, str], run: Callable[[], dict | None]) -> dict | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        value = run()
        if value is None:
            return None
        self._data[key] = value
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)
        return value


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


def _as_scalar(result: dict) -> dict:
    """1行1列の表（SQLの `SELECT COUNT(*) ...` 等）は値として扱う。それ以外はそのまま。"""
    if result.get("type") == "table" and len(result["columns"]) == 1 and result["row_count"] == 1:
        return {"type": "scalar", "value": result["rows"][0][0], "kind": result["kinds"][0]}
    return result


def options_for(spec: GradingSpec, *, collect_files: bool = False) -> ExecOptions:
    return ExecOptions(
        setup=spec.setup,
        writable=spec.writable,
        stdin_query=spec.stdin_query,
        collect_files=collect_files,
    )


def with_artifact(code: str, artifact: str | None, language: str) -> str:
    """コードの末尾に、採点する変数/テーブルを取り出す行を足す。"""
    if artifact is None:
        return code
    if language == "sql":
        return f"{code.rstrip()}\n;\nSELECT * FROM {artifact}"
    return f"{code}\n{artifact}"


def _missing_artifact(response: dict, artifact: str, language: str) -> str | None:
    error = response.get("error") or {}
    message = error.get("message") or ""
    if language == "python" and error.get("type") == "NameError" and f"'{artifact}'" in message:
        return (
            f"変数 {artifact} が見つかりません。作成したデータを変数 {artifact} に入れてください。"
        )
    if language == "sql" and error.get("type") == "UndefinedTable" and artifact in message:
        return f"テーブル {artifact} が見つかりません。CREATE TABLE {artifact} AS ... で作成してください。"
    return None


def _evaluate(spec: GradingSpec, result: dict, reference: dict) -> GradeResult:
    """学習者の結果を1つの参照結果と比較する。"""
    expected_type = "table" if spec.strategy == "table" else "scalar"
    if expected_type == "scalar":
        result, reference = _as_scalar(result), _as_scalar(reference)
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


class _Grading:
    """1回の採点（問題・言語・学習者コード）の実行をまとめる。"""

    def __init__(
        self, exercise: Exercise, language: str, code: str, runner: Runner, cache: ReferenceCache
    ) -> None:
        self.exercise, self.language, self.code = exercise, language, code
        self.runner, self.cache = runner, cache
        self.spec = exercise.grading[language]

    def run(self, code: str, *, collect_files: bool = False) -> dict:
        options = options_for(self.spec, collect_files=collect_files)
        return self.runner(code, GRADE_MAX_ROWS, GRADE_TIMEOUT_SEC, options)

    def learner(
        self, artifact: str | None, *, collect_files: bool = False
    ) -> tuple[dict | None, GradeResult | None]:
        """(学習者の応答, エラー時の採点結果)。"""
        response = self.run(
            with_artifact(self.code, artifact, self.language), collect_files=collect_files
        )
        if response.get("status") != "ok":
            if artifact is not None:
                missing = _missing_artifact(response, artifact, self.language)
                if missing:
                    return None, GradeResult("failed", [missing])
            return None, GradeResult("error", [describe_error(response)])
        return response, None

    def reference(
        self, code: str, artifact: str | None, *, collect_files: bool = False
    ) -> dict | None:
        full = with_artifact(code, artifact, self.language)

        def run() -> dict | None:
            response = self.run(full, collect_files=collect_files)
            if response.get("status") != "ok":
                return None
            if collect_files:
                return response
            result = response.get("result")
            if result is None or result.get("truncated"):
                return None
            return result

        return self.cache.get_or_run((self.language, self.exercise.id, full), run)


def _grade_values(g: _Grading) -> GradeResult:
    """table / scalar: 最後の結果（または artifacts の各データ）を参照結果と比べる。"""
    spec = g.spec
    targets = spec.artifacts or (None,)
    for artifact in targets:
        response, error = g.learner(artifact)
        if error:
            return error
        result = response.get("result")
        if result is None:
            return GradeResult("error", [NO_RESULT_MESSAGE])

        reference = g.reference(spec.reference or "", artifact)
        if reference is None:
            return GradeResult("manual_review", [_REFERENCE_FAILED])
        outcome = _evaluate(spec, result, reference)
        if outcome.status == "failed":
            # 許容する別の参照（ddof の違い・表記の違いなど）のどれかに一致すれば正解
            for alternative in spec.alternatives:
                alt_reference = g.reference(alternative, artifact)
                if (
                    alt_reference is not None
                    and _evaluate(spec, result, alt_reference).status == "passed"
                ):
                    outcome = GradeResult("passed", ["正解です！"])
                    break
        if outcome.status != "passed":
            if artifact is not None and len(targets) > 1:
                outcome = GradeResult(
                    outcome.status, [f"{artifact}: {r}" for r in outcome.feedback]
                )
            return outcome
    return GradeResult("passed", ["正解です！"])


def _decoded_files(response: dict) -> list[tuple[str, bytes]]:
    return [(f["path"], base64.b64decode(f["content_b64"])) for f in response.get("files") or []]


def _grade_file(g: _Grading) -> GradeResult:
    spec = g.spec
    response, error = g.learner(None, collect_files=True)
    if error:
        return error
    learner_files = _decoded_files(response)
    if not learner_files:
        where = "COPY ... TO STDOUT の出力" if g.language == "sql" else "出力先（./data）のファイル"
        return GradeResult("failed", [f"{where}が見つかりません。ファイルが出力されていません。"])

    reference = g.reference(spec.reference or "", None, collect_files=True)
    expected_files = _decoded_files(reference) if reference else []
    if len(expected_files) != 1:
        return GradeResult("manual_review", [_REFERENCE_FAILED])
    expected = expected_files[0][1]

    first_failure = None
    for path, content in learner_files:
        comparison = compare_files(expected, content, spec.file_format)
        if comparison.passed:
            return GradeResult("passed", ["正解です！"])
        if first_failure is None:
            label = "出力" if g.language == "sql" else path
            first_failure = [f"{label}: {r}" for r in comparison.reasons]
    return GradeResult("failed", first_failure or [])


def _grade_custom(g: _Grading) -> GradeResult:
    spec = g.spec
    tables: dict[str, TableResult] = {}
    for role, artifact in zip(VALIDATOR_ROLES[spec.validator], spec.artifacts, strict=True):
        response, error = g.learner(artifact)
        if error:
            return error
        result = response.get("result")
        if result is None or result.get("type") != "table":
            return GradeResult("failed", [f"{artifact} は表（DataFrame / テーブル）にしてください"])
        if result.get("truncated"):
            return GradeResult("failed", [f"{artifact} の行数が多すぎます"])
        tables[role] = _table(result)
    universe = g.reference(spec.reference or "", None)
    if universe is None or universe.get("type") != "table":
        return GradeResult("manual_review", [_REFERENCE_FAILED])
    comparison = VALIDATORS[spec.validator](tables, _table(universe), spec.validator_params)
    if comparison.passed:
        return GradeResult("passed", ["正解です！"])
    return GradeResult("failed", comparison.reasons)


def grade(
    exercise: Exercise, language: str, code: str, runner: Runner, cache: ReferenceCache
) -> GradeResult:
    spec = exercise.grading[language]
    if spec.strategy == "manual_review":
        return GradeResult("manual_review", [spec.reason])
    g = _Grading(exercise, language, code, runner, cache)
    if spec.strategy == "file":
        return _grade_file(g)
    if spec.strategy == "custom":
        return _grade_custom(g)
    return _grade_values(g)
