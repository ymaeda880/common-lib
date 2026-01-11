# common_lib/sessions/db.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from .schema import SCHEMA_SQL


# common_lib/sessions/db.py

def connect_db(db_path: Path) -> sqlite3.Connection:
    """
    sessions.db に接続して返す。

    方針（重要）：
    - DBファイル自体は sqlite に作らせる
    - Storages/_admin/sessions までは自動作成を許可
    - Storages より上は必須（存在しなければ設定ミスとして停止）
    """

    if not isinstance(db_path, Path):
        raise TypeError("db_path must be pathlib.Path")

    sessions_dir = db_path.parent              # .../Storages/_admin/sessions
    admin_dir = sessions_dir.parent            # .../Storages/_admin
    storages_dir = admin_dir.parent             # .../Storages

    # Storages は必須（ここが無ければ設計・設定ミス）
    if not storages_dir.exists() or not storages_dir.is_dir():
        raise FileNotFoundError(
            f"Storages directory not found (must exist): {storages_dir}"
        )

    # _admin は作成してよい
    if not admin_dir.exists():
        admin_dir.mkdir(parents=True, exist_ok=True)

    # sessions も作成してよい
    if not sessions_dir.exists():
        sessions_dir.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(db_path), check_same_thread=False)
    con.row_factory = sqlite3.Row

    # 並行性・耐障害性のための pragma
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")

    return con


def init_schema(con: sqlite3.Connection) -> None:
    """必要テーブルを作成（idempotent）"""
    con.executescript(SCHEMA_SQL)
    con.commit()


def ensure_db(db_path: Path) -> sqlite3.Connection:
    """接続＋スキーマ初期化まで行う（呼び出し側は close する）"""
    con = connect_db(db_path)
    init_schema(con)
    return con


def scalar_int(con: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    cur = con.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return 0
    v = row[0]
    return int(v) if v is not None else 0
