# common_lib/ui/expander_style.py
# ============================================================
# expander style UI
#
# 機能：
# - theme連動 expander CSS
# - container key ごとの expander style
# - banner theme と連動
# ============================================================

from __future__ import annotations


# ============================================================
# imports
# ============================================================
from typing import Any

import streamlit as st


# ============================================================
# theme expander css
# ============================================================
def render_theme_expander_css(
    *,
    container_key: str,
    theme: dict[str, Any],
) -> None:

    theme_accent = theme["primary"]

    theme_border = theme["border"]

    theme_bg = theme["card_bg"]

    # ------------------------------------------------------------
    # css
    # ------------------------------------------------------------
    st.markdown(
        f"""
        <style>

        .st-key-{container_key} div[data-testid="stExpander"] {{
            border: 1px solid {theme_border};

            border-radius: 24px;

            background:
                linear-gradient(
                    135deg,
                    #ffffff 0%,
                    {theme_bg} 100%
                );

            box-shadow:
                0 12px 32px rgba(0,0,0,0.06);

            overflow: hidden;

            margin-top: 10px;
            margin-bottom: 22px;
        }}

        .st-key-{container_key} div[data-testid="stExpander"] summary {{
            padding: 10px 26px !important;
        }}

        .st-key-{container_key} div[data-testid="stExpander"] summary:hover {{
            background: rgba(255,255,255,0.45);
        }}

        .st-key-{container_key} div[data-testid="stExpander"] summary p {{
            /* font-size: 1.10rem !important; */
            font-size: 0.8rem !important;
            font-weight: 800 !important;
            color: {theme_accent} !important;
            letter-spacing: 0.01em;
        }} 

        
        /* =====================================================
           expander本文エリア
           - 説明文全体の余白
           - 説明文全体の行間
           ===================================================== */
        .st-key-{container_key} div[data-testid="stExpanderDetails"] {{
            padding: 14px 30px 28px 30px;

            border-top:
                1px solid {theme_border};

            background:
                rgba(255,255,255,0.58);

            /* 本文全体の行間 */
            line-height: 1.5;
        }}

        /* =====================================================
           expander本文の文字色・フォントサイズ
           - 背景を白系で固定しているため，文字色も濃色に固定する
           - ダークモードでも白背景＋白文字にならないようにする
           ===================================================== */
        .st-key-{container_key} div[data-testid="stExpanderDetails"] {{
            color: #262730 !important;
        }}

        .st-key-{container_key} div[data-testid="stExpanderDetails"] p,
        .st-key-{container_key} div[data-testid="stExpanderDetails"] li,
        .st-key-{container_key} div[data-testid="stExpanderDetails"] h1,
        .st-key-{container_key} div[data-testid="stExpanderDetails"] h2,
        .st-key-{container_key} div[data-testid="stExpanderDetails"] h3,
        .st-key-{container_key} div[data-testid="stExpanderDetails"] h4,
        .st-key-{container_key} div[data-testid="stExpanderDetails"] h5,
        .st-key-{container_key} div[data-testid="stExpanderDetails"] h6 {{
            color: #262730 !important;
        }}

        .st-key-{container_key} div[data-testid="stExpanderDetails"] p,
        .st-key-{container_key} div[data-testid="stExpanderDetails"] li {{
            font-size: 0.90rem !important;
        }}

        /* =====================================================
           tabs文字色
           - 非選択タブも白背景上で読めるようにする
           - 選択中タブはthemeのアクセント色を使用する
           ===================================================== */
        .st-key-{container_key}
        div[data-testid="stExpanderDetails"]
        button[data-baseweb="tab"] {{
            color: #555555 !important;
        }}

        .st-key-{container_key}
        div[data-testid="stExpanderDetails"]
        button[data-baseweb="tab"][aria-selected="true"] {{
            color: {theme_accent} !important;
        }}

        /* =====================================================
        区切り線（---）の上下余白
        ===================================================== */
        .st-key-{container_key} div[data-testid="stExpanderDetails"] hr {{
            margin-top: 0.3rem !important;
            margin-bottom: 0.3rem !important;
        }}
        
        </style>
        """,
        unsafe_allow_html=True,
    )