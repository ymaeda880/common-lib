# common_lib/busy/db.py
# =============================================================================
# ai_runs.db DBユーティリティ（共通ライブラリ / busy）
# - sqlite 接続（row_factory, PRAGMA）を共通化
# - ensure_db() で schema 正本（schema.py）を適用
# - WAL等の設定は sessions系と同じ思想で「素直で安全」に
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import SCHEMA_SQL


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path), check_same_thread=False)
    con.row_factory = sqlite3.Row

    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA journal_mode = WAL;")
    con.execute("PRAGMA synchronous = NORMAL;")
    con.execute("PRAGMA temp_store = MEMORY;")
    return con


def ensure_db(db_path: Path) -> None:
    """
    schema/migration の正本は schema.py（sessions系と同じ方針）。
    """
    con = connect(db_path)
    try:
        con.executescript(SCHEMA_SQL)
        con.commit()
    finally:
        con.close()
