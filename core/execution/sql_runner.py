"""学習者のSQLを教材用PostgreSQLで実行する（変更は必ずロールバック）。

安全性はSQL文字列の検査ではなく、DB側で担保する（docker/db/sql/03_roles.sql）:
- 教材テーブルは SELECT 権限のみ。作れるのはセッション専用の一時テーブルだけ
- 管理者のネットワークログイン不可、サーバ上のファイル入出力（COPY ... TO/FROM 'ファイル'）不可
- 本モジュールでも statement_timeout を設定し、最後に必ず ROLLBACK する

2つのモード:
- 読み取り専用（既定）: `BEGIN READ ONLY` で、`DECLARE ... CURSOR FOR <SQL>` を prepared
  statement として送る。SELECT系（WITH含む）以外は構文エラー、複数文はサーバ側で拒否される
- 書き込み可能（writable、テーブルを作る問題用）: 文ごとに分けて順に実行する。
  search_path を pg_temp 優先にし、`CREATE TABLE` は一時スキーマに作られる。
  SELECT はカーソル経由（巨大な結果でもメモリを使わない）、最後の SELECT の結果を返す。
  `COPY ... TO STDOUT` の出力は files に、`COPY ... FROM STDIN` には stdin_query の出力を流す。
FETCH で先頭 max_rows 行だけ取得し、残りは MOVE で数える。

戻り値はPythonワーカーと同じ形の辞書（status / result / stdout / error / elapsed_ms / files）。
"""

from __future__ import annotations

import base64
import datetime as dt
import math
import re
import time
from decimal import Decimal
from typing import Any

import psycopg
import sqlparse
from psycopg import errors
from psycopg.postgres import types as pg_types

from core.execution.results import BOOLEAN, DATETIME, FLOAT, INTEGER, OTHER, STRING

CURSOR_NAME = "knocks_q"
_DECLARE_PREFIX = f"DECLARE {CURSOR_NAME} NO SCROLL CURSOR FOR "
MAX_COPY_BYTES = 16 * 1024 * 1024

_KIND_BY_TYPE = {
    **dict.fromkeys(("int2", "int4", "int8", "oid"), INTEGER),
    **dict.fromkeys(("numeric", "float4", "float8"), FLOAT),
    **dict.fromkeys(("text", "varchar", "bpchar", "char", "name"), STRING),
    **dict.fromkeys(("date", "timestamp", "timestamptz"), DATETIME),
    "bool": BOOLEAN,
}
_COPY_OUT_RE = re.compile(r"^\s*COPY\b.*\bTO\s+STDOUT\b", re.IGNORECASE | re.DOTALL)
_COPY_IN_RE = re.compile(r"^\s*COPY\b.*\bFROM\s+STDIN\b", re.IGNORECASE | re.DOTALL)
_TRAILING_RE = re.compile(r";(\s|--[^\n]*)*$")


def normalize_sql(sql: str) -> str:
    """前後の空白と、Notebookの `%%sql` 行を除く（Notebookからの貼り付けに対応）。"""
    lines = sql.strip().splitlines()
    if lines and lines[0].strip() == "%%sql":
        lines = lines[1:]
    return "\n".join(lines).strip()


