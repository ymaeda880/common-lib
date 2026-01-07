# -*- coding: utf-8 -*-
# common_lib/inbox_bulk/state.py
from __future__ import annotations

import json
from typing import Any, Dict


def update_where_sig_and_maybe_clear_checked(
    *,
    st_session_state: Any,
    where_sql: str,
    params: Dict[str, Any],
    key_where_sig: str,
    key_checked: str,
    key_page: str,
    toast_func: Any,
) -> None:
    """
    where/params のシグネチャが変わったら、checked と page を安全のためクリアする。
    """
    sig_obj = {"where": where_sql, "params": params}
    sig = json.dumps(sig_obj, ensure_ascii=False, default=str)

    prev_sig = st_session_state.get(key_where_sig)
    if prev_sig is None:
        st_session_state[key_where_sig] = sig
        return

    if prev_sig != sig:
        st_session_state[key_where_sig] = sig
        st_session_state[key_checked] = set()
        st_session_state[key_page] = 0
        toast_func("検索条件が変わったため、チェック選択をクリアしました。", icon="🧹")
