# common_lib/busy/query.py
# =============================================================================
# ai_runs.db クエリ（共通ライブラリ / busy）
# - 最近の run 一覧（条件付き）
# - running の run 一覧
# - run_id 指定の run 取得
# - run_id 指定のイベント取得（ai_busy_events）
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .db import connect, ensure_db
from .paths import resolve_ai_runs_db_path


def list_recent_runs(
    *,
    projects_root: Path,
    limit: int = 50,
    user_sub: Optional[str] = None,
    app_name: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    db_path = resolve_ai_runs_db_path(projects_root)
    ensure_db(db_path)

    con = connect(db_path)
    try:
        wh: list[str] = []
        params: dict[str, Any] = {"limit": int(limit)}

        if user_sub:
            wh.append("user_sub = :user_sub")
            params["user_sub"] = user_sub
        if app_name:
            wh.append("app_name = :app_name")
            params["app_name"] = app_name
        if status:
            wh.append("status = :status")
            params["status"] = status

        where_sql = ("WHERE " + " AND ".join(wh)) if wh else ""
        sql = f"""
        SELECT *
        FROM ai_runs
        {where_sql}
        ORDER BY started_at DESC
        LIMIT :limit
        """
        rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def list_running_runs(
    *,
    projects_root: Path,
    limit: int = 200,
) -> list[dict[str, Any]]:
    return list_recent_runs(projects_root=projects_root, limit=limit, status="running")


def get_run(
    *,
    projects_root: Path,
    run_id: str,
) -> Optional[dict[str, Any]]:
    db_path = resolve_ai_runs_db_path(projects_root)
    ensure_db(db_path)

    con = connect(db_path)
    try:
        row = con.execute("SELECT * FROM ai_runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def list_events_for_run(
    *,
    projects_root: Path,
    run_id: str,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    db_path = resolve_ai_runs_db_path(projects_root)
    ensure_db(db_path)

    con = connect(db_path)
    try:
        rows = con.execute(
            """
            SELECT *
            FROM ai_busy_events
            WHERE run_id = ?
            ORDER BY ts ASC
            LIMIT ?
            """,
            (run_id, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()
