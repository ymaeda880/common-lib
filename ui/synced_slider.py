# -*- coding: utf-8 -*-
# common_lib/ui/synced_slider.py
# ============================================================
# Synced slider UI
#
# 機能：
# - text_input と slider を同期する整数入力UI
# - ◀ / ▶ ボタンで1ずつ移動する
# - raw_key / value_key を session_state の正本として扱う
# - formatter により 3桁番号などの表示整形に対応する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from collections.abc import Callable
from typing import Any

import streamlit as st


# ============================================================
# helper：int parse
# ============================================================
def parse_int_or_none(x: Any) -> int | None:
    try:
        s = str(x).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


# ============================================================
# helper：default formatter
# ============================================================
def format_int_default(x: int) -> str:
    return str(int(x))


# ============================================================
# helper：clamp
# ============================================================
def clamp_int(
    value: int,
    *,
    min_value: int,
    max_value: int,
) -> int:
    return max(int(min_value), min(int(max_value), int(value)))


# ============================================================
# main：text_input + ◀ ▶ + slider
# ============================================================
def render_synced_int_slider(
    *,
    label: str,
    raw_key: str,
    value_key: str,
    min_value: int,
    max_value: int,
    default_value: int,
    page_name: str,
    update_date_key: str | None = None,
    formatter: Callable[[int], str] | None = None,
    help_text: str | None = None,
    input_col_ratio: int = 2,
    slider_col_ratio: int = 5,
) -> int:
    # ------------------------------------------------------------
    # formatter
    # ------------------------------------------------------------
    fmt = formatter or format_int_default

    # ------------------------------------------------------------
    # session_state 初期化
    # ------------------------------------------------------------
    if value_key not in st.session_state:
        st.session_state[value_key] = clamp_int(
            int(default_value),
            min_value=min_value,
            max_value=max_value,
        )

    if raw_key not in st.session_state:
        st.session_state[raw_key] = fmt(int(st.session_state[value_key]))

    # ------------------------------------------------------------
    # callback：raw -> value
    # ------------------------------------------------------------
    def _on_raw_change() -> None:
        parsed = parse_int_or_none(st.session_state.get(raw_key))

        if parsed is None:
            return

        next_value = clamp_int(
            parsed,
            min_value=min_value,
            max_value=max_value,
        )

        st.session_state[value_key] = next_value
        st.session_state[raw_key] = fmt(next_value)

        if update_date_key:
            st.session_state[update_date_key] = __import__("datetime").date.today().isoformat()

    # ------------------------------------------------------------
    # callback：slider -> raw
    # ------------------------------------------------------------
    def _on_slider_change() -> None:
        next_value = clamp_int(
            int(st.session_state.get(value_key, default_value)),
            min_value=min_value,
            max_value=max_value,
        )

        st.session_state[value_key] = next_value
        st.session_state[raw_key] = fmt(next_value)

        if update_date_key:
            st.session_state[update_date_key] = __import__("datetime").date.today().isoformat()

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------
    col_input, col_control = st.columns([input_col_ratio, slider_col_ratio])

    with col_input:
        st.text_input(
            label,
            key=raw_key,
            on_change=_on_raw_change,
            help=help_text,
        )

    with col_control:
        col_left, col_slider, col_right = st.columns([1, 6, 1])

        with col_left:
            st.markdown("<div style='height: 26px;'></div>", unsafe_allow_html=True)

            def _on_minus_click() -> None:
                current = int(st.session_state.get(value_key, default_value))
                next_value = clamp_int(
                    current - 1,
                    min_value=min_value,
                    max_value=max_value,
                )
                st.session_state[value_key] = next_value
                st.session_state[raw_key] = fmt(next_value)

                if update_date_key:
                    st.session_state[update_date_key] = __import__("datetime").date.today().isoformat()

            st.button(
                "◀",
                key=f"{page_name}__{value_key}__minus",
                on_click=_on_minus_click,
            )

        with col_slider:
            st.slider(
                "\u200b",
                min_value=int(min_value),
                max_value=int(max_value),
                step=1,
                key=value_key,
                on_change=_on_slider_change,
                help=help_text,
            )

        with col_right:
            st.markdown("<div style='height: 26px;'></div>", unsafe_allow_html=True)

            def _on_plus_click() -> None:
                current = int(st.session_state.get(value_key, default_value))
                next_value = clamp_int(
                    current + 1,
                    min_value=min_value,
                    max_value=max_value,
                )
                st.session_state[value_key] = next_value
                st.session_state[raw_key] = fmt(next_value)

                if update_date_key:
                    st.session_state[update_date_key] = __import__("datetime").date.today().isoformat()

            st.button(
                "▶",
                key=f"{page_name}__{value_key}__plus",
                on_click=_on_plus_click,
            )

    return int(st.session_state.get(value_key, default_value))