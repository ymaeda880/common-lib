# common_lib/sessions/streamlit_integration.py
from __future__ import annotations

from pathlib import Path
from typing import Optional
import uuid

import streamlit as st

from .config import SessionConfig
from .recorder import record_login, record_heartbeat
from .sampler import maybe_sample_minute
from .time_utils import now_jst


def get_or_create_session_id(key: str = "prec_session_id") -> str:
    sid = st.session_state.get(key)
    if isinstance(sid, str) and sid.strip():
        return sid
    sid = str(uuid.uuid4())
    st.session_state[key] = sid
    return sid

def init_session(
    *,
    db_path: Path,
    cfg: SessionConfig,
    user_sub: str,
    app_name: str,
    page_name: str | None = None,
    session_state_key: str = "prec_session_id",
    init_flag_key: str = "prec_session_inited",
) -> str:
    """
    初回のみ「login 相当」を記録する。
    """
    session_id = get_or_create_session_id(session_state_key)

    already = st.session_state.get(init_flag_key)
    if already is True:
        return session_id

    record_login(
        db_path=db_path,
        cfg=cfg,
        user_sub=user_sub,
        session_id=session_id,
        app_name=app_name,
        page_name=page_name,
        user_agent=None,
        client_ip=None,
    )
    st.session_state[init_flag_key] = True
    return session_id

def heartbeat_tick(
    *,
    db_path: Path,
    cfg: SessionConfig,
    user_sub: str,
    app_name: str,
    page_name: str | None = None,
    session_state_key: str = "prec_session_id",
    last_hb_key: str = "prec_last_hb_ts",
) -> str:
    session_id = get_or_create_session_id(session_state_key)

    now = now_jst().timestamp()
    last = st.session_state.get(last_hb_key)
    should_hb = (not isinstance(last, (int, float))) or (now - float(last) >= cfg.heartbeat_sec)

    if should_hb:
        record_heartbeat(
            db_path=db_path,
            cfg=cfg,
            user_sub=user_sub,
            session_id=session_id,
            app_name=app_name,
            page_name=page_name,
        )
        st.session_state[last_hb_key] = now

    maybe_sample_minute(db_path=db_path, cfg=cfg, app_name=app_name)
    return session_id
