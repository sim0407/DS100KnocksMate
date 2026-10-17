"""100本ノック トレーナー（Streamlit UI）。

起動（Docker）: docker compose up -d --build → http://127.0.0.1:8501
学習者のコードはこのプロセスでは実行しない（Pythonは隔離ワーカー、SQLは読み取り専用DB）。
"""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

# `streamlit run app/main.py` で core パッケージを import できるようにする
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.display import row_summary, to_dataframe  # noqa: E402
from core.grading.grader import GradeResult  # noqa: E402
from core.service import DISPLAY_MAX_ROWS, TrainerService  # noqa: E402

LANGUAGE_LABELS = {"python": "Python", "sql": "SQL"}
VIEW_LABELS = {"practice": "演習", "overview": "進捗一覧"}
STATE_ICONS = {"passed": "✅", "in_progress": "✏️"}
HINTS = {
    "python": (
        "最後の行に書いた式の値が結果として表示されます（Jupyterと同様）。"
        "使えるデータ: `df_customer` `df_category` `df_product` `df_receipt` `df_store` `df_geocode`"
    ),
    "sql": (
        "SELECT文（WITH句を含む）を1つ実行できます。データベースは読み取り専用です。"
        "テーブル: `customer` `category` `product` `receipt` `store` `geocode`"
    ),
}
PLACEHOLDERS = {"python": "ここにPythonコードを書きます", "sql": "SELECT ... FROM ..."}
ATTRIBUTION = (
    "教材: 一般社団法人データサイエンティスト協会 スキル定義委員会「データサイエンス100本ノック"
    "（構造化データ加工編）」 "
    "[GitHub](https://github.com/The-Japan-DataScientist-Society/100knocks-preprocess)（MIT License）。"
    "本アプリは同協会の公式アプリではなく、承認・提携を受けたものでもありません。"
)


@st.cache_resource
def get_service() -> TrainerService:
    return TrainerService.from_env()


def code_key(exercise_id: str, language: str) -> str:
    return f"code::{exercise_id}::{language}"


def outcome_key(exercise_id: str, language: str) -> str:
    return f"outcome::{exercise_id}::{language}"


# ---------------------------------------------------------------- コールバック


def on_code_change(exercise_id: str, language: str) -> None:
    get_service().save_draft(
        exercise_id, language, st.session_state[code_key(exercise_id, language)]
    )


def on_review_change(exercise_id: str, language: str) -> None:
    flag = st.session_state[f"review::{exercise_id}::{language}"]
    get_service().progress.set_needs_review(exercise_id, language, flag)


def go_to(exercise_id: str) -> None:
    st.session_state["exercise_id"] = exercise_id


def on_overview_select(ids: list[str]) -> None:
    """進捗一覧の行を選んだら、その問題の演習画面を開く。"""
    rows = st.session_state["overview_table"]["selection"]["rows"]
    if rows:
        st.session_state["exercise_id"] = ids[rows[0]]
        st.session_state["view"] = "practice"


# ---------------------------------------------------------------- 表示部品


def show_response(response: dict) -> None:
    status = response.get("status")
    error = response.get("error") or {}
    if status == "ok":
        show_result(response.get("result"))
    elif status == "error":
        where = f"（{error['lineno']}行目）" if error.get("lineno") else ""
        st.error(f"**{error.get('type', 'Error')}**{where}: {error.get('message', '')}")
        if error.get("traceback"):
            with st.expander("エラーの詳細"):
                st.code(error["traceback"], language="text")
    else:
        st.error(error.get("message") or f"実行に失敗しました（{status}）")

    if response.get("stdout"):
        st.markdown("**標準出力**")
        st.code(response["stdout"], language="text")
        if response.get("stdout_truncated"):
            st.caption("標準出力が長いため途中で省略しました。")
    if response.get("stderr"):
        with st.expander("警告・標準エラー出力"):
            st.code(response["stderr"], language="text")
    if "elapsed_ms" in response:
        st.caption(f"実行時間: {response['elapsed_ms']:,} ms")


