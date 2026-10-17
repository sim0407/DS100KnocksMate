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
from core.grading.grader import GradeResult, ReferenceCache, Runner, grade
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

        def python_runner(code: str, max_rows: int, timeout_sec: float) -> dict:
            return run_python(code, url=worker_url, max_rows=max_rows, timeout_sec=timeout_sec)

        def sql_runner(code: str, max_rows: int, timeout_sec: float) -> dict:
            return run_sql(code, dsn=dsn, max_rows=max_rows, timeout_sec=timeout_sec)

        return cls(
            exercises=load_exercises(),
            runners={"python": python_runner, "sql": sql_runner},
            progress=ProgressRepository(progress_path),
            cache=ReferenceCache(),
        )

    # ------------------------------------------------------------ 問題

    def exercise(self, exercise_id: str) -> Exercise:
        return self._index[exercise_id]

    def neighbors(self, exercise_id: str) -> tuple[str | None, str | None]:
        i = self._order.index(exercise_id)
        prev_id = self._order[i - 1] if i > 0 else None
        next_id = self._order[i + 1] if i + 1 < len(self._order) else None
        return prev_id, next_id

    # ------------------------------------------------------------ 草稿・進捗

    def draft(self, exercise_id: str, language: str) -> str:
        status = self.progress.get_status(exercise_id, language)
        return status.last_code if status else ""

    def save_draft(self, exercise_id: str, language: str, code: str) -> None:
        self.progress.save_draft(exercise_id, language, code)

    def statuses(self) -> dict[tuple[str, str], ExerciseStatus]:
        return self.progress.list_statuses()

    def passed_count(self, language: str) -> int:
        return self.progress.summary().get(language, {}).get("passed", 0)

    # ------------------------------------------------------------ 実行・採点

    def run(self, exercise_id: str, language: str, code: str) -> dict:
        """実行して結果を返す（採点・合格判定には影響しない）。"""
        response = self.runners[language](code, DISPLAY_MAX_ROWS, RUN_TIMEOUT_SEC)
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
