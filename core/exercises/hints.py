"""模範解答から段階的なヒントを作る（AIは使わず、コードの構文から機械的に作る）。

- ヒント1: 使う関数・構文（Python は呼び出している関数/メソッド、SQL はキーワードと関数）
- ヒント2: コードの骨組み（文字列・数値を「…」に置き換え、コメントを除いたもの）
- 解答例: 上流の解答例すべて（注記つき）と解説。pandas 3 で動かない解答例しかない問題は、
  採点用の参照コードを「pandas 3 で動く書き方の例」として添える

ヒントの元にするコード: Python は解答例が別解の並びなので、動く最初の解答例。
SQL は上流のセルが「作成→表示」の手順になっているので、全セルをつなげたもの。
"""

from __future__ import annotations

import ast
import io
import json
import tokenize
import tomllib
from dataclasses import dataclass
from functools import cache

import sqlparse
from sqlparse import sql as sqltree
from sqlparse import tokens as T

from core.exercises.catalog import CATALOG_DIR, PROJECT_ROOT, get_exercise, load_answers

ANSWER_NOTES_PATH = PROJECT_ROOT / "exercises" / "answer_notes.toml"
MASK = "…"
_MODULE_ALIASES = {"pd", "np", "math", "preprocessing", "os", "relativedelta"}
_IGNORED_FUNCTIONS = {"print", "display"}
# 基本の語と、列の別名に使われがちでキーワード扱いされる語（unknown 等）は除く
_BASIC_SQL = {"SELECT", "FROM", "AS", "AND", "OR", "ON", "IS", "NULL", "NOT", "UNKNOWN"}
NO_FUNCTIONS = "（特別な関数は使いません）"


@dataclass(frozen=True)
class AnswerCell:
    code: str
    note: str = ""
    broken: bool = False  # 本アプリの環境（pandas 3 等）では動かない


@dataclass(frozen=True)
class Hints:
    functions: list[str]
    skeleton: str
    answers: list[AnswerCell]
    explanations: list[str]
    working_example: str = ""  # 動く解答例がない場合の、採点用参照コード


# ---------------------------------------------------------------- Python