def show_result(result: dict | None) -> None:
    if result is None:
        st.info(
            "最後の行が式ではないため、表示する結果はありません。結果を見たい値を最後の行に書いてください。"
        )
        return
    kind = result.get("type")
    if kind == "table":
        st.caption(row_summary(result, len(result["rows"])))
        st.dataframe(to_dataframe(result), hide_index=True)
    elif kind == "scalar":
        st.code(repr(result["value"]), language="text")
    elif kind == "text":
        st.code(result["text"], language="text")
    elif kind == "none":
        st.info("結果は None です。")


def show_grade(grade: GradeResult) -> None:
    reasons = "\n".join(f"- {r}" for r in grade.feedback)
    if grade.status == "passed":
        st.success("✅ **正解です！**")
    elif grade.status == "failed":
        st.error(f"❌ **不正解です**\n\n{reasons}")
    elif grade.status == "manual_review":
        st.warning(f"⚠️ **自動採点できません**\n\n{reasons}")
    else:
        st.error(f"⚠️ **エラーのため採点できません**\n\n{reasons}")


# ---------------------------------------------------------------- ページ


def state_label(row: dict, language: str) -> str:
    state = row[f"{language}_state"]
    text = {"passed": "✅ 正解", "in_progress": "✏️ 挑戦中"}.get(state, "⬜ 未着手")
    if not row[f"{language}_auto"]:
        text += "（採点未対応）"
    if row[f"{language}_review"]:
        text += " 🔖"
    return text


def render_overview(service: TrainerService) -> None:
    st.subheader("進捗一覧")
    total = len(service.exercises)
    for col, language in zip(st.columns(len(LANGUAGE_LABELS)), LANGUAGE_LABELS, strict=True):
        auto = len(service.auto_gradable_ids(language))
        col.metric(
            f"{LANGUAGE_LABELS[language]} 正解", f"{service.passed_count(language)} / {total}"
        )
        col.caption(f"自動採点に対応している問題: {auto} / {total}")

    rows = service.overview()
    table = pd.DataFrame(
        {
            "ID": [r["id"] for r in rows],
            "問題": [r["title"] for r in rows],
            "Python": [state_label(r, "python") for r in rows],
            "SQL": [state_label(r, "sql") for r in rows],
        }
    )
    st.dataframe(
        table,
        hide_index=True,
        key="overview_table",
        # st.dataframe は args を受け付けないため partial で問題IDの並びを渡す
        on_select=partial(on_overview_select, [r["id"] for r in rows]),
        selection_mode="single-row",
        height=560,
    )
    st.caption("行を選ぶと、その問題の演習画面を開きます。")


