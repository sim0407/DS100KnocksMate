"""UI（Streamlit）から使うアプリケーション操作。UIフレームワークには依存しない。

- 草稿の保存・復元、実行（表示用の行数上限）、採点、進捗の取得
- 学習者のPythonは隔離ワーカー、SQLは読み取り専用DBで実行する（このプロセスでは実行しない）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core.execution.python_runner import run_python
from core.execution.sql_runner import run_sql
from core.exercises.catalog import PROJECT_ROOT, Exercise, load_exercises
from core.exercises.hints import Hints, build_hints
from core.grading.grader import ExecOptions, GradeResult, ReferenceCache, Runner, grade, options_for
from core.progress.repository import ExerciseStatus, ProgressRepository

DISPLAY_MAX_ROWS = 200
RUN_TIMEOUT_SEC = 10.0

DEFAULT_WORKER_URL = "http://worker:8000"
DEFAULT_DB_DSN = "host=db dbname=dsdojo_db user=knocks_learner password=knocks-learner-readonly"
DEFAULT_PROGRESS_DB = PROJECT_ROOT / "var" / "progress.sqlite3"


@dataclass
class TrainerService:
    exercises: list[Exercise]
    runners: dict[str, Runner]
    progress: ProgressRepository
    cache: ReferenceCache

    def __post_init__(self) -> None:
        self._index = {e.id: e for e in self.exercises}
        self._order = [e.id for e in self.exercises]

    @classmethod
    def from_env(cls) -> TrainerService:
        worker_url = os.environ.get("KNOCKS_WORKER_URL", DEFAULT_WORKER_URL)
        dsn = os.environ.get("KNOCKS_DB_DSN", DEFAULT_DB_DSN)
        progress_path = Path(os.environ.get("KNOCKS_PROGRESS_DB", DEFAULT_PROGRESS_DB))

        def python_runner(
            code: str, max_rows: int, timeout_sec: float, options: ExecOptions
        ) -> dict:
            return run_python(
                code,
                url=worker_url,
                max_rows=max_rows,
                timeout_sec=timeout_sec,
                setup=options.setup,
                collect_files=options.collect_files,
            )

        def sql_runner(code: str, max_rows: int, timeout_sec: float, options: ExecOptions) -> dict:
            return run_sql(
                code,
                dsn=dsn,
                max_rows=max_rows,
                timeout_sec=timeout_sec,
                writable=options.writable,
                setup=options.setup,
                stdin_query=options.stdin_query,
            )

        return cls(
            exercises=load_exercises(),
            runners={"python": python_runner, "sql": sql_runner},
            progress=ProgressRepository(progress_path),
            cache=ReferenceCache(),
        )

    # ------------------------------------------------------------ 問題

    def exercise(self, exercise_id: str) -> Exercise:
        return self._index[exercise_id]

    def neighbors(
        self, exercise_id: str, order: list[str] | None = None
    ) -> tuple[str | None, str | None]:
        """前後の問題ID。order を渡すとその並び（絞り込み後の一覧など）の中で探す。"""
        order = order or self._order
        i = order.index(exercise_id)
        prev_id = order[i - 1] if i > 0 else None
        next_id = order[i + 1] if i + 1 < len(order) else None
        return prev_id, next_id

    # ------------------------------------------------------------ 草稿・進捗

    def draft(self, exercise_id: str, language: str) -> str:
        status = self.progress.get_status(exercise_id, language)
        return status.last_code if status else ""

    def save_draft(self, exercise_id: str, language: str, code: str) -> None:
        self.progress.save_draft(exercise_id, language, code)

    def hints(self, exercise_id: str, language: str) -> Hints:
        return build_hints(exercise_id, language)

    def reveal_hint(self, exercise_id: str, language: str, level: int) -> None:
        self.progress.reveal_hint(exercise_id, language, level)

    def statuses(self) -> dict[tuple[str, str], ExerciseStatus]:
        return self.progress.list_statuses()

    def passed_count(self, language: str) -> int:
        return self.progress.summary().get(language, {}).get("passed", 0)

    def auto_gradable_ids(self, language: str) -> list[str]:
        return [e.id for e in self.exercises if e.grading[language].strategy != "manual_review"]

    def overview(self) -> list[dict]:
        """進捗一覧用: 問題ごとの言語別の状態・自動採点対応・復習フラグ。"""
        statuses = self.statuses()
        rows = []
        for e in self.exercises:
            row: dict = {"id": e.id, "title": e.title("python", 60)}
            for lang in ("python", "sql"):
                status = statuses.get((e.id, lang))
                row[f"{lang}_state"] = status.state if status else "not_started"
                row[f"{lang}_review"] = bool(status and status.needs_review)
                row[f"{lang}_auto"] = e.grading[lang].strategy != "manual_review"
                row[f"{lang}_hint"] = status.hint_level if status else 0
            rows.append(row)
        return rows

    # ------------------------------------------------------------ 実行・採点

    def run(self, exercise_id: str, language: str, code: str) -> dict:
        """実行して結果を返す（採点・合格判定には影響しない）。

        前の問題のデータ（setup）やテーブル作成の可否（writable）は採点と同じ条件にする。
        Python では出力先 data フォルダのファイルも返す（画面で確認できるように）。
        """
        spec = self.exercise(exercise_id).grading[language]
        options = options_for(spec, collect_files=language == "python")
        response = self.runners[language](code, DISPLAY_MAX_ROWS, RUN_TIMEOUT_SEC, options)
        self.progress.record_run(exercise_id, language, code, response.get("status", "error"))
        return response

    def grade(self, exercise_id: str, language: str, code: str) -> GradeResult:
        result = grade(
            self.exercise(exercise_id), language, code, self.runners[language], self.cache
        )
        self.progress.record_grade(
            exercise_id,
            language,
            code,
            "error" if result.status == "error" else "ok",
            result.status,
            "\n".join(result.feedback)[:2000],
        )
        return result
