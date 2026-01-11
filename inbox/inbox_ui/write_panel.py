# -*- coding: utf-8 -*-
# common_lib/inbox/inbox_ui/write_panel.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import streamlit as st

from common_lib.inbox.inbox_common.tags import tags_json_from_input


# ============================================================
# Result container
# ============================================================
@dataclass
class WritePanelResult:
    uploaded_files: List[st.runtime.uploaded_file_manager.UploadedFile]
    tags_json: str
    write_clicked: bool
    clear_clicked: bool
    tag_text: str


# ============================================================
# UI panel
# ============================================================
def render_inbox_write_panel(
    *,
    key_prefix: str,
    title: str = "1) Drop して Inbox に書き込む（テスト）",
    caption: str = "複数ファイルOK。ここで入力したタグは「今回アップロードした全ファイルに共通」で付与します。",
    default_tag_text: str = "",
) -> WritePanelResult:
    """
    st.form を使わない前提のパネル。
    key_prefix を必須にして、key衝突をシステム的に防ぐ。
    """
    st.subheader(title)
    st.caption(caption)

    k_tag = f"{key_prefix}_tag_text"
    k_uploader = f"{key_prefix}_uploader"
    k_write = f"{key_prefix}_write"
    k_clear = f"{key_prefix}_clear"

    st.session_state.setdefault(k_tag, default_tag_text)

    tag_text = st.text_input(
        "共通タグ（任意）",
        value=st.session_state.get(k_tag, ""),
        key=k_tag,
        help="例：2025/001 または 2025/002/議事録。複数ならカンマ/空白/改行で区切れます。",
    )

    uploaded_files = st.file_uploader(
        "ファイルを drop / 選択（複数可）",
        accept_multiple_files=True,
        key=k_uploader,
    ) or []

    col_a, col_b = st.columns([1, 1])
    with col_a:
        write_clicked = st.button("📥 Inbox に書き込む", type="primary", width="stretch", key=k_write)
    with col_b:
        clear_clicked = st.button("🧹 結果表示をクリア", width="stretch", key=k_clear)

    return WritePanelResult(
        uploaded_files=uploaded_files,
        tags_json=tags_json_from_input(tag_text),
        write_clicked=bool(write_clicked),
        clear_clicked=bool(clear_clicked),
        tag_text=tag_text,
    )
