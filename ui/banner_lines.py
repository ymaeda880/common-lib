# common_lib/ui/banner_lines.py
# =============================================================================
# UI用：横ライン型バナー（情報ゼロ・色だけ）
#
# 目的：
# - app.py / 各 page の最上部などで使う「視覚的区切り」
# - 画像不使用／高さ固定（px）／use_container_width 不使用
#
# 方針：
# - st.markdown + HTML div のみ
# - style 属性内に改行・空行を入れない（重要）
#
# 提供API：
# - render_banner_line(style: str, height_px: int = 24, radius_px: int = 4)
# - render_banner_line_by_key(key: str, height_px: int = 24, radius_px: int = 4)
# - BANNER_STYLES: 見本・共通定義
# =============================================================================

from __future__ import annotations

import streamlit as st
from typing import Dict


# =============================================================================
# バナー配色定義（正本）
# =============================================================================
BANNER_STYLES: Dict[str, str] = {
    # --- 暗色・業務向け ---
    "navy_standard": "linear-gradient(90deg,#2b2f4a,#5b5fd6)",
    "navy_heavy": "linear-gradient(90deg,#1f2436,#3a3f7a)",
    "blue_purple": "linear-gradient(90deg,#243b55,#5f2c82)",
    "gray_minimal": "linear-gradient(90deg,#2a2a2a,#4a4a4a)",
    "navy_solid": "#2b2f4a",
    "navy_dark": "#151a2d",

    # --- 中間色 ---
    "teal_public": "linear-gradient(90deg,#0f3d3e,#1f7a7a)",
    "green_safe": "linear-gradient(90deg,#1b3a2f,#2e7d32)",
    "brown_culture": "linear-gradient(90deg,#3b2f2f,#6d4c41)",
    "wine": "linear-gradient(90deg,#3a1f2b,#7a2e4a)",
    "ochre": "linear-gradient(90deg,#5a4a2f,#a07c2c)",
    "slate_blue": "linear-gradient(90deg,#2f3b4a,#4f6a8a)",

    # --- 明るい色調 ---
    "light_blue": "linear-gradient(90deg,#5fa8ff,#8fd3f4)",
    "cyan_clean": "linear-gradient(90deg,#4dd0e1,#80deea)",
    "light_green": "linear-gradient(90deg,#66bb6a,#a5d6a7)",
    "lime": "linear-gradient(90deg,#9ccc65,#dcedc8)",
    "yellow_soft": "linear-gradient(90deg,#fbc02d,#fff176)",
    "orange_event": "linear-gradient(90deg,#fb8c00,#ffcc80)",
    "pink_soft": "linear-gradient(90deg,#f48fb1,#f8bbd0)",
    "purple_light": "linear-gradient(90deg,#b39ddb,#d1c4e9)",

        # --- 明るい赤・暖色系 ---
    "red_soft": "linear-gradient(90deg,#ef5350,#e57373)",        # やわらかい赤
    "salmon": "linear-gradient(90deg,#ff8a65,#ffab91)",         # サーモン系（軽め）
    "coral_light": "linear-gradient(90deg,#ff7043,#ffab91)",   # コーラル寄り
    "rose": "linear-gradient(90deg,#f06292,#f8bbd0)",           # ローズ（赤×ピンク）
    "peach": "linear-gradient(90deg,#ff9e80,#ffccbc)",         # ピーチ系
    "red_orange": "linear-gradient(90deg,#f4511e,#ffb74d)",    # 赤橙（イベント向き）

}


# =============================================================================
# 基本レンダラ
# =============================================================================
def render_banner_line(
    style: str,
    *,
    height_px: int = 24,
    radius_px: int = 4,
    margin_bottom_px: int = 8,
) -> None:
    """
    横ライン型バナーを描画する（最小UI部品）

    Parameters
    ----------
    style : str
        CSS の background 値（単色 or linear-gradient）
    height_px : int
        高さ（px）
    radius_px : int
        角丸（px）
    margin_bottom_px : int
        下マージン（px）
    """
    html = (
        f'<div style="width:100%;'
        f'height:{height_px}px;'
        f'background:{style};'
        f'border-radius:{radius_px}px;'
        f'margin-bottom:{margin_bottom_px}px;"></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# =============================================================================
# キー指定レンダラ（推奨）
# =============================================================================
def render_banner_line_by_key(
    key: str,
    *,
    height_px: int = 24,
    radius_px: int = 4,
    margin_bottom_px: int = 8,
) -> None:
    """
    定義済みキーから横ライン型バナーを描画する

    Raises
    ------
    KeyError
        未定義キー指定時
    """
    if key not in BANNER_STYLES:
        raise KeyError(f"Unknown banner style key: {key}")

    render_banner_line(
        BANNER_STYLES[key],
        height_px=height_px,
        radius_px=radius_px,
        margin_bottom_px=margin_bottom_px,
    )


# =============================================================================
# 見本表示用（デモ・確認用）
# =============================================================================
def render_all_banner_samples(
    *,
    height_px: int = 24,
    radius_px: int = 4,
    margin_bottom_px: int = 8,
) -> None:
    """
    定義済みすべてのバナーを順に表示する（見本ページ用）
    """
    for key, style in BANNER_STYLES.items():
        render_banner_line(
            style,
            height_px=height_px,
            radius_px=radius_px,
            margin_bottom_px=margin_bottom_px,
        )


# page / app.py 側での使い方（例）
# from common_lib.ui.banner_lines import render_banner_line_by_key

# # app.py 最上部
# render_banner_line_by_key("navy_standard")

# from common_lib.ui.banner_lines import render_all_banner_samples

# # 見本ページ
# render_all_banner_samples()