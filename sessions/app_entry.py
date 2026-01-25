# common_lib/sessions/app_entry.py
from __future__ import annotations

from pathlib import Path

from common_lib.auth.auth_helpers import require_login
from common_lib.storage.storages_config import resolve_storages_root
from common_lib.sessions import SessionConfig, init_session, heartbeat_tick

def app_session_heartbeat(
    st,
    projects_root: Path,
    *,
    app_name: str,
    cfg: SessionConfig | None = None,
) -> str:
    """
    app.py 先頭で 1 行呼ぶだけで：

    - require_login
    - init_session（初回のみ）
    - heartbeat_tick（一定間隔）

    を行う。
    """

    # ログイン必須
    sub = require_login(st)
    if not sub:
        st.stop()

    # sessions.db
    storages_root = resolve_storages_root(projects_root)
    sessions_db = (
        storages_root
        / "_admin"
        / "sessions"
        / "sessions.db"
    )

    cfg = cfg or SessionConfig()

    # app.py 用の固定 page_name
    page_name = "__app__"

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