def _response(status: str, started: float, *, result=None, error=None, files=None) -> dict:
    response = {
        "status": status,
        "result": result,
        "stdout": "",
        "stdout_truncated": False,
        "stderr": "",
        "stderr_truncated": False,
        "error": error,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
    if files is not None:
        response["files"] = files
    return response


def _error(err_type: str, message: str, lineno: int | None = None) -> dict:
    return {"type": err_type, "message": message, "traceback": "", "lineno": lineno}


def _kind(type_code: int) -> str:
    info = pg_types.get(type_code)
    return _KIND_BY_TYPE.get(info.name, OTHER) if info else OTHER


def _convert(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return None if value.is_nan() else float(value)
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------- エラーメッセージ


class _AppError(Exception):
    """学習者に見せるアプリ側のエラー（COPY FROM STDIN のデータがない等）。"""


class _StatementError(Exception):
    """書き込み可能モードで、ある文の実行中に起きたDBエラー（位置の補正情報つき）。"""

    def __init__(self, exc: psycopg.Error, offset: int, prefix_len: int) -> None:
        super().__init__(str(exc))
        self.exc, self.offset, self.prefix_len = exc, offset, prefix_len


def _lineno_at(query: str, index: int) -> int:
    return query[: max(index, 0)].count("\n") + 1


def _error_message(
    query: str, exc: psycopg.Error, *, offset: int = 0, prefix_len: int = len(_DECLARE_PREFIX)
) -> tuple[str, int | None]:
    """(学習者向けメッセージ, 学習者SQL全体での行番号)。"""
    diag = exc.diag
    message = diag.message_primary or str(exc).splitlines()[0]
    if diag.message_hint:
        message += f"\nヒント: {diag.message_hint}"

    pos = None
    if diag.statement_position:
        relative = int(diag.statement_position) - prefix_len
        if relative >= 1:
            pos = relative
    lineno = _lineno_at(query, offset + pos - 1) if pos else None
    if lineno is None and offset:
        lineno = _lineno_at(query, offset)  # 位置が分からなければ文の先頭行

    if isinstance(exc, errors.SyntaxError):
        if diag.statement_position is None and prefix_len:
            message += "\nSQLは1文ずつ実行してください。"
        elif pos == 1 and prefix_len:
            message += "\n実行できるのは SELECT 文（WITH 句を含む）だけです。"
    elif isinstance(exc, errors.InsufficientPrivilege) and "COPY" in message.upper():
        message += (
            "\nこのアプリでは安全のため、DBサーバー上のファイルへの入出力はできません。"
            "COPY ... TO STDOUT（出力）/ COPY ... FROM STDIN（読み込み）を使ってください。"
        )
    elif isinstance(exc, (errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction)):
        if prefix_len:
            message += "\n教材データベースは読み取り専用です。"
        else:
            message += (
                "\n教材データベースのテーブルは変更できません（一時テーブルは作成できます）。"
            )
    return message, lineno


# ---------------------------------------------------------------- 実行の部品


def _fetch_table(conn: psycopg.Connection, cursor_name: str, max_rows: int) -> dict:
    cur = conn.execute(f"FETCH FORWARD {int(max_rows)} FROM {cursor_name}")
    rows = cur.fetchall()
    description = cur.description or []
    moved = conn.execute(f"MOVE FORWARD ALL IN {cursor_name}").statusmessage or "MOVE 0"
    remaining = int(moved.split()[-1])
    return {
        "type": "table",
        "columns": [d.name for d in description],
        "rows": [[_convert(v) for v in row] for row in rows],
        "kinds": [_kind(d.type_code) for d in description],
        "row_count": len(rows) + remaining,
        "truncated": remaining > 0,
    }


def _copy_out(conn: psycopg.Connection, statement: str) -> bytes:
    chunks, size = [], 0
    with conn.cursor().copy(statement) as copy:
        for chunk in copy:
            size += len(chunk)
            if size > MAX_COPY_BYTES:
                raise _AppError(
                    f"COPY の出力が大きすぎます（上限 {MAX_COPY_BYTES // 1024 // 1024}MB）"
                )
            chunks.append(bytes(chunk))
    return b"".join(chunks)


def _copy_in(conn: psycopg.Connection, statement: str, data: bytes) -> None:
    with conn.cursor().copy(statement) as copy:
        copy.write(data)


def split_statements(script: str) -> list[tuple[int, str]]:
    """[(script 内の開始位置, 文)]。文字列・コメント中の ; では分割しない。"""
    result, cursor = [], 0
    for statement in sqlparse.split(script):
        statement = statement.strip()
        if not statement or not sqlparse.format(statement, strip_comments=True).strip(" ;\n\t"):
            continue
        offset = script.find(statement, cursor)
        offset = cursor if offset < 0 else offset
        cursor = offset + len(statement)
        result.append((offset, statement))
    return result


def _classify(statement: str) -> str:
    body = sqlparse.format(statement, strip_comments=True).strip()
    if _COPY_OUT_RE.match(body):
        return "copy_out"
    if _COPY_IN_RE.match(body):
        return "copy_in"
    parsed = sqlparse.parse(statement)
    if parsed and parsed[0].get_type() == "SELECT" and not re.search(r"\bINTO\b", body, re.I):
        return "select"
    return "other"


def _without_trailing_semicolon(statement: str) -> str:
    return _TRAILING_RE.sub("", statement).rstrip()


def _file(index: int, data: bytes) -> dict:
    return {
        "path": f"COPY_TO_STDOUT_{index}",
        "size": len(data),
        "content_b64": base64.b64encode(data).decode("ascii"),
        "truncated": False,
    }


def _run_script(
    conn: psycopg.Connection,
    query: str,
    *,
    setup: str,
    stdin_query: str,
    max_rows: int,
) -> tuple[dict | None, list[dict]]:
    conn.execute("SET LOCAL search_path = pg_temp, public")  # CREATE TABLE は一時スキーマへ
    for _, statement in split_statements(setup):
        try:
            conn.execute(statement)
        except psycopg.Error as exc:
            raise _AppError(
                f"前提データの準備に失敗しました（アプリ側の問題の可能性があります）: {exc}"
            ) from exc
    stdin_data = _copy_out(conn, stdin_query) if stdin_query else None

    result, files = None, []
    for index, (offset, statement) in enumerate(split_statements(query)):
        kind = _classify(statement)
        prefix_len = 0
        try:
            if kind == "select":
                cursor_name = f"{CURSOR_NAME}{index}"
                prefix = f"DECLARE {cursor_name} NO SCROLL CURSOR FOR "
                prefix_len = len(prefix)
                conn.execute(prefix + _without_trailing_semicolon(statement), prepare=True)
                result = _fetch_table(conn, cursor_name, max_rows)
                conn.execute(f"CLOSE {cursor_name}")
            elif kind == "copy_out":
                files.append(_file(len(files) + 1, _copy_out(conn, statement)))
            elif kind == "copy_in":
                if stdin_data is None:
                    raise _AppError(
                        "この問題では COPY ... FROM STDIN で読み込むデータは用意されていません。"
                    )
                _copy_in(conn, statement, stdin_data)
            else:
                conn.execute(statement)
        except psycopg.Error as exc:
            raise _StatementError(exc, offset, prefix_len) from exc
    return result, files


# ---------------------------------------------------------------- 入口


def run_sql(
    sql: str,
    *,
    dsn: str,
    max_rows: int = 200,
    timeout_sec: float = 10.0,
    writable: bool = False,
    setup: str = "",
    stdin_query: str = "",
) -> dict:
    started = time.monotonic()
    query = normalize_sql(sql)
    if not query:
        return _response("error", started, error=_error("EmptyQuery", "SQLを入力してください"))
    writable = writable or bool(setup) or bool(stdin_query)

    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
    except psycopg.OperationalError:
        return _response(
            "unavailable",
            started,
            error=_error(
                "ConnectionError", "データベースに接続できません（起動中の可能性があります）"
            ),
        )

    files: list[dict] | None = [] if writable else None
    try:
        # read_only=True なら BEGIN READ ONLY、False なら BEGIN READ WRITE（ロール既定の読み取り専用を上書き）
        conn.read_only = not writable
        conn.execute(
            "SELECT set_config('statement_timeout', %s, true)", [f"{int(timeout_sec * 1000)}ms"]
        )
        if writable:
            result, files = _run_script(
                conn, query, setup=setup, stdin_query=stdin_query, max_rows=max_rows
            )
        else:
            conn.execute(_DECLARE_PREFIX + query, prepare=True)
            result = _fetch_table(conn, CURSOR_NAME, max_rows)
        return _response("ok", started, result=result, files=files)
    except errors.QueryCanceled:
        return _response(
            "timeout",
            started,
            error=_error("timeout", f"制限時間（{timeout_sec:g}秒）を超えました"),
            files=files,
        )
    except _StatementError as exc:
        if isinstance(exc.exc, errors.QueryCanceled):
            return _response(
                "timeout",
                started,
                error=_error("timeout", f"制限時間（{timeout_sec:g}秒）を超えました"),
                files=files,
            )
        message, lineno = _error_message(
            query, exc.exc, offset=exc.offset, prefix_len=exc.prefix_len
        )
        return _response(
            "error", started, error=_error(type(exc.exc).__name__, message, lineno), files=files
        )
    except _AppError as exc:
        return _response("error", started, error=_error("AppError", str(exc)), files=files)
    except psycopg.Error as exc:
        message, lineno = _error_message(query, exc)
        return _response("error", started, error=_error(type(exc).__name__, message, lineno))
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()
