# common_lib/ui/theme_colors.py
# =============================================================================
# UI用：バナー配色からテーマカラーを生成する共通ライブラリ
#
# 機能：
# - banner_lines.py の BANNER_STYLES を正本として使う
# - "light_blue" などの banner key から HEX 色を抽出する
# - intro_panel.py などで使うテーマ色 dict を生成する
#
# 方針：
# - バナー配色の正本は banner_lines.py に置く
# - このファイルでは色抽出・テーマ変換だけを担当する
# - 未定義キーは KeyError で明確に停止する
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
import re
from typing import Dict

from common_lib.ui.banner_lines import BANNER_STYLES


# =============================================================================
# HEXカラー抽出
# =============================================================================
def extract_hex_colors_from_css_background(style: str) -> list[str]:
    """
    CSS background 文字列から HEX カラーを抽出する
    """
    return re.findall(r"#[0-9a-fA-F]{6}", style)


# =============================================================================
# HEXカラー取得
# =============================================================================
def get_primary_secondary_from_banner_key(banner_key: str) -> tuple[str, str]:
    """
    banner key から primary / secondary 色を取得する
    """
    if banner_key not in BANNER_STYLES:
        raise KeyError(f"Unknown banner style key: {banner_key}")

    style = BANNER_STYLES[banner_key]
    colors = extract_hex_colors_from_css_background(style)

    if len(colors) >= 2:
        return colors[0], colors[1]

    if len(colors) == 1:
        return colors[0], colors[0]

    raise ValueError(f"No HEX color found in banner style: {banner_key}")


# =============================================================================
# テーマカラー生成
# =============================================================================
def get_theme_colors_from_banner_key(banner_key: str) -> Dict[str, str]:
    """
    banner key から UI テーマカラーを生成する
    """
    primary, secondary = get_primary_secondary_from_banner_key(banner_key)

    return {
        "primary": primary,
        "secondary": secondary,
        "hero_bg": f"linear-gradient(135deg,{secondary}22 0%,#ffffff 58%,{primary}18 100%)",
        "border": f"{secondary}66",
        "shadow": f"{primary}22",
        "text": "#3f3a4f",
        "title": "#262233",
        "card_title": "#2d2840",
        "highlight": primary,
        "chip_bg": f"{secondary}33",
        "chip_text": primary,
        "card_bg": "#ffffff",
    }