"""同梱した上流Notebookから問題定義（カタログ）を生成するツール。

使い方:
    uv run python -m tools.extract_problems

出力（いずれも生成物。手で編集しない）:
    exercises/catalog/problems.json  問題文・注記・依存関係（学習UIに表示してよい情報）
    exercises/catalog/answers.json   模範解答コード・解説（学習UIには初期表示しない）

採点方式など手作業で決める情報はここに含めず、別の問題定義ファイルで管理する。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tools.vendor_upstream import PINNED_COMMIT, UPSTREAM_REPO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = PROJECT_ROOT / "upstream" / "100knocks-preprocess"
OUTPUT_DIR = PROJECT_ROOT / "exercises" / "catalog"

NOTEBOOKS = {
    "python": {
        "prefix": "P",
        "question": "docker/work/preprocess_knock_Python.ipynb",
        "answer": "docker/work/answer/ans_preprocess_knock_Python.ipynb",
    },
    "sql": {
        "prefix": "S",
        "question": "docker/work/preprocess_knock_SQL.ipynb",
        "answer": "docker/work/answer/ans_preprocess_knock_SQL.ipynb",
    },
}

# 例: "---\n> P-001: ..." / "> P-043： ..." / "> P-閑話: ..."
_HEADER_RE = re.compile(r"\A\s*(?:-{3,}\s*\n)?\s*>\s*([PS])-([^\s:：]+)\s*[:：]")
_ID_PREFIX_RE = re.compile(r"\A[PS]-[^\s:：]+\s*[:：]\s*")
# 「043で作成した」「056の抽出結果」「079で確認した」等。「100〜209の」のような数値表現は拾わない
_DEPENDENCY_RE = re.compile(r"(\d{3})(?:で作成|の抽出結果|で確認)")


@dataclass
class Section:
    statement: str
    code_cells: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SplitResult:
    problems: dict[str, Section] = field(default_factory=dict)
    interludes: list[dict] = field(default_factory=list)
    setup_cells: list[str] = field(default_factory=list)


def cell_text(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else source


def parse_header(text: str) -> tuple[str, str] | None:
    """問題見出しセルなら (言語接頭辞, 番号) を返す。番号は '001' や '閑話'。"""
    m = _HEADER_RE.match(text)
    return (m.group(1), m.group(2)) if m else None


def normalize_statement(raw: str) -> str:
    """見出しセルのMarkdownから区切り線・引用記号・問題IDを除いた問題文を返す。"""
    lines = raw.splitlines()
    while lines and (not lines[0].strip() or set(lines[0].strip()) == {"-"}):
        lines.pop(0)
    out = []
    for line in lines:
        if line.startswith(">"):
            line = line[1:]
            if line.startswith(" "):
                line = line[1:]
        out.append(line.rstrip())
    if out:
        out[0] = _ID_PREFIX_RE.sub("", out[0])
    return "\n".join(out).strip()


def strip_sql_magic(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].strip() == "%%sql":
        lines = lines[1:]
    return "\n".join(lines).strip()


def detect_dependencies(statement: str) -> list[str]:
    """「043で作成した〜」のような前問への依存を検出する（ヒューリスティック）。"""
    return sorted(set(_DEPENDENCY_RE.findall(statement)))


def split_notebook(cells: list[dict], prefix: str) -> SplitResult:
    """Notebookのセル列を問題ごとに分割する。

    - 最初の問題見出しより前のcode cellは共通セットアップ
    - 見出しの後のcode cellはその問題の解答欄、markdownは注記（TIPS・解説）
    - 「P-閑話」のような番号のない見出しは interludes に分ける
    - 問題開始後の「# 」で始まる見出しは終端とみなす
    """
    result = SplitResult()
    current: Section | None = None
    current_interlude: dict | None = None
    last_id: str | None = None
    started = False

    for cell in cells:
        text = cell_text(cell)
        kind = cell.get("cell_type")

        if kind == "markdown":
            header = parse_header(text)
            if header:
                lang, number = header
                if lang != prefix:
                    raise ValueError(f"接頭辞が想定({prefix})と異なる見出し: {text[:40]!r}")
                started = True
                if number.isdigit():
                    if number in result.problems:
                        raise ValueError(f"問題IDが重複: {prefix}-{number}")
                    current = Section(statement=normalize_statement(text))
                    result.problems[number] = current
                    current_interlude = None
                    last_id = number
                else:
                    current = None
                    current_interlude = {
                        "after": last_id,
                        "statement": normalize_statement(text),
                        "code_cells": [],
                    }
                    result.interludes.append(current_interlude)
                continue
            if started and text.lstrip().startswith("# "):
                current = current_interlude = None
                continue
            if current is not None and text.strip():
                current.notes.append(text.strip())
            continue

        if kind != "code":
            continue
        body = strip_sql_magic(text) if prefix == "S" else text.strip()
        if not body:
            continue
        if not started:
            result.setup_cells.append(text.strip())
        elif current is not None:
            current.code_cells.append(body)
        elif current_interlude is not None:
            current_interlude["code_cells"].append(body)

    return result


def load_cells(rel_path: str) -> list[dict]:
    notebook = json.loads((SNAPSHOT_DIR / rel_path).read_text(encoding="utf-8"))
    return notebook["cells"]


def build_catalog() -> dict[str, dict]:
    warnings: list[str] = []
    split: dict[str, dict[str, SplitResult]] = {}
    for lang, spec in NOTEBOOKS.items():
        split[lang] = {
            kind: split_notebook(load_cells(spec[kind]), spec["prefix"])
            for kind in ("question", "answer")
        }
        q, a = split[lang]["question"], split[lang]["answer"]
        if list(q.problems) != list(a.problems):
            raise ValueError(f"{lang}: 設問Notebookと解答NotebookのID列が一致しない")
        for pid, section in q.problems.items():
            if section.statement != a.problems[pid].statement:
                warnings.append(
                    f"{spec['prefix']}-{pid}: 設問Notebookと解答Notebookで問題文が異なる"
                )
            for code in a.problems[pid].code_cells:
                if any(line.lstrip().startswith(("%", "!")) for line in code.splitlines()):
                    warnings.append(f"{spec['prefix']}-{pid}: 解答にIPythonマジック/シェル行を含む")
                    break

    ids = list(split["python"]["question"].problems)
    if ids != list(split["sql"]["question"].problems):
        raise ValueError("PythonとSQLで問題IDの列が一致しない")

    problems, answers = [], []
    for pid in ids:
        entry: dict = {"id": pid}
        answer: dict = {"id": pid}
        deps: set[str] = set()
        for lang, spec in NOTEBOOKS.items():
            q = split[lang]["question"].problems[pid]
            a = split[lang]["answer"].problems[pid]
            entry[lang] = {
                "source_id": f"{spec['prefix']}-{pid}",
                "statement": q.statement,
                "notes": q.notes,
            }
            answer[lang] = {
                "code_cells": a.code_cells,
                "notes": [n for n in a.notes if n not in q.notes],
            }
            deps.update(detect_dependencies(q.statement))
        entry["depends_on"] = sorted(deps)
        problems.append(entry)
        answers.append(answer)

    source = {"repository": UPSTREAM_REPO, "commit": PINNED_COMMIT}
    return {
        "problems": {
            "generated_by": "tools/extract_problems.py",
            "source": {**source, "notebooks": {k: v["question"] for k, v in NOTEBOOKS.items()}},
            "problems": problems,
            "warnings": warnings,
        },
        "answers": {
            "generated_by": "tools/extract_problems.py",
            "source": {**source, "notebooks": {k: v["answer"] for k, v in NOTEBOOKS.items()}},
            "setup": {lang: split[lang]["answer"].setup_cells for lang in NOTEBOOKS},
            "answers": answers,
            "interludes": {lang: split[lang]["answer"].interludes for lang in NOTEBOOKS},
        },
    }


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    catalog = build_catalog()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in catalog.items():
        (OUTPUT_DIR / f"{name}.json").write_text(dumps(data), encoding="utf-8", newline="\n")
    problems = catalog["problems"]
    print(f"problems: {len(problems['problems'])}  warnings: {len(problems['warnings'])}")
    for w in problems["warnings"]:
        print(f"  - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
