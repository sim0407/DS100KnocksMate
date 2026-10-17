"""Streamlit UI の統合テスト（AppTest でページを操作し、本物のワーカー・DBを使う）。

実行: docker compose --profile test run --rm --build tests
"""

import os
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "app" / "main.py")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.environ.get("KNOCKS_WORKER_URL") and os.environ.get("KNOCKS_DB_DSN")),
        reason="compose の tests サービスで実行",
    ),
]


@pytest.fixture
def progress_db(tmp_path, monkeypatch):
    path = tmp_path / "progress.sqlite3"
    monkeypatch.setenv("KNOCKS_PROGRESS_DB", str(path))
    # AppTest は独自部品（コードエディタ）を操作できないため、シンプル入力欄で操作する。
    # コードエディタ自体は tests/e2e/test_editor_browser.py（実ブラウザ）で確認する。
    monkeypatch.setenv("KNOCKS_EDITOR", "plain")
    return path


def start() -> AppTest:
    """アプリの起動（プロセス再起動に相当: キャッシュ済みサービスを破棄してから開く）。"""
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception
    return at


def texts(elements):
    return " ".join(str(e.value) for e in elements)


def test_initial_page(progress_db):
    at = start()
    assert at.subheader[0].value == "P-001"
    assert "レシート明細データ" in texts(at.markdown)
    assert at.text_area(key="code::001::python").value == ""


def test_python_run_then_grade(progress_db):
    at = start()
    at.text_area(key="code::001::python").input("df_receipt.head(10)").run()
    at.button(key="run").click().run()
    assert not at.exception
    assert len(at.dataframe) == 1
    assert len(at.dataframe[0].value) == 10
    assert at.success == []  # 実行だけでは正解にならない

    at.button(key="grade").click().run()
    assert not at.exception
    assert "正解です" in texts(at.success)
    assert "Python 正解: 1 / 100" in str(at.sidebar.get("progress")[0].proto)


def test_sql_run_then_grade_after_language_switch(progress_db):
    at = start()
    at.radio(key="language").set_value("sql").run()
    assert at.subheader[0].value == "S-001"
    at.text_area(key="code::001::sql").input("SELECT * FROM receipt LIMIT 10;").run()
    at.button(key="run").click().run()
    assert len(at.dataframe[0].value) == 10
    at.button(key="grade").click().run()
    assert "正解です" in texts(at.success)


def test_wrong_answer_feedback(progress_db):
    at = start()
    at.text_area(key="code::001::python").input("df_receipt.head(5)").run()
    at.button(key="grade").click().run()
    assert "不正解" in texts(at.error)
    assert "行数" in texts(at.error)


def test_python_error_is_shown(progress_db):
    at = start()
    at.text_area(key="code::001::python").input("x = 1\n1 / 0").run()
    at.button(key="run").click().run()
    assert "ZeroDivisionError" in texts(at.error)
    assert "2行目" in texts(at.error)


def test_sql_update_is_rejected(progress_db):
    at = start()
    at.radio(key="language").set_value("sql").run()
    at.text_area(key="code::001::sql").input("DELETE FROM receipt").run()
    at.button(key="run").click().run()
    assert "SELECT" in texts(at.error)


def test_next_and_unsupported_problem(progress_db):
    at = start()
    at.button(key="next").click().run()
    assert at.subheader[0].value == "P-002"
    at.selectbox(key="exercise_id").set_value("075").run()
    assert at.subheader[0].value == "P-075"
    assert "自動採点できません" in texts(at.warning)


def test_draft_and_pass_survive_restart(progress_db):
    at = start()
    at.text_area(key="code::001::python").input("df_receipt.head(10)").run()
    at.button(key="grade").click().run()
    at.radio(key="language").set_value("sql").run()
    at.text_area(key="code::001::sql").input("SELECT 1").run()

    restarted = start()
    assert restarted.text_area(key="code::001::python").value == "df_receipt.head(10)"
    assert "✅ 001" in restarted.selectbox(key="exercise_id").format_func("001")
    restarted.radio(key="language").set_value("sql").run()
    assert restarted.text_area(key="code::001::sql").value == "SELECT 1"


def test_grading_note_is_shown(progress_db):
    at = start()
    at.selectbox(key="exercise_id").set_value("009").run()
    assert "結果のみで判定" in texts(at.info)


def test_manual_review_problem_reason_is_shown(progress_db):
    at = start()
    at.selectbox(key="exercise_id").set_value("020").run()
    assert "複数の正解" in texts(at.warning)


