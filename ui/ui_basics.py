"""
common_lib/ui/ui_basics.py
==========================================
Streamlit UI 補助関数（共通コンポーネント）

提供機能
--------
- thick_divider(color: str = "#666", height: int = 3, margin: str = "1.5em 0")
    カスタム区切り線（HTML/CSSベース）を表示。
    Streamlit 標準の st.divider() よりも太さや色を制御できる。

使用例
------

from common_lib.ui.ui_basics import thick_divider

thick_divider("#007ACC", 4)
"""

import streamlit as st

# --------------------------------------------
# 🎨 カラー定義（HTMLカラーコード）
# --------------------------------------------
COLOR_PRESETS = {
    "Blue": "#007ACC",        # Visual Studio風ブルー
    "Red": "#E74C3C",         # 明るい赤
    "Green": "#2ECC71",       # 落ち着いた緑
    "Orange": "#E67E22",      # オレンジ
    "Gray": "#666666",        # 標準グレー
    "LightGray": "#CCCCCC",   # 薄いグレー
    "Navy": "#004080",        # 濃い青
    "Cyan": "#33CCFF",        # 水色
}


def thick_divider(color: str = "Gray", height: int = 3, margin: str = "1.5em 0") -> None:
    """
    カスタム区切り線を表示する。

    Parameters
    ----------
    color : str, optional
        線の色（CSSカラーコードまたは色名）, by default "#666"
    height : int, optional
        線の太さ（px単位）, by default 3
    margin : str, optional
        上下マージン（CSS形式, 例: "2em 0"）, by default "1.5em 0"

    Examples
    --------
    >>> thick_divider("#007ACC", 4)
    >>> thick_divider("red", 2, "0.5em 0")
    """

    # プリセット名の場合は辞書から解決
    color_resolved = COLOR_PRESETS.get(color, color)

    st.markdown(
        f"""
        <hr style="
            height:{height}px;
            border:none;
            background-color:{color_resolved};
            margin:{margin};
        ">
        """,
        unsafe_allow_html=True,
    )


def subtitle(
    text: str,
    *,
    font_size: str = "1.05rem",
    font_weight: int = 600,
    color: str = "#444",
    border_color: str = "#ddd",
    margin_top: str = "-6px",
    margin_bottom: str = "6px",
) -> None:
    """
    ページ用サブタイトルを表示する（title の直下想定）。

    Parameters
    ----------
    text : str
        表示するサブタイトル文字列
    """
    st.markdown(
        f"""
        <div style="
            font-size:{font_size};
            font-weight:{font_weight};
            color:{color};
            border-left:4px solid {border_color};
            padding-left:8px;
            margin-top:{margin_top};
            margin-bottom:{margin_bottom};
        ">
            {text}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("")
