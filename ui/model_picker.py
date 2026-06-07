# -*- coding: utf-8 -*-
# common_lib/ui/model_picker.py
# ============================================================
# Text モデル選択 UI（共通）
# - provider:model 形式の model_key を返す
# - 表示順・既定値は ai.models 側の正本に従う
# - Gemini が使えない環境では自動的に除外
# ============================================================

from __future__ import annotations
from typing import List, Tuple

import streamlit as st


# ============================================================
# Public API
# ============================================================
def render_text_model_picker(
    *,
    title: str,
    catalog: List[Tuple[str, str]],
    session_key: str,
    default_key: str,
    page_name: str,
    gemini_available: bool,
) -> str:
    """
    Text モデル選択（radio）
    Returns:
        model_key（provider:model）
    """

    # ------------------------------------------------------------
    # 見出し
    # ------------------------------------------------------------
    st.header(title)

    # ------------------------------------------------------------
    # 表示用ラベル / 内部キー
    # ------------------------------------------------------------
    # keys = [x[1] for x in catalog]
    # labels = [k.split(":", 1)[1] if ":" in k else k for k in keys]

    # ------------------------------------------------------------
    # 表示用ラベル / 内部キー
    # - catalog 側の表示名をそのまま使う
    # ------------------------------------------------------------
    # labels = [x[0] for x in catalog]
    # keys = [x[1] for x in catalog]

    # ------------------------------------------------------------
    # 表示用ラベル / 内部キー
    # - Azure のみ識別表示を付ける
    # ------------------------------------------------------------
    keys = [x[1] for x in catalog]

    labels = []

    for k in keys:
        if k.startswith("azure:"):
            labels.append(f"(Azure) {k.split(':', 1)[1]}")
        else:
            labels.append(k.split(":", 1)[1] if ":" in k else k)

    # ------------------------------------------------------------
    # Gemini が使えない場合は候補から除外
    # ------------------------------------------------------------
    # if not gemini_available:
    #     filtered = [(lab, k) for (lab, k) in catalog if not k.startswith("gemini:")]
    #     keys = [x[1] for x in filtered]
    #     labels = [k.split(":", 1)[1] if ":" in k else k for k in keys]
    #     st.caption("Gemini はこの環境では利用できないため候補から除外しています。")

    # if not gemini_available:
    #     filtered = [(lab, k) for (lab, k) in catalog if not k.startswith("gemini:")]

    #     labels = [x[0] for x in filtered]
    #     keys = [x[1] for x in filtered]

    #     st.caption("Gemini はこの環境では利用できないため候補から除外しています。")

    if not gemini_available:
        filtered = [(lab, k) for (lab, k) in catalog if not k.startswith("gemini:")]

        keys = [x[1] for x in filtered]

        labels = []

        for k in keys:
            if k.startswith("azure:"):
                labels.append(f"(Azure) {k.split(':', 1)[1]}")
            else:
                labels.append(k.split(":", 1)[1] if ":" in k else k)

        st.caption("Gemini はこの環境では利用できないため候補から除外しています。")   

    # ------------------------------------------------------------
    # session_state の正規化（既定値へ寄せる）
    # ------------------------------------------------------------
    current_key = str(st.session_state.get(session_key) or default_key)
    if current_key not in keys:
        current_key = default_key
        st.session_state[session_key] = current_key

    current_index = keys.index(current_key)

    # ------------------------------------------------------------
    # radio UI
    # ------------------------------------------------------------
    picked_label = st.radio(
        "モデル",
        options=labels,
        index=current_index,
        key=f"{page_name}__model_radio",
    )

    # ------------------------------------------------------------
    # label → key の復元
    # ------------------------------------------------------------
    picked_key = keys[labels.index(picked_label)]
    if picked_key != st.session_state.get(session_key):
        st.session_state[session_key] = picked_key
        st.rerun()

    # ------------------------------------------------------------
    # 現在のモデル名（表示用）
    # ------------------------------------------------------------
    _, cur_model = st.session_state[session_key].split(":", 1)
    st.caption(f"現在: **{cur_model}**")

    return st.session_state[session_key]


# ============================================================
# Public API（Transcribe）
# ============================================================
def render_transcribe_model_picker(
    *,
    title: str,
    models: list[str],
    session_key: str,
    default_model: str,
    page_name: str,
    gemini_available: bool,
) -> str:
    """
    Transcribe モデル選択（radio）
    Returns:
        model（例: whisper-1 / gemini-2.0-flash）
    """

    # ------------------------------------------------------------
    # 見出し
    # ------------------------------------------------------------
    st.header(title)

    # ------------------------------------------------------------
    # 候補（Gemini 利用不可なら gemini-* を除外）
    # ------------------------------------------------------------
    options = list(models)

    if not gemini_available:
        options = [m for m in options if not str(m).startswith("gemini")]
        st.caption("Gemini はこの環境では利用できないため候補から除外しています。")

    # ------------------------------------------------------------
    # session_state の正規化（既定値へ寄せる）
    # ------------------------------------------------------------
    current = str(st.session_state.get(session_key) or default_model)
    if current not in options:
        current = default_model if default_model in options else (options[0] if options else "")
        st.session_state[session_key] = current

    if not options:
        st.warning("利用可能なモデルがありません。")
        return str(st.session_state.get(session_key) or "")

    # ------------------------------------------------------------
    # radio UI
    # ------------------------------------------------------------
    picked = st.radio(
        "使用モデル",
        options=options,
        index=options.index(current),
        key=f"{page_name}__transcribe_model_radio",
    )

    if picked != st.session_state.get(session_key):
        st.session_state[session_key] = picked
        st.rerun()

    st.caption(f"現在: **{st.session_state[session_key]}**")

    return st.session_state[session_key]

# ============================================================
# Public API（Image）
# ============================================================
def render_image_model_picker(
    *,
    title: str,
    catalog: List[Tuple[str, str]],
    session_key: str,
    default_key: str,
    page_name: str,
    gemini_available: bool,
) -> str:
    """
    Image モデル選択（radio）
    Returns:
        model_key（provider:model）
    """

    # ------------------------------------------------------------
    # 見出し
    # ------------------------------------------------------------
    st.header(title)

    # ------------------------------------------------------------
    # 候補
    # ------------------------------------------------------------
    filtered = list(catalog)

    if not gemini_available:
        filtered = [(lab, k) for (lab, k) in filtered if not k.startswith("gemini:")]
        st.caption("Gemini はこの環境では利用できないため候補から除外しています。")

    keys = [x[1] for x in filtered]
    labels = [x[0] for x in filtered]

    if not keys:
        st.warning("利用可能な画像モデルがありません。")
        return ""

    # ------------------------------------------------------------
    # session_state の正規化
    # ------------------------------------------------------------
    current_key = str(st.session_state.get(session_key) or default_key)

    if current_key not in keys:
        current_key = default_key if default_key in keys else keys[0]
        st.session_state[session_key] = current_key

    current_index = keys.index(current_key)

    # ------------------------------------------------------------
    # radio UI
    # ------------------------------------------------------------
    picked_label = st.radio(
        "画像生成モデル",
        options=labels,
        index=current_index,
        key=f"{page_name}__image_model_radio",
    )

    picked_key = keys[labels.index(picked_label)]

    if picked_key != st.session_state.get(session_key):
        st.session_state[session_key] = picked_key
        st.rerun()

    # ------------------------------------------------------------
    # 現在のモデル名
    # ------------------------------------------------------------
    provider, cur_model = st.session_state[session_key].split(":", 1)
    st.caption(f"現在: **{provider} / {cur_model}**")

    return st.session_state[session_key]