def python_functions(code: str) -> list[str]:
    """呼び出している関数・メソッド名を、ソース上の出現順に重複なく返す。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    found: list[tuple[tuple[int, int], str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
            if isinstance(func.value, ast.Name) and func.value.id in _MODULE_ALIASES:
                name = f"{func.value.id}.{func.attr}"
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            continue
        if name in _IGNORED_FUNCTIONS:
            continue
        found.append(((func.end_lineno or 0, func.end_col_offset or 0), name))
    result: list[str] = []
    for _, name in sorted(found):
        if name not in result:
            result.append(name)
    return result


def python_skeleton(code: str) -> str:
    """文字列・数値を「…」に置き換え、コメントを除いたコード。"""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, SyntaxError):
        return code
    lines = code.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def pos(point: tuple[int, int]) -> int:
        row, col = point
        return offsets[row - 1] + col

    replacements: list[tuple[int, int, str]] = []
    fstring_depth, fstring_start = 0, (0, 0)
    for tok in tokens:
        if tok.type == tokenize.FSTRING_START:
            if fstring_depth == 0:
                fstring_start = tok.start
            fstring_depth += 1
        elif tok.type == tokenize.FSTRING_END:
            fstring_depth -= 1
            if fstring_depth == 0:
                replacements.append((pos(fstring_start), pos(tok.end), f'"{MASK}"'))
        elif fstring_depth:
            continue
        elif tok.type == tokenize.STRING:
            replacements.append((pos(tok.start), pos(tok.end), f'"{MASK}"'))
        elif tok.type == tokenize.NUMBER:
            replacements.append((pos(tok.start), pos(tok.end), MASK))
        elif tok.type == tokenize.COMMENT:
            replacements.append((pos(tok.start), pos(tok.end), ""))

    text = code
    for start, end, new in sorted(replacements, reverse=True):
        text = text[:start] + new + text[end:]
    kept = [
        line.rstrip()
        for original, line in zip(code.splitlines(), text.splitlines(), strict=False)
        if line.strip() or not original.strip()
    ]
    return "\n".join(kept).strip("\n")


# ---------------------------------------------------------------- SQL


def _walk(token: sqltree.Token):
    """構文木を出現順にたどる。関数はまとまりで返す。"""
    if isinstance(token, sqltree.Function):
        yield token
        for child in token.tokens[1:]:  # 名前以外（引数）の中もたどる
            yield from _walk(child)
    elif token.is_group:
        for child in token.tokens:
            yield from _walk(child)
    else:
        yield token


def sql_keywords(code: str) -> list[str]:
    """キーワード（SELECT/FROM 等の基本を除く）と関数名を、出現順に重複なく返す。"""
    result: list[str] = []
    for statement in sqlparse.parse(code):
        for token in _walk(statement):
            if isinstance(token, sqltree.Function):
                name = (token.get_name() or "").upper()
            elif token.ttype in T.Keyword or (
                token.ttype in T.Operator.Comparison and token.value.replace(" ", "").isalpha()
            ):
                name = " ".join(token.value.upper().split())
            else:
                continue
            if name and name not in _BASIC_SQL and name not in result:
                result.append(name)
    return result


def _function_name_tokens(statement: sqltree.Statement) -> set[int]:
    ids: set[int] = set()
    for token in _walk(statement):
        if isinstance(token, sqltree.Function):
            ids.update(id(leaf) for leaf in token.tokens[0].flatten())
    return ids


def sql_skeleton(code: str) -> str:
    """キーワードと関数名だけを残し、テーブル名・列名・文字列・数値を「…」に置き換えたSQL。

    SQL は文字列や数値を含まない解答が多いため、識別子も隠さないと解答例と同じになってしまう。
    """
    parts = []
    for statement in sqlparse.parse(code):
        functions = _function_name_tokens(statement)
        for token in statement.flatten():
            if token.ttype in T.Comment:
                parts.append("\n" if token.value.endswith("\n") else "")
            elif token.ttype in T.String.Single or token.ttype in T.String.Symbol:
                parts.append(f"'{MASK}'")
            elif token.ttype in T.Number:
                parts.append(MASK)
            elif token.ttype in T.Name and id(token) not in functions:
                parts.append(MASK)
            else:
                parts.append(token.value)
    lines = [line.rstrip() for line in "".join(parts).splitlines()]
    return "\n".join(line for line in lines if line.strip()).strip()


# ---------------------------------------------------------------- 解答例の組み立て


@cache
def load_answer_notes() -> dict[tuple[str, str, int], AnswerCell]:
    data = tomllib.loads(ANSWER_NOTES_PATH.read_text(encoding="utf-8"))
    return {
        (n["id"], n["language"], int(n["cell"])): AnswerCell(
            code="", note=n["text"], broken=bool(n.get("broken", False))
        )
        for n in data.get("note", [])
    }


@cache
def _explanations() -> dict[tuple[str, str], list[str]]:
    answers = json.loads((CATALOG_DIR / "answers.json").read_text(encoding="utf-8"))
    return {
        (a["id"], lang): a[lang]["notes"] for a in answers["answers"] for lang in ("python", "sql")
    }


@cache
def build_hints(exercise_id: str, language: str) -> Hints:
    notes = load_answer_notes()
    cells = load_answers()[exercise_id][language]
    answers = []
    for index, code in enumerate(cells):
        note = notes.get((exercise_id, language, index))
        answers.append(
            AnswerCell(code=code, note=note.note if note else "", broken=bool(note and note.broken))
        )

    working = [a.code for a in answers if not a.broken]
    working_example = ""
    if not working:
        spec = get_exercise(exercise_id).grading[language]
        working_example = spec.reference or ""

    if language == "python":
        base = working[0] if working else working_example
        functions = python_functions(base)
        skeleton = python_skeleton(base)
    else:
        base = "\n".join(working) if working else working_example
        functions = sql_keywords(base)
        skeleton = sql_skeleton(base)
    return Hints(
        functions=functions or [NO_FUNCTIONS],
        skeleton=skeleton,
        answers=answers,
        explanations=_explanations()[(exercise_id, language)],
        working_example=working_example,
    )