def test_overview_page(progress_db):
    at = start()
    at.text_area(key="code::001::python").input("df_receipt.head(10)").run()
    at.button(key="grade").click().run()
    at.radio(key="view").set_value("overview").run()
    assert not at.exception
    table = at.dataframe[0].value
    assert len(table) == 100
    assert table.iloc[0]["Python"] == "✅ 正解"
    assert "採点未対応" in table.iloc[74]["SQL"]  # 075 は乱数のため自動採点しない
    assert "1 / 100" in texts(at.metric)


def test_auto_only_filter_limits_list_and_navigation(progress_db):
    at = start()
    at.selectbox(key="exercise_id").set_value("038").run()
    at.checkbox(key="auto_only").check().run()
    options = at.selectbox(key="exercise_id").options
    assert all("採点未対応" not in o for o in options)
    at.button(key="next").click().run()
    assert at.subheader[0].value == "P-040"  # 039 は自動採点しないため飛ばす


def test_default_editor_mode_renders_without_error(tmp_path, monkeypatch):
    """既定（コードエディタ）でもページがエラーなく表示される。"""
    monkeypatch.setenv("KNOCKS_PROGRESS_DB", str(tmp_path / "p.sqlite3"))
    monkeypatch.delenv("KNOCKS_EDITOR", raising=False)
    at = start()
    assert at.radio(key="editor_mode").value == "editor"
    assert at.subheader[0].value == "P-001"


def test_selection_survives_language_switch_and_label_change(progress_db):
    """選択欄のラベルが変わっても（言語切替・状態変化）、選んだ問題が維持される。"""
    at = start()
    at.selectbox(key="exercise_id").set_value("008").run()
    at.text_area(key="code::008::python").input("x = 1").run()  # ⬜ → ✏️ にラベルが変わる
    at.radio(key="language").set_value("sql").run()
    assert at.subheader[0].value == "S-008"
    at.radio(key="language").set_value("python").run()
    assert at.subheader[0].value == "P-008"


def test_setup_note_and_file_output_preview(progress_db):
    at = start()
    at.selectbox(key="exercise_id").set_value("094").run()
    assert "用意済みのデータ" in texts(at.info)
    at.text_area(key="code::094::python").input(
        'df_product_full.to_csv("data/out.csv", index=False)'
    ).run()
    at.button(key="run").click().run()
    assert not at.exception
    assert "出力ファイル" in texts(at.markdown)
    assert "product_cd" in " ".join(str(c.value) for c in at.code)
    at.button(key="grade").click().run()
    assert "正解です" in texts(at.success)


def test_sql_writable_problem(progress_db):
    at = start()
    at.radio(key="language").set_value("sql").run()
    at.selectbox(key="exercise_id").set_value("080").run()
    assert "CREATE TABLE" in " ".join(str(c.value) for c in at.caption)
    code = (
        "CREATE TABLE product_1 AS SELECT * FROM product "
        "WHERE unit_price IS NOT NULL AND unit_cost IS NOT NULL;\nSELECT COUNT(*) FROM product_1;"
    )
    at.text_area(key="code::080::sql").input(code).run()
    at.button(key="run").click().run()
    assert len(at.dataframe[0].value) == 1
    at.button(key="grade").click().run()
    assert "正解です" in texts(at.success)


def test_hints_are_revealed_step_by_step_and_remembered(progress_db):
    at = start()
    at.selectbox(key="exercise_id").set_value("023").run()
    assert at.button(key="hint2").disabled and at.button(key="hint3").disabled
    at.button(key="hint1").click().run()
    assert "`groupby`" in texts(at.markdown)
    assert not at.button(key="hint2").disabled and at.button(key="hint3").disabled
    at.button(key="hint2").click().run()
    assert any("…" in str(c.value) for c in at.code)
    at.button(key="hint3").click().run()
    assert any("# コード例1" in str(c.value) for c in at.code)
    assert "MIT License" in texts(at.markdown)

    restarted = start()
    restarted.selectbox(key="exercise_id").set_value("023").run()
    assert any("# コード例1" in str(c.value) for c in restarted.code)
    assert "📖" in restarted.selectbox(key="exercise_id").format_func("023")


def test_broken_upstream_answer_shows_warning_and_working_example(progress_db):
    at = start()
    at.selectbox(key="exercise_id").set_value("071").run()
    for key in ("hint1", "hint2", "hint3"):
        at.button(key=key).click().run()
    assert "pandas 3" in texts(at.warning)
    assert "pandas 3 で動く書き方の例" in texts(at.markdown)
