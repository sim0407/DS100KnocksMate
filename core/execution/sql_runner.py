"""学習者のSQLを教材用PostgreSQLで読み取り専用に実行する。

安全性はSQL文字列の検査ではなく、DB側で担保する（docker/db/sql/03_roles.sql）:
- SELECT権限のみのロール、一時テーブル作成不可、管理者のネットワークログイン不可
- 本関数でも BEGIN READ ONLY、statement_timeout、ROLLBACK を必ず行う
実行方法:
- `DECLARE ... CURSOR FOR <SQL>` を prepared statement として送る。これにより
  SELECT系（WITH含む）以外の文は構文エラー、複数文はサーバ側で拒否される
- FETCH で先頭 max_rows 行だけ取得し、残りは MOVE で数える（巨大な結果でもメモリを使わない）

戻り値はPythonワーカーと同じ形の辞書（status / result / stdout / error / elapsed_ms 等）。
"""

from __future__ import annotations

import datetime as dt
import math
import time
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import errors
from psycopg.postgres import types as pg_types

from core.execution.results import BOOLEAN, DATETIME, FLOAT, INTEGER, OTHER, STRING

CURSOR_NAME = "knocks_q"
_DECLARE_PREFIX = f"DECLARE {CURSOR_NAME} NO SCROLL CURSOR FOR "

_KIND_BY_TYPE = {
    **dict.fromkeys(("int2", "int4", "int8", "oid"), INTEGER),
    **dict.fromkeys(("numeric", "float4", "float8"), FLOAT),
    **dict.fromkeys(("text", "varchar", "bpchar", "char", "name"), STRING),
    **dict.fromkeys(("date", "timestamp", "timestamptz"), DATETIME),
    "bool": BOOLEAN,
}


def normalize_sql(sql: str) -> str:
    """前後の空白と、Notebookの `%%sql` 行を除く（Notebookからの貼り付けに対応）。"""
    lines = sql.strip().splitlines()
    if lines and lines[0].strip() == "%%sql":
        lines = lines[1:]
    return "\n".join(lines).strip()


def _response(status: str, started: float, *, result=None, error=None) -> dict:
    return {
        "status": status,
        "result": result,
        "stdout": "",
        "stdout_truncated": False,
        "stderr": "",
        "stderr_truncated": False,
        "error": error,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


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


def _learner_lineno(query: str, exc: psycopg.Error) -> tuple[int | None, int | None]:
    """(学習者SQL内の文字位置, 行番号)。位置が無い・DECLARE部分を指す場合は None。"""
    raw = exc.diag.statement_position
    if not raw:
        return None, None
    pos = int(raw) - len(_DECLARE_PREFIX)
    if pos < 1:
        return None, None
    return pos, query[: pos - 1].count("\n") + 1


def _error_message(query: str, exc: psycopg.Error) -> tuple[str, int | None]:
    diag = exc.diag
    message = diag.message_primary or str(exc).splitlines()[0]
    if diag.message_hint:
        message += f"\nヒント: {diag.message_hint}"
    pos, lineno = _learner_lineno(query, exc)
    if isinstance(exc, errors.SyntaxError):
        if diag.statement_position is None:
            message += "\nSQLは1文ずつ実行してください。"
        elif pos == 1:
            message += "\n実行できるのは SELECT 文（WITH 句を含む）だけです。"
    elif isinstance(exc, (errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction)):
        message += "\n教材データベースは読み取り専用です。"
    return message, lineno


def run_sql(sql: str, *, dsn: str, max_rows: int = 200, timeout_sec: float = 10.0) -> dict:
    started = time.monotonic()
    query = normalize_sql(sql)
    if not query:
        return _response("error", started, error=_error("EmptyQuery", "SQLを入力してください"))

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

    try:
        conn.read_only = True  # 最初の文で BEGIN READ ONLY が発行される
        conn.execute(
            "SELECT set_config('statement_timeout', %s, true)", [f"{int(timeout_sec * 1000)}ms"]
        )
        conn.execute(_DECLARE_PREFIX + query, prepare=True)
        cur = conn.execute(f"FETCH FORWARD {int(max_rows)} FROM {CURSOR_NAME}")
        rows = cur.fetchall()
        description = cur.description or []
        moved = conn.execute(f"MOVE FORWARD ALL IN {CURSOR_NAME}").statusmessage or "MOVE 0"
        remaining = int(moved.split()[-1])
        result = {
            "type": "table",
            "columns": [d.name for d in description],
            "rows": [[_convert(v) for v in row] for row in rows],
            "kinds": [_kind(d.type_code) for d in description],
            "row_count": len(rows) + remaining,
            "truncated": remaining > 0,
        }
        return _response("ok", started, result=result)
    except errors.QueryCanceled:
        return _response(
            "timeout",
            started,
            error=_error("timeout", f"制限時間（{timeout_sec:g}秒）を超えました"),
        )
    except psycopg.Error as exc:
        message, lineno = _error_message(query, exc)
        return _response("error", started, error=_error(type(exc).__name__, message, lineno))
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()
