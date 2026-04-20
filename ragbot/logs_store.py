# common_lib/ragbot/logs_store.py
# =============================================================================
# ragbot 質問・回答ログ保存（common_lib）
#
# 役割:
# - sqlite3 に質問・回答ログを保存する
# - DB / テーブルを自動初期化する
# - 根拠は保存せず、質問・回答・model 等だけを保存する
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# =============================================================================
# local imports
# =============================================================================
from common_lib.ragbot.paths import get_ragbot_history_db_path


# =============================================================================
# helper
# =============================================================================
def _now_iso_utc() -> str:
    # -------------------------------------------------------------------------
    # UTC ISO文字列
    # -------------------------------------------------------------------------
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: Path) -> sqlite3.Connection:
    # -------------------------------------------------------------------------
    # sqlite 接続
    # -------------------------------------------------------------------------
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# schema
# =============================================================================
def ensure_history_db(
    *,
    projects_root: str | Path,
    user_sub: str,
) -> Path:
    # -------------------------------------------------------------------------
    # DB とテーブルを作成
    # -------------------------------------------------------------------------
    db_path = get_ragbot_history_db_path(
        projects_root=projects_root,
        user_sub=user_sub,
        create_parent=True,
    )

    with _connect(db_path) as conn:
        cur = conn.cursor()

        # ---------------------------------------------------------------------
        # qa_history
        # ---------------------------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                user_sub TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                model_key TEXT NOT NULL,
                use_stream INTEGER NOT NULL DEFAULT 0,
                top_k INTEGER NOT NULL DEFAULT 0,
                selected_years_json TEXT NOT NULL DEFAULT '[]',
                hit_count INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT ''
            )
            """
        )

        # ---------------------------------------------------------------------
        # index
        # ---------------------------------------------------------------------
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_qa_history_created_at
            ON qa_history(created_at)
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_qa_history_user_sub
            ON qa_history(user_sub)
            """
        )

        conn.commit()

    return db_path


# =============================================================================
# insert
# =============================================================================
def insert_qa_history(
    *,
    projects_root: str | Path,
    user_sub: str,
    question: str,
    answer: str,
    model_key: str,
    use_stream: bool,
    top_k: int,
    selected_years: list[int] | None = None,
    hit_count: int = 0,
    note: str = "",
) -> int:
    # -------------------------------------------------------------------------
    # qa_history に 1 件追加
    # -------------------------------------------------------------------------
    db_path = ensure_history_db(
        projects_root=projects_root,
        user_sub=user_sub,
    )

    selected_years_json = json.dumps(
        [int(y) for y in list(selected_years or [])],
        ensure_ascii=False,
    )

    with _connect(db_path) as conn:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO qa_history (
                created_at,
                user_sub,
                question,
                answer,
                model_key,
                use_stream,
                top_k,
                selected_years_json,
                hit_count,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now_iso_utc(),
                str(user_sub or "").strip(),
                str(question or "").strip(),
                str(answer or "").strip(),
                str(model_key or "").strip(),
                1 if bool(use_stream) else 0,
                int(top_k),
                selected_years_json,
                int(hit_count),
                str(note or ""),
            ),
        )

        conn.commit()
        row_id = int(cur.lastrowid)

    return row_id