"""core/grading/grader.py: 実行→参照結果→比較→採点結果、の流れ（ランナーは偽物）。"""

from core.exercises.catalog import Exercise, GradingSpec
from core.grading.compare import TableSpec
from core.grading.grader import ReferenceCache, grade


def table(columns, rows, *, truncated=False, row_count=None):
    return {
        "status": "ok",
        "result": {
            "type": "table",
            "columns": columns,
            "rows": rows,
            "kinds": ["integer"] * len(columns),
            "row_count": row_count if row_count is not None else len(rows),
            "truncated": truncated,
        },
        "stdout": "",
        "error": None,
    }


def failure(status, err_type, message, lineno=None):
    return {
        "status": status,
        "result": None,
        "stdout": "",
        "error": {"type": err_type, "message": message, "traceback": "", "lineno": lineno},
    }


class FakeRunner:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, code, max_rows, timeout_sec, options=None):
        self.calls.append(code)
        return self.responses[code]


UNIVERSE = table(["a"], [[1], [2], [3], [4]])


def exercise(spec):
    return Exercise(
        id="001",
        statements={"python": "問", "sql": "問"},
        notes={"python": [], "sql": []},
        depends_on=(),
        grading={"python": spec, "sql": spec},
        status="verified",
    )


SUBSET2 = exercise(GradingSpec("table", reference="REF", table=TableSpec(rows="subset_n", n=2)))


def test_passed():
    runner = FakeRunner({"REF": UNIVERSE, "mine": table(["a"], [[3], [1]])})
    r = grade(SUBSET2, "python", "mine", runner, ReferenceCache())
    assert r.status == "passed"


def test_failed_with_reasons():
    runner = FakeRunner({"REF": UNIVERSE, "mine": table(["a"], [[1], [2], [3]])})
    r = grade(SUBSET2, "python", "mine", runner, ReferenceCache())
    assert r.status == "failed"
    assert any("行数" in f for f in r.feedback)


def test_learner_error_is_error_status_with_message_and_line():
    runner = FakeRunner({"mine": failure("error", "NameError", "name 'x' is not defined", 2)})
    r = grade(SUBSET2, "python", "mine", runner, ReferenceCache())
    assert r.status == "error"
    assert "NameError" in r.feedback[0]
    assert "2行目" in r.feedback[0]
    assert runner.calls == ["mine"]  # 参照は実行しない


def test_learner_timeout_is_error():
    runner = FakeRunner({"mine": failure("timeout", "timeout", "制限時間（20秒）を超えました")})
    r = grade(SUBSET2, "python", "mine", runner, ReferenceCache())
    assert r.status == "error"
    assert "制限時間" in r.feedback[0]


def test_no_last_expression_guides_learner():
    runner = FakeRunner({"mine": {"status": "ok", "result": None, "stdout": "", "error": None}})
    r = grade(SUBSET2, "python", "mine", runner, ReferenceCache())
    assert r.status == "error"
    assert "最後" in r.feedback[0]


def test_scalar_where_table_expected_fails():
    scalar = {"status": "ok", "result": {"type": "scalar", "value": 1, "kind": "integer"}}
    runner = FakeRunner({"REF": UNIVERSE, "mine": scalar})
    r = grade(SUBSET2, "python", "mine", runner, ReferenceCache())
    assert r.status == "failed"
    assert "表" in r.feedback[0]


def test_truncated_learner_result_fails_with_row_count():
    big = table(["a"], [[1], [2]], truncated=True, row_count=999_999)
    runner = FakeRunner({"REF": UNIVERSE, "mine": big})
    r = grade(SUBSET2, "python", "mine", runner, ReferenceCache())
    assert r.status == "failed"
    assert "999999" in r.feedback[0] or "999,999" in r.feedback[0]


def test_manual_review_spec_does_not_claim_pass():
    ex = exercise(GradingSpec("manual_review", reason="この問題の自動採点は未対応です"))
    runner = FakeRunner({})
    r = grade(ex, "sql", "SELECT 1", runner, ReferenceCache())
    assert r.status == "manual_review"
    assert "未対応" in r.feedback[0]
    assert runner.calls == []


