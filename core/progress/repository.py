"""学習履歴（草稿・実行/採点の記録・進捗）を SQLite に保存する。

- exercise_status: 問題×言語ごとの最新状態（草稿コード、状態、初回正解日時など）
- attempts:        実行・採点の履歴（実行では grading_status は NULL）

状態: 行なし=not_started / in_progress / passed。一度 passed になったら後の不正解で戻さない
（直近の採点結果は last_grade_status に残す）。復習フラグ・ヒントを見た段階は状態とは別属性。
接続は操作ごとに開き、各操作は1トランザクション（Streamlit の複数スレッドから安全に使うため）。
スキーマは PRAGMA user_version で管理し、MIGRATIONS を順に適用する。
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

LANGUAGES = ("python", "sql")
MAX_CODE_CHARS = 200_000

MIGRATIONS: list[str] = [
    # v1
    """
    CREATE TABLE exercise_status (
        exercise_id       TEXT NOT NULL,
        language          TEXT NOT NULL CHECK (language IN ('python', 'sql')),
        state             TEXT NOT NULL CHECK (state IN ('not_started', 'in_progress', 'passed')),
        last_code         TEXT NOT NULL DEFAULT '',
        needs_review      INTEGER NOT NULL DEFAULT 0,
        last_grade_status TEXT,
        grade_count       INTEGER NOT NULL DEFAULT 0,
        first_passed_at   TEXT,
        last_attempted_at TEXT,
        updated_at        TEXT NOT NULL,
        PRIMARY KEY (exercise_id, language)
    );
    CREATE TABLE attempts (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        exercise_id      TEXT NOT NULL,
        language         TEXT NOT NULL,
        code             TEXT NOT NULL,
        mode             TEXT NOT NULL CHECK (mode IN ('run', 'grade')),
        execution_status TEXT NOT NULL,
        grading_status   TEXT,
        feedback_summary TEXT,
        created_at       TEXT NOT NULL
    );
    CREATE INDEX attempts_by_exercise ON attempts (exercise_id, language, id);
    """,
    # v2: ヒント・解答例をどこまで見たか（0: なし / 1: 使う関数 / 2: 骨組み / 3: 解答例）
    """
    ALTER TABLE exercise_status ADD COLUMN hint_level INTEGER NOT NULL DEFAULT 0;
    """,
]
SCHEMA_VERSION = len(MIGRATIONS)


@dataclass(frozen=True)
class ExerciseStatus:
    exercise_id: str
    language: str
    state: str
    last_code: str
    needs_review: bool
    last_grade_status: str | None
    grade_count: int
    first_passed_at: str | None
    last_attempted_at: str | None
    updated_at: str
    hint_level: int = 0


@dataclass(frozen=True)
class Attempt:
    id: int
    exercise_id: str
    language: str
    code: str
    mode: str
    execution_status: str
    grading_status: str | None
    feedback_summary: str | None
    created_at: str


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class ProgressRepository:
    def __init__(self, path: str | Path, now: Callable[[], dt.datetime] = _utc_now) -> None:
        self.path = Path(path)
        self._now = now
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    # ------------------------------------------------------------ 接続・マイグレーション

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # 成功で commit、例外で rollback
                yield conn
        finally:
            conn.close()

    def _migrate(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"学習履歴DBの版({version})がアプリ({SCHEMA_VERSION})より新しい: {self.path}"
                )
            for index in range(version, SCHEMA_VERSION):
                conn.executescript(
                    "BEGIN;" + MIGRATIONS[index] + f"PRAGMA user_version = {index + 1};COMMIT;"
                )

    def _timestamp(self) -> str:
        return self._now().astimezone(dt.UTC).isoformat(timespec="seconds")

    @staticmethod
    def _validate(language: str, code: str | None = None) -> None:
        if language not in LANGUAGES:
            raise ValueError(f"未対応の言語: {language!r}")
        if code is not None and len(code) > MAX_CODE_CHARS:
            raise ValueError(f"コードが長すぎます（上限 {MAX_CODE_CHARS} 文字）")

    def _ensure_row(self, conn: sqlite3.Connection, exercise_id: str, language: str, now: str):
        conn.execute(
            "INSERT OR IGNORE INTO exercise_status (exercise_id, language, state, updated_at)"
            " VALUES (?, ?, 'not_started', ?)",
            (exercise_id, language, now),
        )

    # ------------------------------------------------------------ 書き込み

    def save_draft(self, exercise_id: str, language: str, code: str) -> None:
        self._validate(language, code)
        now = self._timestamp()
        with self._connect() as conn:
            self._ensure_row(conn, exercise_id, language, now)
            conn.execute(
                "UPDATE exercise_status SET last_code = ?, updated_at = ?,"
                " state = CASE WHEN state = 'passed' THEN 'passed' ELSE 'in_progress' END"
                " WHERE exercise_id = ? AND language = ?",
                (code, now, exercise_id, language),
            )

    def record_run(self, exercise_id: str, language: str, code: str, execution_status: str) -> None:
        self._record(exercise_id, language, code, "run", execution_status, None, None)

    def record_grade(
        self,
        exercise_id: str,
        language: str,
        code: str,
        execution_status: str,
        grading_status: str,
        feedback_summary: str,
    ) -> None:
        self._record(
            exercise_id, language, code, "grade", execution_status, grading_status, feedback_summary
        )

    def _record(
        self,
        exercise_id: str,
        language: str,
        code: str,
        mode: str,
        execution_status: str,
        grading_status: str | None,
        feedback_summary: str | None,
    ) -> None:
        self._validate(language, code)
        now = self._timestamp()
        passed = grading_status == "passed"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO attempts (exercise_id, language, code, mode, execution_status,"
                " grading_status, feedback_summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    exercise_id,
                    language,
                    code,
                    mode,
                    execution_status,
                    grading_status,
                    feedback_summary,
                    now,
                ),
            )
            self._ensure_row(conn, exercise_id, language, now)
            conn.execute(
                "UPDATE exercise_status SET"
                " last_code = ?, last_attempted_at = ?, updated_at = ?,"
                " state = CASE WHEN state = 'passed' OR ? THEN 'passed' ELSE 'in_progress' END,"
                " first_passed_at = CASE WHEN first_passed_at IS NULL AND ? THEN ?"
                "   ELSE first_passed_at END,"
                " last_grade_status = COALESCE(?, last_grade_status),"
                " grade_count = grade_count + ?"
                " WHERE exercise_id = ? AND language = ?",
                (
                    code,
                    now,
                    now,
                    passed,
                    passed,
                    now,
                    grading_status,
                    1 if mode == "grade" else 0,
                    exercise_id,
                    language,
                ),
            )

    def reveal_hint(self, exercise_id: str, language: str, level: int) -> None:
        """ヒント・解答例を見た段階を記録する（下がらない）。正解・挑戦中の状態は変えない。"""
        self._validate(language)
        now = self._timestamp()
        with self._connect() as conn:
            self._ensure_row(conn, exercise_id, language, now)
            conn.execute(
                "UPDATE exercise_status SET hint_level = MAX(hint_level, ?), updated_at = ?"
                " WHERE exercise_id = ? AND language = ?",
                (int(level), now, exercise_id, language),
            )

    def set_needs_review(self, exercise_id: str, language: str, flag: bool) -> None:
        self._validate(language)
        now = self._timestamp()
        with self._connect() as conn:
            self._ensure_row(conn, exercise_id, language, now)
            conn.execute(
                "UPDATE exercise_status SET needs_review = ?, updated_at = ?"
                " WHERE exercise_id = ? AND language = ?",
                (int(flag), now, exercise_id, language),
            )

    # ------------------------------------------------------------ 読み出し

    @staticmethod
    def _status(row: sqlite3.Row) -> ExerciseStatus:
        data = dict(row)
        data["needs_review"] = bool(data["needs_review"])
        return ExerciseStatus(**data)

    def get_status(self, exercise_id: str, language: str) -> ExerciseStatus | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM exercise_status WHERE exercise_id = ? AND language = ?",
                (exercise_id, language),
            ).fetchone()
        return self._status(row) if row else None

    def list_statuses(self) -> dict[tuple[str, str], ExerciseStatus]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM exercise_status").fetchall()
        return {(r["exercise_id"], r["language"]): self._status(r) for r in rows}

    def attempts(self, exercise_id: str, language: str, limit: int = 20) -> list[Attempt]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM attempts WHERE exercise_id = ? AND language = ?"
                " ORDER BY id DESC LIMIT ?",
                (exercise_id, language, limit),
            ).fetchall()
        return [Attempt(**dict(r)) for r in rows]

    def summary(self) -> dict[str, dict[str, int]]:
        """{言語: {状態: 件数}}（not_started の行は数えない）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT language, state, count(*) AS n FROM exercise_status"
                " WHERE state != 'not_started' GROUP BY language, state"
            ).fetchall()
        result: dict[str, dict[str, int]] = {}
        for r in rows:
            result.setdefault(r["language"], {})[r["state"]] = r["n"]
        return result
