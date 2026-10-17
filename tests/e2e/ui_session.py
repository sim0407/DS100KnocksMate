"""E2E確認用スクリプト: 起動中の app コンテナ内で UI を操作する（pytest の収集対象外）。

    docker compose -p ds100knocks-e2e exec -T app python - solve  < tests/e2e/ui_session.py
    docker compose -p ds100knocks-e2e exec -T app python - verify < tests/e2e/ui_session.py

solve:  P-001 を Python で正解し、S-001 に草稿を書く（コンテナの学習履歴volumeに保存される）
verify: アプリを新しく開き、草稿と正解状態が復元されていることを確認する
注意: 学習履歴を書き換えるため、普段使いのプロジェクトではなく E2E 用プロジェクトで実行する。
"""

import sys

from streamlit.testing.v1 import AppTest

APP = "/opt/knocks/app/main.py"
PY_CODE = "df_receipt.head(10)"
SQL_DRAFT = "SELECT * FROM receipt"


def open_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception
    return at


def solve() -> None:
    at = open_app()
    at.text_area(key="code::001::python").input(PY_CODE).run()
    at.button(key="run").click().run()
    assert len(at.dataframe[0].value) == 10
    at.button(key="grade").click().run()
    assert any("正解です" in str(s.value) for s in at.success), [e.value for e in at.error]
    at.radio(key="language").set_value("sql").run()
    at.text_area(key="code::001::sql").input(SQL_DRAFT).run()
    print("solve: OK (P-001 passed, S-001 draft saved)")


def verify() -> None:
    at = open_app()
    assert at.text_area(key="code::001::python").value == PY_CODE
    assert at.selectbox(key="exercise_id").format_func("001").startswith("✅")
    at.radio(key="language").set_value("sql").run()
    assert at.text_area(key="code::001::sql").value == SQL_DRAFT
    assert at.selectbox(key="exercise_id").format_func("001").startswith("✏️")
    print("verify: OK (draft and passed state restored)")


if __name__ == "__main__":
    {"solve": solve, "verify": verify}[sys.argv[1]]()