def test_reference_failure_is_manual_review_not_pass():
    runner = FakeRunner(
        {"REF": failure("error", "KeyError", "boom"), "mine": table(["a"], [[1], [2]])}
    )
    r = grade(SUBSET2, "python", "mine", runner, ReferenceCache())
    assert r.status == "manual_review"


def test_reference_is_cached_per_language_and_exercise():
    runner = FakeRunner({"REF": UNIVERSE, "mine": table(["a"], [[1], [2]])})
    cache = ReferenceCache()
    grade(SUBSET2, "python", "mine", runner, cache)
    grade(SUBSET2, "python", "mine", runner, cache)
    assert runner.calls.count("REF") == 1
    grade(SUBSET2, "sql", "mine", runner, cache)
    assert runner.calls.count("REF") == 2


def test_unavailable_runner_is_error():
    runner = FakeRunner({"mine": failure("unavailable", "WorkerUnavailable", "接続できません")})
    r = grade(SUBSET2, "python", "mine", runner, ReferenceCache())
    assert r.status == "error"


def test_scalar_strategy():
    ex = exercise(GradingSpec("scalar", reference="REF"))
    scalar = {"status": "ok", "result": {"type": "scalar", "value": 10, "kind": "integer"}}
    runner = FakeRunner({"REF": scalar, "mine": scalar})
    assert grade(ex, "python", "mine", runner, ReferenceCache()).status == "passed"


def test_scalar_strategy_accepts_one_by_one_table():
    """SQLの `SELECT COUNT(*) ...` は1行1列の表で返るため、値として扱う（列名は問わない）。"""
    ex = exercise(GradingSpec("scalar", reference="REF"))
    ref = table(["count"], [[104681]])
    mine = table(["cnt"], [[104681]])
    runner = FakeRunner({"REF": ref, "mine": mine})
    assert grade(ex, "sql", "mine", runner, ReferenceCache()).status == "passed"


def test_scalar_strategy_rejects_multi_row_table():
    ex = exercise(GradingSpec("scalar", reference="REF"))
    runner = FakeRunner({"REF": table(["n"], [[1]]), "mine": table(["n"], [[1], [2]])})
    result = grade(ex, "sql", "mine", runner, ReferenceCache())
    assert result.status == "failed"
    assert "1つの値" in result.feedback[0]


def test_alternative_reference_is_accepted():
    ex = exercise(GradingSpec("scalar", reference="REF", alternatives=("ALT",)))
    scalar = lambda v: {"status": "ok", "result": {"type": "scalar", "value": v, "kind": "float"}}  # noqa: E731
    runner = FakeRunner({"REF": scalar(1.0), "ALT": scalar(2.0), "mine": scalar(2.0)})
    assert grade(ex, "python", "mine", runner, ReferenceCache()).status == "passed"


def test_alternatives_not_run_when_primary_matches():
    ex = exercise(GradingSpec("scalar", reference="REF", alternatives=("ALT",)))
    scalar = {"status": "ok", "result": {"type": "scalar", "value": 1, "kind": "integer"}}
    runner = FakeRunner({"REF": scalar, "mine": scalar})
    grade(ex, "python", "mine", runner, ReferenceCache())
    assert "ALT" not in runner.calls


def test_feedback_comes_from_primary_when_all_fail():
    ex = exercise(GradingSpec("scalar", reference="REF", alternatives=("ALT",)))
    scalar = lambda v: {"status": "ok", "result": {"type": "scalar", "value": v, "kind": "integer"}}  # noqa: E731
    runner = FakeRunner({"REF": scalar(1), "ALT": scalar(2), "mine": scalar(3)})
    result = grade(ex, "python", "mine", runner, ReferenceCache())
    assert result.status == "failed"
    assert "3" in result.feedback[0]


def test_reference_cache_is_bounded():
    cache = ReferenceCache(max_entries=2)
    for i in range(3):
        cache.get_or_run(("python", f"{i:03d}", "REF"), lambda i=i: {"v": i})
    assert len(cache) == 2
    calls = []
    cache.get_or_run(("python", "000", "REF"), lambda: calls.append(1) or {"v": 0})
    assert calls == [1]  # 最も古いものから追い出される


