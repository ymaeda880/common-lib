# common_lib/sessions/queries.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import SessionConfig
from .db import ensure_db, scalar_int
from .time_utils import now_jst, dt_to_iso


def get_active_counts(
    *,
    db_path: Path,
    cfg: SessionConfig,
    app_name: Optional[str] = None,
) -> Dict[str, int]:
    """
    現在の active を TTL で判定して数を返す。

    戻り値：
      - active_users
      - active_sessions
    """
    con = ensure_db(db_path)
    try:
        # last_seen >= now - ttl
        # SQLite で ISO を比較するため、ISO文字列を統一（JST, seconds）している。
        now_iso = dt_to_iso(now_jst())

        params: list[Any] = [now_iso, cfg.ttl_sec]
        where_app = ""
        if app_name:
            where_app = " AND app_name = ?"
            params.append(app_name)

        # 注意：ISO文字列の差分計算は SQLite では扱いにくい。
        # ここでは datetime() 関数で "now - ttl seconds" を作って比較する。
        # ただし "now" はDB側時刻でなく、アプリ側 now_iso を基準にしたいので、
        # datetime(?, printf('-%d seconds', ttl)) を用いる。
        active_sessions = scalar_int(
            con,
            f"""
            SELECT COUNT(*)
              FROM session_state
             WHERE last_seen >= datetime(?, printf('-%d seconds', ?))
               AND logout_at IS NULL
               {where_app}
            """,
            tuple(params),
        )

        active_users = scalar_int(
            con,
            f"""
            SELECT COUNT(DISTINCT user_sub)
              FROM session_state
             WHERE last_seen >= datetime(?, printf('-%d seconds', ?))
               AND logout_at IS NULL
               {where_app}
            """,
            tuple(params),
        )

        return {"active_users": active_users, "active_sessions": active_sessions}
    finally:
        con.close()


def get_active_sessions(
    *,
    db_path: Path,
    cfg: SessionConfig,
    app_name: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """
    現在 active の session 一覧（管理画面用）
    """
    con = ensure_db(db_path)
    try:
        now_iso = dt_to_iso(now_jst())
        params: list[Any] = [now_iso, cfg.ttl_sec]
        where_app = ""
        if app_name:
            where_app = " AND app_name = ?"
            params.append(app_name)

        rows = con.execute(
            f"""
            SELECT session_id, user_sub, app_name, login_at, last_seen, logout_at, user_agent, client_ip
              FROM session_state
             WHERE last_seen >= datetime(?, printf('-%d seconds', ?))
               AND logout_at IS NULL
               {where_app}
             ORDER BY last_seen DESC
             LIMIT ?
            """,
            tuple(params + [limit]),
        ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(dict(r))
        return out
    finally:
        con.close()
