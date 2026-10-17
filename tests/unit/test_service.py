"""core/service.py: UIから使う操作（草稿・実行・採点・進捗）。ランナーは偽物。"""

import pytest

from core.exercises.catalog import load_exercises
from core.grading.grader import ReferenceCache
from core.progress.repository import ProgressRepository
from core.service import DISPLAY_MAX_ROWS, TrainerService


def table(rows):
    return {
        "status": "ok",
        "result": {
            "type": "table",
            "columns": ["a"],
            "rows": rows,
            "kinds": ["integer"],
            "row_count": len(rows),
            "truncated": False,
        },
        "stdout": "",
        "error": None,
    }


class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, code, max_rows, timeout_sec, options=None):
        self.calls.append((code, max_rows))
        if code == "boom":
            return {
                "status": "error",
                "result": None,
                "stdout": "",
                "error": {"type": "NameError", "message": "x", "lineno": 1},
            }
        if code in ("df_receipt", "SELECT * FROM receipt"):  # 001 の参照
            return table([[i] for i in range(20)])
        return table([[i] for i in range(10)])


@pytest.fixture
def service(tmp_path):
    return TrainerService(
        exercises=load_exercises(),
        runners={"python": FakeRunner(), "sql": FakeRunner()},
        progress=ProgressRepository(tmp_path / "p.sqlite3"),
        cache=ReferenceCache(),
    )


def test_exercise_list_and_lookup(service):
    assert len(service.exercises) == 100
    assert service.exercise("001").id == "001"


def test_draft_is_empty_then_saved(service):
    assert service.draft("001", "python") == ""
    service.save_draft("001", "python", "df_receipt.head(10)")
    assert service.draft("001", "python") == "df_receipt.head(10)"
    assert service.draft("001", "sql") == ""


def test_run_uses_display_row_limit_and_records_attempt(service):
    response = service.run("001", "python", "df_receipt.head(10)")
    assert response["status"] == "ok"
    assert service.runners["python"].calls == [("df_receipt.head(10)", DISPLAY_MAX_ROWS)]
    status = service.progress.get_status("001", "python")
    assert status.state == "in_progress"
    assert status.last_code == "df_receipt.head(10)"


def test_run_error_is_recorded(service):
    service.run("001", "python", "boom")
    (attempt,) = service.progress.attempts("001", "python")
    assert attempt.execution_status == "error"


def test_grade_records_result_and_progress(service):
    result = service.grade("001", "sql", "SELECT * FROM receipt LIMIT 10")
    assert result.status == "passed"
    assert service.progress.get_status("001", "sql").state == "passed"
    (attempt,) = service.progress.attempts("001", "sql")
    assert attempt.mode == "grade"
    assert attempt.grading_status == "passed"


def test_grade_error_records_error_execution_status(service):
    result = service.grade("001", "python", "boom")
    assert result.status == "error"
    (attempt,) = service.progress.attempts("001", "python")
    assert attempt.execution_status == "error"
    assert attempt.grading_status == "error"


def test_grade_unsupported_problem_is_manual_review_and_not_passed(service):
    result = service.grade("075", "python", "anything")
    assert result.status == "manual_review"
    assert service.progress.get_status("075", "python").state == "in_progress"


def test_progress_summary(service):
    service.grade("001", "python", "df_receipt.head(10)")
    assert service.passed_count("python") == 1
    assert service.passed_count("sql") == 0


def test_neighbors(service):
    assert service.neighbors("001") == (None, "002")
    assert service.neighbors("050") == ("049", "051")
    assert service.neighbors("100") == ("099", None)
    assert service.neighbors("005", ["001", "005", "009"]) == ("001", "009")


def test_overview_rows(service):
    service.grade("001", "python", "df_receipt.head(10)")
    service.save_draft("002", "sql", "SELECT")
    service.progress.set_needs_review("003", "python", True)
    rows = {r["id"]: r for r in service.overview()}
    assert len(rows) == 100
    assert rows["001"]["python_state"] == "passed"
    assert rows["001"]["sql_state"] == "not_started"
    assert rows["002"]["sql_state"] == "in_progress"
    assert rows["003"]["python_review"] is True
    assert rows["001"]["python_auto"] is True
    assert rows["075"]["python_auto"] is False
    assert rows["001"]["title"].startswith("レシート明細データ")


def test_auto_gradable_ids(service):
    ids = service.auto_gradable_ids("python")
    assert "001" in ids and "100" in ids and "075" not in ids and "020" not in ids


def test_hints_and_reveal(service):
    h = service.hints("023", "sql")
    assert "SUM" in h.functions
    service.reveal_hint("023", "sql", 1)
    service.reveal_hint("023", "sql", 3)
    rows = {r["id"]: r for r in service.overview()}
    assert rows["023"]["sql_hint"] == 3
    assert rows["023"]["python_hint"] == 0