# ---------------------------------------------------------------- 作ったデータ（artifact）・ファイル・性質


class RecordingRunner(FakeRunner):
    """コードの末尾に付け足された変数名/テーブル名で応答を決める。"""

    def __call__(self, code, max_rows, timeout_sec, options=None):
        self.calls.append((code, options))
        last = code.strip().splitlines()[-1]
        return self.responses.get(last, self.responses.get(code))


def test_artifact_is_appended_and_graded():
    spec = GradingSpec("table", reference="REF", table=TableSpec(), artifacts=("df_product_1",))
    runner = RecordingRunner({"df_product_1": table(["a"], [[1]])})
    result = grade(exercise(spec), "python", "df_product_1 = ...", runner, ReferenceCache())
    assert result.status == "passed"
    assert runner.calls[0][0] == "df_product_1 = ...\ndf_product_1"


def test_missing_artifact_message():
    spec = GradingSpec("table", reference="REF", table=TableSpec(), artifacts=("df_product_1",))
    missing = failure("error", "NameError", "name 'df_product_1' is not defined", 2)
    runner = RecordingRunner({"df_product_1": missing})
    result = grade(exercise(spec), "python", "x = 1", runner, ReferenceCache())
    assert result.status == "failed"
    assert "df_product_1" in result.feedback[0]
    assert "見つかりません" in result.feedback[0]


def test_sql_artifact_appends_select():
    spec = GradingSpec(
        "table", reference="REF", table=TableSpec(), artifacts=("product_1",), writable=True
    )
    runner = RecordingRunner({"SELECT * FROM product_1": table(["a"], [[1]])})
    result = grade(
        exercise(spec), "sql", "CREATE TABLE product_1 AS SELECT 1 AS a;", runner, ReferenceCache()
    )
    assert result.status == "passed"
    code, options = runner.calls[0]
    assert code.endswith("SELECT * FROM product_1")
    assert options.writable is True


def test_multiple_artifacts_all_must_match():
    spec = GradingSpec("table", reference="REF", table=TableSpec(), artifacts=("a", "b"))
    runner = RecordingRunner({"a": table(["x"], [[1]]), "b": table(["x"], [[2]])})
    assert grade(exercise(spec), "python", "...", runner, ReferenceCache()).status == "passed"


def test_setup_is_passed_to_runner():
    spec = GradingSpec("scalar", reference="REF", setup="df = 1")
    scalar = {"status": "ok", "result": {"type": "scalar", "value": 1, "kind": "integer"}}
    runner = RecordingRunner({"REF": scalar, "mine": scalar})
    grade(exercise(spec), "python", "mine", runner, ReferenceCache())
    assert all(options.setup == "df = 1" for _, options in runner.calls)


def b64(text):
    import base64

    return base64.b64encode(text.encode()).decode()


def test_file_strategy():
    from core.grading.files import FileFormat

    spec = GradingSpec("file", reference="REF", file_format=FileFormat())
    ok_file = {
        "path": "data/x.csv",
        "size": 1,
        "content_b64": b64("a,b\n1,2\n"),
        "truncated": False,
    }
    response = lambda files: {"status": "ok", "result": None, "files": files}  # noqa: E731
    runner = RecordingRunner(
        {"REF": response([ok_file]), "mine": response([ok_file]), "none": response([])}
    )
    assert grade(exercise(spec), "python", "mine", runner, ReferenceCache()).status == "passed"
    result = grade(exercise(spec), "python", "none", runner, ReferenceCache())
    assert result.status == "failed"
    assert "ファイル" in result.feedback[0]
    assert runner.calls[0][1].collect_files is True


def test_custom_validator_strategy():
    spec = GradingSpec(
        "custom",
        reference="REF",
        artifacts=("df_train", "df_test"),
        validator="train_test_split",
        validator_params={"test_ratio": 0.5},
    )
    runner = RecordingRunner(
        {
            "REF": table(["id"], [[1], [2]]),
            "df_train": table(["id"], [[1]]),
            "df_test": table(["id"], [[2]]),
        }
    )
    assert grade(exercise(spec), "python", "...", runner, ReferenceCache()).status == "passed"
