"""コード入力用の軽量エディタ（Streamlit Components v2、外部ライブラリ・CDN なし）。

- Tab / Shift+Tab: インデント / 戻す（複数行選択にも対応、4スペース）
- Enter: 直前行のインデントを引き継ぐ（Python では `:` で終わる行の後に1段下げる）
- Backspace: 行頭の空白内ではインデント1段分を削除
- Ctrl+Enter（Mac は Cmd+Enter）: 実行
- Esc の直後の Tab: エディタの外へフォーカスを移す（キーボード操作のため）
- 行番号表示、元に戻す（Ctrl+Z）が効くよう execCommand('insertText') で編集

Python 側へは「入力欄から離れたとき」「Ctrl+Enter」「入力が1.5秒止まったとき」に送る
（1文字ごとに送るとスクリプトが毎回再実行されるため）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

HTML = """
<div class="knocks-editor">
  <div class="knocks-gutter" aria-hidden="true">1</div>
  <textarea class="knocks-input" spellcheck="false" autocapitalize="off" autocomplete="off"
            autocorrect="off" wrap="off" aria-label="コード入力欄"></textarea>
</div>
"""

CSS = """
.knocks-editor {
  display: flex;
  height: var(--knocks-editor-height, 260px);
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
  border-radius: var(--st-base-radius, 0.5rem);
  overflow: hidden;
  background: var(--st-secondary-background-color, #f0f2f6);
  font-family: var(--st-code-font, "Source Code Pro", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);
  font-size: 14px;
  line-height: 1.5;
}
.knocks-editor:focus-within {
  border-color: var(--st-primary-color, #ff4b4b);
}
.knocks-gutter {
  padding: 8px 8px 24px 12px;
  min-width: 2.5em;
  text-align: right;
  white-space: pre;
  overflow: hidden;
  user-select: none;
  color: var(--st-text-color, #31333f);
  opacity: 0.45;
}
.knocks-input {
  flex: 1;
  margin: 0;
  padding: 8px;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--st-text-color, #31333f);
  font: inherit;
  line-height: inherit;
  white-space: pre;
  overflow: auto;
  tab-size: 4;
}
"""

JS = r"""
const INDENT = "    ";
const SYNC_DELAY_MS = 1500;

export default function (component) {
  const { parentElement, data, setStateValue, setTriggerValue } = component;
  const root = parentElement.querySelector(".knocks-editor");
  const ta = root.querySelector("textarea");
  const gutter = root.querySelector(".knocks-gutter");

  root.style.setProperty("--knocks-editor-height", `${data.height}px`);
  ta.placeholder = data.placeholder || "";

  // 再描画のたびにこの関数が呼ばれるため、状態は要素に保持し、ハンドラは代入で上書きする
  let st = root.__knocks;
  const incoming = data.value ?? "";
  if (!st) {
    st = root.__knocks = { synced: incoming, timer: null, escape: false };
    ta.value = incoming;
  } else if (parentElement.activeElement !== ta && incoming !== ta.value && incoming !== st.synced) {
    // 入力中でなければ、Python 側の値（別の問題の草稿など）を反映する
    ta.value = incoming;
    st.synced = incoming;
  }
  st.language = data.language;

  const renderGutter = () => {
    const lines = ta.value.split("\n").length;
    let text = "";
    for (let i = 1; i <= lines; i++) text += i + "\n";
    gutter.textContent = text;
    gutter.scrollTop = ta.scrollTop;
  };

  const sync = () => {
    clearTimeout(st.timer);
    st.timer = null;
    if (ta.value !== st.synced) {
      st.synced = ta.value;
      setStateValue("value", ta.value);
    }
  };

  const insert = (text) => {
    const caret = ta.selectionStart + text.length;
    // execCommand なら元に戻す（Ctrl+Z）の履歴が残る。使えない環境では setRangeText で代替
    if (!document.execCommand("insertText", false, text)) {
      ta.setRangeText(text, ta.selectionStart, ta.selectionEnd, "end");
      ta.dispatchEvent(new Event("input"));
    }
    // 末尾の改行の直前でカーソルがずれるブラウザがあるため、位置を明示する
    ta.setSelectionRange(caret, caret);
  };

  const lineStartOf = (pos) => ta.value.lastIndexOf("\n", pos - 1) + 1;

  const indentLines = (dedent) => {
    const value = ta.value;
    const start = lineStartOf(ta.selectionStart);
    let end = ta.selectionEnd;
    if (end > start && value[end - 1] === "\n") end -= 1; // 末尾の改行の次の行は含めない
    const lineEnd = value.indexOf("\n", end);
    const blockEnd = lineEnd === -1 ? value.length : lineEnd;
    const lines = value.slice(start, blockEnd).split("\n");
    const changed = lines.map((line) => {
      if (!dedent) return INDENT + line;
      const spaces = line.match(/^ */)[0].length;
      return line.slice(Math.min(spaces, INDENT.length));
    });
    ta.setSelectionRange(start, blockEnd);
    insert(changed.join("\n"));
    ta.setSelectionRange(start, start + changed.join("\n").length);
  };

  ta.oninput = () => {
    renderGutter();
    clearTimeout(st.timer);
    st.timer = setTimeout(sync, SYNC_DELAY_MS);
  };
  ta.onblur = sync;
  ta.onscroll = () => {
    gutter.scrollTop = ta.scrollTop;
  };

  ta.onkeydown = (e) => {
    if (e.key === "Escape") {
      st.escape = true;
      return;
    }
    const escaped = st.escape;
    st.escape = false;
    if (e.isComposing) return; // 日本語入力の変換中は既定の動作に任せる

    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sync();
      setTriggerValue("run", Date.now());
      return;
    }
    if (e.key === "Tab" && !e.ctrlKey && !e.altKey && !e.metaKey) {
      if (escaped) return; // Esc の直後はフォーカス移動を許す
      e.preventDefault();
      const multiLine = ta.value.slice(ta.selectionStart, ta.selectionEnd).includes("\n");
      if (e.shiftKey || multiLine) {
        indentLines(e.shiftKey);
      } else {
        const column = ta.selectionStart - lineStartOf(ta.selectionStart);
        insert(" ".repeat(INDENT.length - (column % INDENT.length)));
      }
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      const before = ta.value.slice(lineStartOf(ta.selectionStart), ta.selectionStart);
      let indent = before.match(/^[ \t]*/)[0];
      if (st.language === "python" && /:\s*(#.*)?$/.test(before)) indent += INDENT;
      insert("\n" + indent);
      return;
    }
    if (e.key === "Backspace" && ta.selectionStart === ta.selectionEnd) {
      const before = ta.value.slice(lineStartOf(ta.selectionStart), ta.selectionStart);
      if (before.length > 0 && /^ +$/.test(before)) {
        e.preventDefault();
        const count = ((before.length - 1) % INDENT.length) + 1;
        ta.setSelectionRange(ta.selectionStart - count, ta.selectionStart);
        insert("");
      }
    }
  };

  renderGutter();
}
"""

_component = st.components.v2.component("knocks_code_editor", html=HTML, css=CSS, js=JS)


@dataclass(frozen=True)
class EditorResult:
    code: str
    run_requested: bool  # Ctrl+Enter が押された


def code_editor(
    *,
    key: str,
    initial: str,
    language: str,
    placeholder: str,
    on_change: Callable[[], None],
    height: int = 260,
) -> EditorResult:
    """エディタを表示し、現在のコードと Ctrl+Enter の有無を返す。

    最新の値は st.session_state[key]["value"] に保持される（on_change で草稿を保存する）。
    """
    state = st.session_state.get(key)
    value = state.get("value", initial) if isinstance(state, dict) else initial
    result = _component(
        key=key,
        data={"value": value, "language": language, "placeholder": placeholder, "height": height},
        default={"value": value},
        on_value_change=on_change,
        on_run_change=lambda: None,
        height=height + 2,
    )
    code = result.get("value")
    return EditorResult(code=value if code is None else code, run_requested=bool(result.get("run")))
