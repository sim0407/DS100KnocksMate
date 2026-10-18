"""学習者のSQLを教材用PostgreSQLで実行する（変更は必ずロールバック）。

安全性はSQL文字列の検査ではなく、DB側で担保する（docker/db/sql/03_roles.sql）:
- 教材テーブルは SELECT 権限のみ。作れるのはセッション専用の一時テーブルだけ
- 管理者のネットワークログイン不可、サーバ上のファイル入出力（COPY ... TO/FROM 'ファイル'）不可
- 本モジュールでも、文を実行する直前ごとに「実行全体の残り時間」を statement_timeout に
  設定し直す（複数文の合計も制限時間内。学習者が SET statement_timeout = 0 としても次の文で戻る）。
  最後に必ず ROLLBACK する

2つのモード:
- 読み取り専用（既定）: `BEGIN READ ONLY` で、`DECLARE ... CURSOR FOR <SQL>` を prepared
  statement として送る。SELECT系（WITH含む）以外は構文エラー、複数文はサーバ側で拒否される
- 書き込み可能（writable、テーブルを作る問題用）: 文ごとに分けて順に実行する。
  search_path を pg_temp 優先にし、`CREATE TABLE` は一時スキーマに作られる。
  SELECT はカーソル経由（巨大な結果でもメモリを使わない）、最後の SELECT の結果を返す。
  `COPY ... TO STDOUT` の出力は files に、`COPY ... FROM STDIN` には stdin_query の出力を流す。
FETCH で先頭 max_rows 行だけ（少しずつ、表1つあたり MAX_RESULT_BYTES まで）取得し、残りは MOVE で数える。
artifacts を指定すると、学習者のSQLの後で各テーブルを `SELECT * FROM 名前` で取り出し、
応答の artifacts に {名前: 表} として返す（1回の実行から複数のテーブルを取り出すため）。

戻り値はPythonワーカーと同じ形の辞書（status / result / stdout / error / elapsed_ms / files / artifacts）。
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
# 結果の表1つあたりの大きさの上限（文字数の概算）。UIと同じプロセスのメモリを守る
MAX_RESULT_BYTES = 64 * 1024 * 1024
FETCH_CHUNK_ROWS = 5000
_FIRST_CHUNK_ROWS = 100

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


def _response(
    status: str, started: float, *, result=None, error=None, files=None, artifacts=None
) -> dict:
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
    if artifacts is not None:
        response["artifacts"] = artifacts
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


class _Timeout(Exception):
    """実行全体の期限を過ぎた（次の文を実行する前に検出）。"""


class _ArtifactError(Exception):
    """採点対象のテーブルを取り出せなかった（テーブルがない等）。"""

    def __init__(self, exc: psycopg.Error) -> None:
        super().__init__(str(exc))
        self.exc = exc


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


class _Session:
    """1回の実行: 接続と、実行全体の期限。"""

    def __init__(self, conn: psycopg.Connection, timeout_sec: float) -> None:
        self.conn = conn
        self.expires_at = time.monotonic() + timeout_sec

    def arm(self) -> None:
        """次の文の statement_timeout を残り時間にする（期限切れなら _Timeout）。"""
        remaining_ms = int((self.expires_at - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            raise _Timeout
        self.conn.execute("SELECT set_config('statement_timeout', %s, true)", [f"{remaining_ms}ms"])

    def execute(self, statement: str, *, prepare: bool | None = None) -> psycopg.Cursor:
        self.arm()
        return self.conn.execute(statement, prepare=prepare)


def _row_size(row: list) -> int:
    return sum(len(v) if isinstance(v, str) else 8 for v in row) + 8


def _fetch_table(session: _Session, cursor_name: str, max_rows: int) -> dict:
    """カーソルから max_rows 行まで取得する。大きさが MAX_RESULT_BYTES を超えたらエラー。

    1行の大きさを見ながら1回に取る行数を決め、上限を大きく超えて読み込まないようにする。
    """
    rows: list[list] = []
    description: list = []
    size, chunk, largest = 0, _FIRST_CHUNK_ROWS, 1
    while len(rows) < max_rows:
        n = min(chunk, max_rows - len(rows))
        cur = session.execute(f"FETCH FORWARD {int(n)} FROM {cursor_name}")
        description = cur.description or description
        fetched = cur.fetchall()
        for raw in fetched:
            row = [_convert(v) for v in raw]
            row_size = _row_size(row)
            size += row_size
            largest = max(largest, row_size)
            if size > MAX_RESULT_BYTES:
                raise _AppError(
                    f"結果が大きすぎます（上限 約{MAX_RESULT_BYTES // 1024 // 1024}MB）。"
                    "LIMIT で行数を絞るか、列を選んでください"
                )
            rows.append(row)
        if len(fetched) < n:
            break
        chunk = max(1, min(FETCH_CHUNK_ROWS, (MAX_RESULT_BYTES - size) // largest))
    moved = session.execute(f"MOVE FORWARD ALL IN {cursor_name}").statusmessage or "MOVE 0"
    remaining = int(moved.split()[-1])
    return {
        "type": "table",
        "columns": [d.name for d in description],
        "rows": rows,
        "kinds": [_kind(d.type_code) for d in description],
        "row_count": len(rows) + remaining,
        "truncated": remaining > 0,
    }


def _copy_out(session: _Session, statement: str) -> bytes:
    chunks, size = [], 0
    session.arm()
    with session.conn.cursor().copy(statement) as copy:
        for chunk in copy:
            size += len(chunk)
            if size > MAX_COPY_BYTES:
                raise _AppError(
                    f"COPY の出力が大きすぎます（上限 {MAX_COPY_BYTES // 1024 // 1024}MB）"
                )
            chunks.append(bytes(chunk))
    return b"".join(chunks)


def _copy_in(session: _Session, statement: str, data: bytes) -> None:
    session.arm()
    with session.conn.cursor().copy(statement) as copy:
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
    session: _Session,
    query: str,
    *,
    setup: str,
    stdin_query: str,
    max_rows: int,
) -> tuple[dict | None, list[dict]]:
    session.execute("SET LOCAL search_path = pg_temp, public")  # CREATE TABLE は一時スキーマへ
    for _, statement in split_statements(setup):
        try:
            session.execute(statement)
        except psycopg.Error as exc:
            if isinstance(exc, errors.QueryCanceled):
                raise
            raise _AppError(
                f"前提データの準備に失敗しました（アプリ側の問題の可能性があります）: {exc}"
            ) from exc
    stdin_data = _copy_out(session, stdin_query) if stdin_query else None

    result, files = None, []
    for index, (offset, statement) in enumerate(split_statements(query)):
        kind = _classify(statement)
        prefix_len = 0
        try:
            if kind == "select":
                cursor_name = f"{CURSOR_NAME}{index}"
                prefix = f"DECLARE {cursor_name} NO SCROLL CURSOR FOR "
                prefix_len = len(prefix)
                result = None  # 前の結果を先に手放す（メモリ）
                session.execute(prefix + _without_trailing_semicolon(statement), prepare=True)
                result = _fetch_table(session, cursor_name, max_rows)
                session.execute(f"CLOSE {cursor_name}")
            elif kind == "copy_out":
                files.append(_file(len(files) + 1, _copy_out(session, statement)))
            elif kind == "copy_in":
                if stdin_data is None:
                    raise _AppError(
                        "この問題では COPY ... FROM STDIN で読み込むデータは用意されていません。"
                    )
                _copy_in(session, statement, stdin_data)
            else:
                session.execute(statement)
        except psycopg.Error as exc:
            raise _StatementError(exc, offset, prefix_len) from exc
    return result, files


def _fetch_artifacts(session: _Session, artifacts: tuple[str, ...], max_rows: int) -> dict:
    """学習者のSQLが作ったテーブルを取り出す（名前は採点定義で識別子と確認済み）。"""
    tables = {}
    for index, name in enumerate(artifacts):
        if not name.isidentifier():
            raise ValueError(f"テーブル名として使えません: {name!r}")
        cursor_name = f"knocks_artifact{index}"
        try:
            session.execute(f"DECLARE {cursor_name} NO SCROLL CURSOR FOR SELECT * FROM {name}")
            tables[name] = _fetch_table(session, cursor_name, max_rows)
            session.execute(f"CLOSE {cursor_name}")
        except psycopg.Error as exc:
            if isinstance(exc, errors.QueryCanceled):
                raise
            raise _ArtifactError(exc) from exc
    return tables


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
    artifacts: tuple[str, ...] = (),
) -> dict:
    """artifacts: 実行後に取り出すテーブル名（応答の artifacts に {名前: 表} で返す）。"""
    started = time.monotonic()
    query = normalize_sql(sql)
    if not query:
        return _response("error", started, error=_error("EmptyQuery", "SQLを入力してください"))
    artifacts = tuple(artifacts)
    writable = writable or bool(setup) or bool(stdin_query) or bool(artifacts)

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

    def timed_out() -> dict:
        message = f"制限時間（{timeout_sec:g}秒）を超えました"
        return _response("timeout", started, error=_error("timeout", message), files=files)

    try:
        # read_only=True なら BEGIN READ ONLY、False なら BEGIN READ WRITE（ロール既定の読み取り専用を上書き）
        conn.read_only = not writable
        session = _Session(conn, timeout_sec)
        if writable:
            result, files = _run_script(
                session, query, setup=setup, stdin_query=stdin_query, max_rows=max_rows
            )
        else:
            session.execute(_DECLARE_PREFIX + query, prepare=True)
            result = _fetch_table(session, CURSOR_NAME, max_rows)
        tables = _fetch_artifacts(session, artifacts, max_rows) if artifacts else None
        return _response("ok", started, result=result, files=files, artifacts=tables)
    except (_Timeout, errors.QueryCanceled):
        return timed_out()
    except _StatementError as exc:
        if isinstance(exc.exc, errors.QueryCanceled):
            return timed_out()
        message, lineno = _error_message(
            query, exc.exc, offset=exc.offset, prefix_len=exc.prefix_len
        )
        return _response(
            "error", started, error=_error(type(exc.exc).__name__, message, lineno), files=files
        )
    except _ArtifactError as exc:
        message = exc.exc.diag.message_primary or str(exc.exc).splitlines()[0]
        return _response("error", started, error=_error(type(exc.exc).__name__, message))
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
