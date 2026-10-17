"""core/progress/repository.py: SQLiteによる草稿・実行/採点履歴・進捗の保存。"""

import datetime as dt
import sqlite3

import pytest

from core.progress.repository import SCHEMA_VERSION, ProgressRepository


class Clock:
    def __init__(self):
        self.t = dt.datetime(2026, 10, 18, 9, 0, tzinfo=dt.UTC)

    def __call__(self):
        self.t += dt.timedelta(seconds=1)
        return self.t


@pytest.fixture
def path(tmp_path):
    return tmp_path / "nested" / "progress.sqlite3"


@pytest.fixture
def repo(path):
    return ProgressRepository(path, now=Clock())


def test_creates_database_and_schema(path, repo):
    assert path.exists()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_reopening_is_idempotent(path, repo):
    repo.save_draft("001", "python", "x")
    again = ProgressRepository(path)
    assert again.get_status("001", "python").last_code == "x"


def test_unknown_status_is_none(repo):
    assert repo.get_status("001", "python") is None


def test_draft_survives_restart(path, repo):
    repo.save_draft("001", "python", "df_receipt.head(10)")
    restarted = ProgressRepository(path)
    status = restarted.get_status("001", "python")
    assert status.last_code == "df_receipt.head(10)"
    assert status.state == "in_progress"


def test_languages_are_independent(repo):
    repo.save_draft("001", "python", "py code")
    repo.save_draft("001", "sql", "SELECT 1")
    repo.record_grade("001", "python", "py code", "ok", "passed", "正解です！")
    assert repo.get_status("001", "python").state == "passed"
    assert repo.get_status("001", "sql").state == "in_progress"
    assert repo.get_status("001", "sql").last_code == "SELECT 1"


def test_run_records_attempt_without_grading(repo):
    repo.record_run("001", "sql", "SELECT 1", "ok")
    status = repo.get_status("001", "sql")
    assert status.state == "in_progress"
    assert status.last_attempted_at is not None
    assert status.last_grade_status is None
    (attempt,) = repo.attempts("001", "sql")
    assert attempt.mode == "run"
    assert attempt.execution_status == "ok"
    assert attempt.grading_status is None


def test_run_never_marks_passed(repo):
    """実行だけでは正解扱いにしない。"""
    repo.record_run("001", "python", "df_receipt.head(10)", "ok")
    assert repo.get_status("001", "python").state != "passed"


def test_failed_grade_keeps_in_progress(repo):
    repo.record_grade("002", "python", "c", "ok", "failed", "行数が違います")
    status = repo.get_status("002", "python")
    assert status.state == "in_progress"
    assert status.last_grade_status == "failed"
    assert status.first_passed_at is None


def test_passed_is_sticky_and_first_passed_at_is_kept(repo):
    repo.record_grade("003", "sql", "good", "ok", "passed", "正解です！")
    first = repo.get_status("003", "sql").first_passed_at
    repo.record_grade("003", "sql", "bad", "ok", "failed", "列が足りません")
    status = repo.get_status("003", "sql")
    assert status.state == "passed"
    assert status.first_passed_at == first
    assert status.last_grade_status == "failed"
    assert status.last_code == "bad"


def test_draft_after_pass_keeps_passed(repo):
    repo.record_grade("003", "sql", "good", "ok", "passed", "")
    repo.save_draft("003", "sql", "edited")
    assert repo.get_status("003", "sql").state == "passed"


def test_attempts_are_newest_first_and_limited(repo):
    for i in range(5):
        repo.record_run("001", "python", f"code{i}", "ok")
    attempts = repo.attempts("001", "python", limit=3)
    assert [a.code for a in attempts] == ["code4", "code3", "code2"]


def test_attempt_count_until_first_pass(repo):
    repo.record_grade("004", "python", "a", "ok", "failed", "")
    repo.record_grade("004", "python", "b", "error", "error", "")
    repo.record_grade("004", "python", "c", "ok", "passed", "")
    assert repo.get_status("004", "python").grade_count == 3


def test_needs_review_flag(repo):
    repo.set_needs_review("005", "python", True)
    assert repo.get_status("005", "python").needs_review is True
    assert repo.get_status("005", "python").state == "not_started"
    repo.set_needs_review("005", "python", False)
    assert repo.get_status("005", "python").needs_review is False


def test_list_statuses_and_summary(repo):
    repo.record_grade("001", "python", "a", "ok", "passed", "")
    repo.record_grade("002", "python", "a", "ok", "failed", "")
    repo.record_grade("001", "sql", "a", "ok", "passed", "")
    statuses = repo.list_statuses()
    assert set(statuses) == {("001", "python"), ("002", "python"), ("001", "sql")}
    assert repo.summary() == {
        "python": {"passed": 1, "in_progress": 1},
        "sql": {"passed": 1},
    }


def test_rejects_unknown_language(repo):
    with pytest.raises(ValueError):
        repo.save_draft("001", "ruby", "x")


def test_rejects_oversized_code(repo):
    with pytest.raises(ValueError):
        repo.save_draft("001", "python", "x" * 200_001)


def test_timestamps_are_utc_iso(repo):
    repo.record_grade("001", "python", "a", "ok", "passed", "")
    status = repo.get_status("001", "python")
    assert status.first_passed_at.endswith("+00:00")


def test_wal_mode_enabled(path, repo):
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
