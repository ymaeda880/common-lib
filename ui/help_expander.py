# common_lib/ui/help_expander.py
# ============================================================
# Themed help expander
#
# 機能：
# - 各 app/page の説明 expander を共通描画する
# - theme に合わせた expander CSS を適用する
# - tabs=[("タブ名", "HTML/Markdown本文"), ...] を描画する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import re
from collections.abc import Callable
from typing import Any

import streamlit as st

from common_lib.ui.expander_style import render_theme_expander_css
from common_lib.ui.theme_colors import get_theme_colors_from_banner_key


# ============================================================
# themed help expander
# ============================================================
# ============================================================
# themed help expander
# ============================================================
def render_themed_help_expander(
    *,
    expander_key: str,
    expander_title: str,
    tabs: list[
        tuple[
            str,
            str | Callable[[], None],
        ]
    ],
    theme: dict[str, Any] | None = None,
    banner_key: str = "navy_dark",
    expanded: bool = False,
    before_tabs: Callable[[], None] | None = None,
) -> None:
    """
    テーマ付きの説明expanderを描画する。

    tabsの本文には、次のいずれかを指定できる。

    - Markdown／HTML文字列
    - 描画処理を行う引数なし関数

    before_tabsには、st.tabs()作成前に実行する
    CSS適用関数などを指定できる。
    """
    # ------------------------------------------------------------
    # theme
    # ------------------------------------------------------------
    if theme is None:
        theme = get_theme_colors_from_banner_key(
            banner_key
        )

    # ------------------------------------------------------------
    # safe container key
    # ------------------------------------------------------------
    safe_key = re.sub(
        r"[^0-9a-zA-Z_]+",
        "_",
        expander_key,
    )

    container_key = f"{safe_key}_theme_area"

    # ------------------------------------------------------------
    # expander css
    # ------------------------------------------------------------
    render_theme_expander_css(
        container_key=container_key,
        theme=theme,
    )

    # ------------------------------------------------------------
    # container
    # ------------------------------------------------------------
    theme_area = st.container(
        key=container_key,
    )

    # ------------------------------------------------------------
    # expander + tabs
    # ------------------------------------------------------------
    with theme_area:
        with st.expander(
            expander_title,
            expanded=expanded,
        ):
            if not tabs:
                st.caption("説明は未設定です。")
                return

            # ----------------------------------------------------
            # タブ作成前の追加処理
            #
            # 例：
            # - タブ用CSSの適用
            # ----------------------------------------------------
            if before_tabs is not None:
                before_tabs()

            tab_titles = [
                title
                for title, _content in tabs
            ]

            st_tabs = st.tabs(
                tab_titles,
            )

            for st_tab, (_title, content) in zip(
                st_tabs,
                tabs,
            ):
                with st_tab:
                    # --------------------------------------------
                    # 関数形式
                    # --------------------------------------------
                    if callable(content):
                        content()

                    # --------------------------------------------
                    # Markdown／HTML文字列形式
                    # --------------------------------------------
                    else:
                        st.markdown(
                            content,
                            unsafe_allow_html=True,
                        )