def render_practice(service: TrainerService, exercise_id: str, language: str, order: list[str]):
    statuses = service.statuses()
    exercise = service.exercise(exercise_id)
    spec = exercise.grading[language]
    status = statuses.get((exercise_id, language))

    # ---- 問題文
    st.subheader(exercise.source_ids[language])
    st.markdown(exercise.statements[language])
    for note in exercise.notes[language]:
        with st.expander("補足（TIPS）"):
            st.markdown(note)
    if exercise.depends_on:
        st.info(f"この問題は {', '.join(exercise.depends_on)} の結果を使います。")
    if spec.strategy == "manual_review":
        st.warning(spec.reason)
    if spec.note:
        st.info(f"採点基準: {spec.note}")

    # ---- コード入力
    key = code_key(exercise_id, language)
    if key not in st.session_state:
        st.session_state[key] = service.draft(exercise_id, language)
    st.text_area(
        "コード",
        key=key,
        height=240,
        placeholder=PLACEHOLDERS[language],
        on_change=on_code_change,
        args=(exercise_id, language),
    )
    st.caption(HINTS[language])

    prev_id, next_id = service.neighbors(exercise_id, order)
    col_run, col_grade, col_prev, col_next, col_review = st.columns([1, 1, 1, 1, 2])
    run_clicked = col_run.button("▶ 実行", key="run", type="primary", width="stretch")
    grade_clicked = col_grade.button("✔ 採点", key="grade", width="stretch")
    col_prev.button(
        "← 前へ",
        key="prev",
        disabled=prev_id is None,
        on_click=go_to,
        args=(prev_id,),
        width="stretch",
    )
    col_next.button(
        "次へ →",
        key="next",
        disabled=next_id is None,
        on_click=go_to,
        args=(next_id,),
        width="stretch",
    )
    review_key = f"review::{exercise_id}::{language}"
    if review_key not in st.session_state:
        st.session_state[review_key] = bool(status and status.needs_review)
    col_review.checkbox(
        "復習対象にする", key=review_key, on_change=on_review_change, args=(exercise_id, language)
    )

    code = st.session_state[key]
    okey = outcome_key(exercise_id, language)
    if run_clicked:
        with st.spinner("実行中…"):
            st.session_state[okey] = {
                "mode": "run",
                "response": service.run(exercise_id, language, code),
            }
    if grade_clicked:
        with st.spinner("採点中…"):
            st.session_state[okey] = {
                "mode": "grade",
                "grade": service.grade(exercise_id, language, code),
            }
        st.rerun()  # サイドバーの進捗表示を更新する

    # ---- 結果
    outcome = st.session_state.get(okey)
    if outcome:
        st.divider()
        if outcome["mode"] == "grade":
            st.markdown("#### 採点結果")
            show_grade(outcome["grade"])
            st.caption("実行結果は「▶ 実行」で確認できます。")
        else:
            st.markdown("#### 実行結果")
            show_response(outcome["response"])
    elif status and status.last_grade_status:
        st.caption(f"前回の採点結果: {status.last_grade_status}")


def main() -> None:
    st.set_page_config(page_title="100本ノック トレーナー", page_icon="📝", layout="wide")
    service = get_service()
    statuses = service.statuses()

    # ---- サイドバー: 表示切替・言語・進捗・問題選択
    with st.sidebar:
        st.header("100本ノック トレーナー")
        view = st.radio(
            "表示", list(VIEW_LABELS), format_func=VIEW_LABELS.get, horizontal=True, key="view"
        )
        language = st.radio(
            "言語",
            list(LANGUAGE_LABELS),
            format_func=LANGUAGE_LABELS.get,
            horizontal=True,
            key="language",
        )
        total = len(service.exercises)
        passed = service.passed_count(language)
        st.progress(passed / total, text=f"{LANGUAGE_LABELS[language]} 正解: {passed} / {total}")

        auto_only = st.checkbox("自動採点に対応している問題だけ表示", key="auto_only")
        order = (
            service.auto_gradable_ids(language) if auto_only else [e.id for e in service.exercises]
        )
        if st.session_state.get("exercise_id") not in order:
            st.session_state["exercise_id"] = order[0]

        def label(exercise_id: str) -> str:
            ex = service.exercise(exercise_id)
            status = statuses.get((exercise_id, language))
            icon = STATE_ICONS.get(status.state, "⬜") if status else "⬜"
            review = " 🔖" if status and status.needs_review else ""
            unsupported = (
                "（採点未対応）" if ex.grading[language].strategy == "manual_review" else ""
            )
            return f"{icon} {exercise_id} {ex.title(language, 24)}{unsupported}{review}"

        exercise_id = st.selectbox("問題", order, format_func=label, key="exercise_id")
        st.caption("✅ 正解 / ✏️ 挑戦中 / ⬜ 未着手 / 🔖 復習対象")

    if view == "overview":
        render_overview(service)
    else:
        render_practice(service, exercise_id, language, order)

    st.divider()
    st.caption(ATTRIBUTION)
    st.caption(
        f"表示は最大{DISPLAY_MAX_ROWS}行。入力したコードは自動保存されます（入力欄から離れたとき、または Ctrl+Enter）。"
    )


main()
