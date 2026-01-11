# common_lib/sessions/recorder.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import SessionConfig
from .db import ensure_db
from .time_utils import now_jst, dt_to_iso


def record_login(
    *,
    db_path: Path,
    cfg: SessionConfig,
    user_sub: str,
    session_id: str,
    app_name: str,
    user_agent: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> None:
    """
    ログイン成功時に session_state を upsert。

    注意：
    - logout を厳密には受け取れない（ブラウザ閉じ等）ため、last_seen と TTL が正本。
    - login は「開始点」として持つ。再ログインやページ復帰は last_seen 更新で吸収。
    """
    now = now_jst()
    now_iso = dt_to_iso(now)

    con = ensure_db(db_path)
    try:
        con.execute(
            """
            INSERT INTO session_state(
              session_id, user_sub, app_name,
              login_at, last_seen, logout_at,
              user_agent, client_ip
            )
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
              user_sub   = excluded.user_sub,
              app_name   = excluded.app_name,
              -- login_at は最初の値を温存したい場合は COALESCE にする。
              -- ここでは「最新ログイン」を採用して更新する（要件に合わせて変更可能）。
              login_at   = excluded.login_at,
              last_seen  = excluded.last_seen,
              logout_at  = NULL,
              user_agent = excluded.user_agent,
              client_ip  = excluded.client_ip
            """,
            (session_id, user_sub, app_name, now_iso, now_iso, None, user_agent, client_ip),
        )
        con.commit()
    finally:
        con.close()


def record_heartbeat(
    *,
    db_path: Path,
    cfg: SessionConfig,
    user_sub: str,
    session_id: str,
    app_name: str,
) -> None:
    """
    生存更新：last_seen を更新する。

    期待：
    - app.py 側で 30秒間隔（cfg.heartbeat_sec）を目安に呼ぶ
    - 本関数は呼ばれた分だけ更新する（間引きは app.py 側で実施してよい）
    """
    now = now_jst()
    now_iso = dt_to_iso(now)

    con = ensure_db(db_path)
    try:
        # session_state が無い場合は login 扱いで作ってしまう（運用上の安全策）。
        # ただし “login を必ず先に記録する” 運用なら、ここをエラーにする設計も可能。
        con.execute(
            """
            INSERT INTO session_state(
              session_id, user_sub, app_name,
              login_at, last_seen, logout_at
            )
            VALUES(?,?,?,?,?,NULL)
            ON CONFLICT(session_id) DO UPDATE SET
              user_sub  = excluded.user_sub,
              app_name  = excluded.app_name,
              last_seen = excluded.last_seen,
              logout_at = NULL
            """,
            (session_id, user_sub, app_name, now_iso, now_iso),
        )
        con.commit()
    finally:
        con.close()


def record_logout(
    *,
    db_path: Path,
    cfg: SessionConfig,
    user_sub: str,
    session_id: str,
    app_name: str,
) -> None:
    """
    明示 logout（押された時だけ来る想定）。
    来なくても TTL で自然に inactive 扱いになるので必須ではない。
    """
    now = now_jst()
    now_iso = dt_to_iso(now)

    con = ensure_db(db_path)
    try:
        con.execute(
            """
            UPDATE session_state
               SET logout_at = ?,
                   last_seen = ?
             WHERE session_id = ?
            """,
            (now_iso, now_iso, session_id),
        )
        con.commit()
    finally:
        con.close()
