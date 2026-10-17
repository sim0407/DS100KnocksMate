"""参照結果の照合: 自動採点する問題について、本アプリで模範解答を実行した結果が、
上流の解答Notebookに保存された出力（pandas 1.5.3 / PostgreSQL 時代）と一致することを確認する。

- Python: 表なら行数、値ならその値（text/plain から読む）
- SQL:    jupysql が出力する「N rows affected.」の行数

実行: docker compose --profile test run --rm --build tests
"""

import json
import math
import os
import re
from functools import cache
from pathlib import Path

import pytest

from core.execution.python_runner import run_python
from core.execution.sql_runner import run_sql
from core.exercises.catalog import load_answers, load_exercises

WORKER_URL = os.environ.get("KNOCKS_WORKER_URL")
DB_DSN = os.environ.get("KNOCKS_DB_DSN")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (WORKER_URL and DB_DSN), reason="compose の tests サービスで実行"),
]

NOTEBOOK_DIR = (
    Path(__file__).resolve().parents[2] / "upstream/100knocks-preprocess/docker/work/answer"
)
NOTEBOOKS = {
    "python": ("ans_preprocess_knock_Python.ipynb", "P"),
    "sql": ("ans_preprocess_knock_SQL.ipynb", "S"),
}


@cache
def first_outputs(language: str) -> dict[str, list[dict]]:
    """{問題ID: 最初の解答セルの outputs}"""
    filename, prefix = NOTEBOOKS[language]
    cells = json.loads((NOTEBOOK_DIR / filename).read_text(encoding="utf-8"))["cells"]
    result: dict[str, list[dict]] = {}
    current = None
    for cell in cells:
        text = "".join(cell["source"])
        m = re.search(prefix + r"-(\d{3})[:：]", text) if cell["cell_type"] == "markdown" else None
        if m:
            current = m.group(1)
        elif cell["cell_type"] == "code" and current and current not in result:
            result[current] = cell.get("outputs", [])
    return result


def notebook_python(outputs: list[dict]) -> tuple[str, object]:
    """('rows', 行数) または ('value', 値の文字列)。"""
    text = next("".join(o["data"]["text/plain"]) for o in outputs if "data" in o)
    m = re.search(r"\[(\d+) rows x \d+ columns\]", text)
    if m:
        return "rows", int(m.group(1))
    lines = text.splitlines()
    if lines and lines[-1].startswith(("dtype:", "Name:")):  # Series の表示
        return "rows", len([line for line in lines if not line.startswith(("dtype:", "Name:"))])
    index_tokens = {line.split()[0] for line in lines if re.match(r"^\d+\s+\S", line)}
    if index_tokens:
        return "rows", len(index_tokens)
    return "value", text.strip()


def notebook_sql_rows(outputs: list[dict]) -> int:
    text = "".join("".join(o.get("text", [])) for o in outputs if o.get("output_type") == "stream")
    return int(re.search(r"(\d+) rows affected", text).group(1))


def values_match(value, text: str) -> bool:
    """Notebook の表示は浮動小数点を丸めて表示するため、数値は誤差を許容して比べる。"""
    try:
        return math.isclose(float(value), float(text), rel_tol=1e-9)
    except (TypeError, ValueError):
        return str(value) == text


CASES = [
    (e.id, lang)
    for e in load_exercises()
    for lang in ("python", "sql")
    if e.grading[lang].strategy != "manual_review"
]


@pytest.mark.parametrize(("exercise_id", "language"), CASES)
def test_model_answer_matches_notebook_output(exercise_id, language):
    code = load_answers()[exercise_id][language][0]
    outputs = first_outputs(language)[exercise_id]
    if language == "python":
        response = run_python(code, url=WORKER_URL, max_rows=1000)
        assert response["status"] == "ok", response["error"]
        kind, expected = notebook_python(outputs)
        result = response["result"]
        if kind == "rows":
            assert result["row_count"] == expected
        else:
            assert values_match(result["value"], expected)
    else:
        response = run_sql(code, dsn=DB_DSN, max_rows=1000)
        assert response["status"] == "ok", response["error"]
        assert response["result"]["row_count"] == notebook_sql_rows(outputs)
