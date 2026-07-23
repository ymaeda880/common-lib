# -*- coding: utf-8 -*-
# common_lib/ui/synced_controls/pending_state.py
# ============================================================

from __future__ import annotations


def init_pending(st, *, key: str) -> None:
    if key not in st.session_state:
        st.session_state[key] = {}


def set_pending(st, *, key: str, updates: dict) -> None:
    init_pending(st, key=key)

    pending = dict(st.session_state.get(key, {}) or {})
    pending.update(dict(updates or {}))
    st.session_state[key] = pending


def apply_pending_before_widgets(st, *, key: str) -> None:
    pending = dict(st.session_state.get(key, {}) or {})

    if not pending:
        return

    for k, v in pending.items():
        st.session_state[k] = v

    st.session_state[key] = {}