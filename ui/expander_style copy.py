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

    # ------------------------------------------------------------
    # debug
    # ------------------------------------------------------------
    # st.write("DEBUG container_key =", container_key)

    # st.write("DEBUG theme =", theme)

    # st.write(
    #     "DEBUG keys =",
    #     list(theme.keys()),
    # )

    # st.write(
    #     "DEBUG accent =",
    #     theme.get("accent"),
    # )

    # st.write(
    #     "DEBUG border =",
    #     theme.get("border"),
    # )

    # st.write(
    #     "DEBUG bg =",
    #     theme.get("bg"),
    # )


    # ------------------------------------------------------------
    # theme values
    # ------------------------------------------------------------
    # theme_accent = theme.get(
    #     "accent",
    #     "#15803d",
    # )

    # theme_border = theme.get(
    #     "border",
    #     "rgba(34, 197, 94, 0.35)",
    # )

    # theme_bg = theme.get(
    #     "bg",
    #     "#f4fff7",
    # )

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
            <!-- font-size: 1.10rem !important; -->
            font-size: 0.8rem !important;
            font-weight: 800 !important;
            color: {theme_accent} !important;
            letter-spacing: 0.01em;
        }}

        .st-key-{container_key} div[data-testid="stExpanderDetails"] {{
            padding: 14px 30px 28px 30px;

            border-top:
                1px solid {theme_border};

            background:
                rgba(255,255,255,0.58);

            line-height: 1.9;
        }}

        </style>
        """,
        unsafe_allow_html=True,
    )