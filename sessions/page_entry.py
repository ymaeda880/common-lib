# common_lib/sessions/page_entry.py
from __future__ import annotations

from pathlib import Path
import streamlit as st

from common_lib.auth.auth_helpers import require_login
from common_lib.storage.storages_config import resolve_storages_root
from common_lib.sessions import SessionConfig, init_session, heartbeat_tick


def page_session_heartbeat(
    st_module,
    projects_root: Path,
    *,
    app_name: str,
    page_name: str,
) -> str:
    """
    Streamlit page 先頭で 1 行呼ぶだけで：

    - require_login
    - init_session（初回のみ）
    - heartbeat_tick（一定間隔）
    - app_name / page_name を正しく記録
    """

    # ログイン必須
    sub = require_login(st_module)
    if not sub:
        st_module.stop()

    # sessions.db
    storages_root = resolve_storages_root(projects_root)
    sessions_db = (
        storages_root
        / "_admin"
        / "sessions"
        / "sessions.db"
    )

    cfg = SessionConfig()

    init_session(
        db_path=sessions_db,
        cfg=cfg,
        user_sub=sub,
        app_name=app_name,
        page_name=page_name,
    )

    heartbeat_tick(
        db_path=sessions_db,
        cfg=cfg,
        user_sub=sub,
        app_name=app_name,
        page_name=page_name,
    )

    return sub
