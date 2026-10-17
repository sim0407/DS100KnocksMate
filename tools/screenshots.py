"""README 用のスクリーンショットを撮る（実ブラウザで操作して docs/images/ に保存）。

学習履歴を書き換えるため、E2E 用の環境（初期化済み）に対して実行する:
    docker compose -p ds100knocks-e2e down -v
    KNOCKS_PORT=8502 docker compose -p ds100knocks-e2e up -d --build --wait
    KNOCKS_E2E_URL=http://127.0.0.1:8502 uv run --group e2e python -m tools.screenshots
    docker compose -p ds100knocks-e2e down -v
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
URL = os.environ.get("KNOCKS_E2E_URL", "http://127.0.0.1:8502")


def choose_exercise(page, exercise_id: str) -> None:
    page.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').click()
    page.keyboard.type(exercise_id)
    page.get_by_role("option", name=re.compile(rf" {exercise_id} ")).click()
    expect(page.get_by_role("heading", name=re.compile(rf"[PS]-{exercise_id}"))).to_be_visible()


def scroll_top(page) -> None:
    page.evaluate(
        "() => { window.scrollTo(0, 0); "
        "document.querySelectorAll('[data-testid=\"stMain\"], section').forEach(e => e.scrollTo && e.scrollTo(0, 0)); }"
    )
    page.wait_for_timeout(300)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1450}, locale="ja-JP")
        page.set_default_timeout(60_000)
        page.goto(URL)
        editor = page.locator("textarea.knocks-input")
        editor.wait_for()

        # 1. 演習画面: 実行して結果を確認し、採点で正解
        choose_exercise(page, "004")
        editor.click()
        page.keyboard.type(
            'df_receipt[["sales_ymd", "customer_id", "product_cd", "amount"]]'
            ".query('customer_id == \"CS018205000001\"')"
        )
        page.get_by_role("button", name="▶ 実行").click()
        expect(page.get_by_text("12行 × 4列")).to_be_visible()
        page.wait_for_timeout(2000)  # 表（canvas）の描画を待つ
        scroll_top(page)
        page.screenshot(path=OUT / "practice-run.png")
        page.get_by_role("button", name="✔ 採点").click()
        expect(page.get_by_text("正解です！")).to_be_visible()
        page.wait_for_timeout(1000)
        scroll_top(page)
        page.screenshot(path=OUT / "practice-graded.png")

        # 2. ヒント・解答例（ヒント2まで）
        choose_exercise(page, "023")
        page.get_by_text("💡 ヒント・解答例").click()
        page.get_by_role("button", name="ヒント1: 使う関数・構文").click()
        page.get_by_role("button", name="ヒント2: コードの骨組み").click()
        expect(page.get_by_text("文字列・数値を「…」に置き換えています")).to_be_visible()
        page.wait_for_timeout(1500)  # 欄が開くアニメーションを待つ
        page.get_by_text("💡 ヒント・解答例").scroll_into_view_if_needed()
        page.screenshot(path=OUT / "hints.png")

        # 3. 進捗一覧
        page.locator('[data-testid="stSidebar"]').get_by_text("進捗一覧", exact=True).click()
        expect(page.get_by_role("heading", name="進捗一覧")).to_be_visible()
        page.wait_for_timeout(2000)
        scroll_top(page)
        page.screenshot(path=OUT / "overview.png")
        browser.close()
    for path in sorted(OUT.glob("*.png")):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
