# -*- coding: utf-8 -*-
# common_lib/ui/tab_style.py
# ============================================================
# Streamlit Tabs 共通CSS
# ============================================================

from __future__ import annotations

import streamlit as st


def apply_tab_css(
    *,
    columns: int = 5,
) -> None:
    """
    Streamlitのst.tabs()をGrid表示にする共通CSSを適用する。

    Parameters
    ----------
    columns
        1行あたりのタブ数
    """

    st.markdown(
        f"""
<style>

/* ----------------------------------------------------------
   Tab List
---------------------------------------------------------- */
div[data-baseweb="tab-list"] {{
    display: grid !important;
    grid-template-columns: repeat({columns}, minmax(0, 1fr));
    gap: 8px;

    width: 100%;

    margin-bottom: 12px;

    border-bottom: none !important;
}}

/* ----------------------------------------------------------
   Tab
---------------------------------------------------------- */
button[data-baseweb="tab"] {{

    width: 100% !important;
    min-width: 0 !important;

    height: 42px;

    margin: 0 !important;
    padding: 0 12px !important;

    display: flex;
    justify-content: center;
    align-items: center;

    border-radius: 8px 8px 0 0;

    border: 1px solid #d9d9d9 !important;
    border-bottom: 3px solid transparent !important;

    background: #f7f7f7;

    font-size: 14px;
    font-weight: 500;

    transition: all .15s ease;
}}

button[data-baseweb="tab"] p {{
    margin: 0;
    width: 100%;
    text-align: center;
}}

/* ----------------------------------------------------------
   Hover
---------------------------------------------------------- */
button[data-baseweb="tab"]:hover {{
    background: #efefef;
}}

/* ----------------------------------------------------------
   Selected
---------------------------------------------------------- */
button[data-baseweb="tab"][aria-selected="true"] {{
    background: white;

    color: #d62728;

    font-weight: 700;

    border-bottom: 3px solid #d62728 !important;
}}

/* Streamlit標準の赤線を消す */
div[data-baseweb="tab-highlight"] {{
    display: none !important;
}}

/* Tab Panel */
div[data-baseweb="tab-panel"] {{
    padding-top: 8px;
}}

</style>
""",
        unsafe_allow_html=True,
    )