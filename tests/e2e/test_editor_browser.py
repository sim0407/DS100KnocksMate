"""実ブラウザ（Playwright/Chromium）でのコードエディタと画面操作の確認。

AppTest では独自部品を操作できないため、入力→実行の流れはここで確認する。学習履歴を書き換えるので、
普段使いとは別のプロジェクト名・ポートで起動した環境に対して実行する:

    KNOCKS_PORT=8502 docker compose -p ds100knocks-e2e up -d --build --wait
    uv sync --group e2e && uv run --group e2e playwright install chromium
    KNOCKS_E2E_URL=http://127.0.0.1:8502 uv run --group e2e pytest tests/e2e -m e2e
    docker compose -p ds100knocks-e2e down -v
"""

import os
import re

import pytest

URL = os.environ.get("KNOCKS_E2E_URL")
playwright_api = pytest.importorskip("playwright.sync_api", reason="e2e グループ未インストール")
expect = playwright_api.expect

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not URL, reason="KNOCKS_E2E_URL が未設定（E2E用に起動した環境で実行）"),
]


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="ja-JP")
    page = context.new_page()
    page.set_default_timeout(30_000)
    page.goto(URL)
    page.locator("textarea.knocks-input").wait_for()
    yield page
    context.close()


def editor(page):
    return page.locator("textarea.knocks-input")


def choose_exercise(page, exercise_id):
    page.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').click()
    page.get_by_role("option", name=re.compile(rf" {exercise_id} ")).click()
    expect(page.get_by_role("heading", name=re.compile(rf"[PS]-{exercise_id}"))).to_be_visible()
    editor(page).wait_for()


def choose_language(page, label):
    page.locator('[data-testid="stSidebar"]').get_by_text(label, exact=True).click()
    prefix = "S" if label == "SQL" else "P"
    # 再描画（選択欄の作り直し）が終わるまで待つ
    expect(page.get_by_role("heading", name=re.compile(rf"^{prefix}-\d{{3}}"))).to_be_visible()
    editor(page).wait_for()


def clear_editor(page):
    ed = editor(page)
    ed.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")


def run_button(page):
    return page.get_by_role("button", name="▶ 実行")


def test_type_then_click_run_immediately_uses_latest_code(page):
    choose_exercise(page, "001")
    clear_editor(page)
    page.keyboard.type("df_receipt.head(10)")
    run_button(page).click()  # 入力欄から離れる直前の内容が使われること
    expect(page.get_by_text("10行 × 9列")).to_be_visible()


def test_tab_enter_backspace_indentation(page):
    choose_exercise(page, "002")
    clear_editor(page)
    page.keyboard.type("for i in range(3):")
    page.keyboard.press("Enter")
    page.keyboard.type("print(i)")
    page.keyboard.press("Enter")
    page.keyboard.press("Backspace")
    page.keyboard.type("42")
    assert editor(page).input_value() == "for i in range(3):\n    print(i)\n42"

    page.keyboard.press("Enter")
    page.keyboard.press("Tab")
    assert editor(page).input_value().endswith("\n42\n    ")


def test_shift_tab_and_tab_on_selection(page):
    choose_exercise(page, "003")
    clear_editor(page)
    page.keyboard.insert_text("    a = 1\n    b = 2")
    page.keyboard.press("Control+A")
    page.keyboard.press("Shift+Tab")
    assert editor(page).input_value() == "a = 1\nb = 2"
    page.keyboard.press("Tab")
    assert editor(page).input_value() == "    a = 1\n    b = 2"


def test_undo_after_tab(page):
    choose_exercise(page, "004")
    clear_editor(page)
    page.keyboard.type("abc")
    page.keyboard.press("Tab")
    assert editor(page).input_value() == "abc "
    page.keyboard.press("Control+Z")
    assert editor(page).input_value() == "abc"


def test_ctrl_enter_runs_and_shows_stdout(page):
    choose_exercise(page, "005")
    clear_editor(page)
    page.keyboard.type("for i in range(3):")
    page.keyboard.press("Enter")
    page.keyboard.type("print(i)")
    page.keyboard.press("Enter")
    page.keyboard.press("Backspace")
    page.keyboard.type("42")
    page.keyboard.press("Control+Enter")
    expect(page.get_by_text("標準出力")).to_be_visible()
    expect(page.get_by_text(re.compile(r"^0\s+1\s+2\s*$"))).to_be_visible()


def test_draft_is_saved_without_leaving_editor(page):
    choose_exercise(page, "006")
    clear_editor(page)
    page.keyboard.type("x = 'draft'")
    page.wait_for_timeout(3000)  # 入力が止まってから送信されるまで待つ（1.5秒＋再実行）
    page.reload()
    choose_exercise(page, "006")
    expect(editor(page)).to_have_value("x = 'draft'")


def test_escape_then_tab_leaves_editor(page):
    choose_exercise(page, "007")
    editor(page).click()
    page.keyboard.press("Escape")
    page.keyboard.press("Tab")
    focused = editor(page).evaluate("el => el.getRootNode().activeElement === el")
    assert focused is False


def test_grade_sql_passes(page):
    choose_language(page, "SQL")
    choose_exercise(page, "001")
    clear_editor(page)
    page.keyboard.type("SELECT * FROM receipt LIMIT 10;")
    page.get_by_role("button", name="✔ 採点").click()
    expect(page.get_by_text("正解です！")).to_be_visible()


def test_language_switch_keeps_each_code(page):
    choose_exercise(page, "008")
    clear_editor(page)
    page.keyboard.type("python_code = 1")
    choose_language(page, "SQL")
    expect(page.get_by_role("heading", name="S-008")).to_be_visible()
    clear_editor(page)
    page.keyboard.type("SELECT 8")
    choose_language(page, "Python")
    expect(page.get_by_role("heading", name="P-008")).to_be_visible()
    expect(editor(page)).to_have_value("python_code = 1")
    choose_language(page, "SQL")
    expect(editor(page)).to_have_value("SELECT 8")
