# -*- coding: utf-8 -*-

# common_lib/ui/common_styles.py

# ============================================================
# 共通UIスタイル
#
# 機能：
# - 複数のUIコンポーネントで使用する共通CSSを管理する
# - 文字色などの汎用インラインスタイルを定義する
#
# 方針：
# - 特定のパネルやページに依存しない
# - 色指定などの汎用スタイルだけを管理する
# ============================================================

from __future__ import annotations

import streamlit as st


# ============================================================
# 共通CSS
# ============================================================

COMMON_UI_CSS = """
<style>

/* ==========================================================
   インライン文字色
   ========================================================== */

.green {
    color: #2E7D32;
    font-weight: 700;
}

.red {
    color: #C62828;
    font-weight: 700;
}

.blue {
    color: #1565C0;
    font-weight: 700;
}

.orange {
    color: #EF6C00;
    font-weight: 700;
}

.gray {
    color: #6B7280;
    font-weight: 700;
}


/* ==========================================================
   情報パネル背景色
   ========================================================== */

.panel-green {
    background-color: #F0FDF4 !important;
    border-color: #86EFAC !important;
}

.panel-red {
    background-color: #FFF1F2 !important;
    border-color: #FCA5A5 !important;
}

.panel-blue {
    background-color: #EFF6FF !important;
    border-color: #93C5FD !important;
}

.panel-orange {
    background-color: #FFF7ED !important;
    border-color: #FDBA74 !important;
}

.panel-yellow {
    background-color: #FFFBEB !important;
    border-color: #FCD34D !important;
}

.panel-gray {
    background-color: #F9FAFB !important;
    border-color: #D1D5DB !important;
}

</style>
"""


# ============================================================
# 共通CSS描画
# ============================================================

def render_common_ui_css() -> None:
    """
    common_lib.ui 共通のCSSを描画する．
    """

    st.markdown(
        COMMON_UI_CSS,
        unsafe_allow_html=True,
    )