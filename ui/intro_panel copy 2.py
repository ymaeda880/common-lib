# common_lib/ui/intro_panel.py
# =============================================================================
# UI用：アプリトップページ用イントロパネル
#
# 機能：
# - hero パネルを描画する
# - chip を描画する
# - 情報カードを描画する
# - 2カラムカードを描画する
#
# 方針：
# - 色は theme_colors.py で生成した theme dict を受け取る
# - style 属性内に空行を入れない
# - use_container_width は使わない
# - フォントサイズ・行間・余白は呼び出し側で必要に応じて上書きできる
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from html import escape
from typing import Dict, List

import streamlit as st


# =============================================================================
# CSS描画
# =============================================================================
def render_intro_css(theme: Dict[str, str]) -> None:
    """
    intro panel 用 CSS を描画する
    """
    st.markdown(
        f"""
<style>
.ts-hero{{
    border-radius:22px;
    padding:30px 34px;
    margin-top:24px;
    margin-bottom:24px;
    background:{theme["hero_bg"]};
    border:1px solid {theme["border"]};
    box-shadow:0 10px 28px {theme["shadow"]};
}}
.ts-kicker{{
    font-size:0.82rem;
    font-weight:800;
    color:{theme["highlight"]};
    letter-spacing:0.10em;
    margin-bottom:10px;
}}
.ts-hero-title{{
    font-size:1.55rem;
    font-weight:800;
    color:{theme["title"]};
    margin-bottom:14px;
}}
.ts-body{{
    font-size:1.00rem;
    line-height:1.9;
    color:{theme["text"]};
}}
.ts-highlight{{
    color:{theme["highlight"]};
    font-weight:800;
}}
.ts-chip{{
    display:inline-block;
    border-radius:999px;
    padding:5px 12px;
    margin:14px 8px 0 0;
    background:{theme["chip_bg"]};
    color:{theme["chip_text"]};
    font-size:0.82rem;
    font-weight:800;
}}
.ts-card{{
    border-radius:18px;
    background:{theme["card_bg"]};
    border:1px solid {theme["border"]};
    box-shadow:0 8px 22px {theme["shadow"]};
}}
.ts-card-title{{
    font-size:1.08rem;
    font-weight:800;
    color:{theme["card_title"]};
    margin-bottom:10px;
}}
.ts-card-body{{
    font-size:0.94rem;
    line-height:1.85;
    color:{theme["text"]};
}}
</style>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# chip HTML生成
# =============================================================================
def _make_chip_html(chips: List[str]) -> str:
    """
    chip 一覧の HTML を生成する
    """
    return "\n".join(
        f'<span class="ts-chip">{escape(chip)}</span>'
        for chip in chips
    )


# =============================================================================
# hero panel 描画
# =============================================================================
def render_hero_panel(
    *,
    kicker: str,
    title: str,
    body_html: str,
    chips: List[str],
) -> None:
    """
    hero パネルを描画する
    """
    chips_html = _make_chip_html(chips)

    html = (
        '<div class="ts-hero">'
        f'<div class="ts-kicker">{escape(kicker)}</div>'
        f'<div class="ts-hero-title">{escape(title)}</div>'
        f'<div class="ts-body">{body_html}</div>'
        f'<div>{chips_html}</div>'
        '</div>'
    )

    st.markdown(html, unsafe_allow_html=True)


# =============================================================================
# normal info card 描画
# ＜＜＜ノーマル版＞＞＞
# 
# =============================================================================
# =============================================================================
# info card 描画
# =============================================================================
def render_info_card(
    *,
    title: str,
    body_html: str,
    title_font_size: str = "1.08rem",
    body_font_size: str = "0.94rem",
    body_line_height: str = "1.85",
    card_padding: str = "22px 24px",
    title_margin_bottom: str = "10px",
    body_margin_top: str = "0px",
    body_margin_bottom: str = "0px",
) -> None:
    """
    情報カードを1枚描画する
    """
    html = (
        f'<div class="ts-card" '
        f'style="padding:{card_padding};">'
        f'<div class="ts-card-title" '
        f'style="font-size:{title_font_size};'
        f'font-weight:800;'
        f'margin-bottom:{title_margin_bottom};">'
        f'{escape(title)}'
        '</div>'
        f'<div class="ts-card-body" '
        f'style="font-size:{body_font_size};'
        f'line-height:{body_line_height};'
        f'margin-top:{body_margin_top};'
        f'margin-bottom:{body_margin_bottom};">'
        f'{body_html}'
        '</div>'
        '</div>'
    )

    st.markdown(html, unsafe_allow_html=True)


# =============================================================================
# 2カラムカード描画
# =============================================================================
def render_two_column_cards(
    *,
    left_title: str,
    left_body_html: str,
    right_title: str,
    right_body_html: str,
    title_font_size: str = "1.08rem",
    body_font_size: str = "0.94rem",
    body_line_height: str = "1.85",
    card_padding: str = "22px 24px",
    title_margin_bottom: str = "10px",
    body_margin_top: str = "0px",
    body_margin_bottom: str = "0px",
) -> None:
    """
    2カラムの情報カードを描画する
    """
    c1, c2 = st.columns(2)

    with c1:
        render_info_card(
            title=left_title,
            body_html=left_body_html,
            title_font_size=title_font_size,
            body_font_size=body_font_size,
            body_line_height=body_line_height,
            card_padding=card_padding,
            title_margin_bottom=title_margin_bottom,
            body_margin_top=body_margin_top,
            body_margin_bottom=body_margin_bottom,
        )

    with c2:
        render_info_card(
            title=right_title,
            body_html=right_body_html,
            title_font_size=title_font_size,
            body_font_size=body_font_size,
            body_line_height=body_line_height,
            card_padding=card_padding,
            title_margin_bottom=title_margin_bottom,
            body_margin_top=body_margin_top,
            body_margin_bottom=body_margin_bottom,
        )



# =============================================================================
# compact info card 描画
# ＜＜＜コンパクト版＞＞＞
# タイトルの下の説明書きに使用する
# =============================================================================
# =============================================================================
# compact info card style
# =============================================================================
COMPACT_INFO_TITLE_FONT_SIZE = "0.92rem"

#COMPACT_INFO_BODY_FONT_SIZE = "0.82rem"
COMPACT_INFO_BODY_FONT_SIZE = "0.92rem"
COMPACT_INFO_BODY_LINE_HEIGHT = "1.3"

COMPACT_INFO_CARD_PADDING = "4px 14px"

COMPACT_INFO_TITLE_MARGIN_BOTTOM = "0px"

COMPACT_INFO_BODY_MARGIN_TOP = "6px"
COMPACT_INFO_BODY_MARGIN_BOTTOM = "0px"

COMPACT_INFO_ITEM_MARGIN_BOTTOM = "4px"

COMPACT_INFO_UL_MARGIN_TOP = "0.2rem"
COMPACT_INFO_UL_MARGIN_BOTTOM = "0"

COMPACT_INFO_UL_PADDING_LEFT = "1.2rem"


# =============================================================================
# compact info card 描画
# ＜＜＜コンパクト版＞＞＞
# タイトルの下の説明書きに使用する
# =============================================================================
def render_info_card_compact(
    *,
    title: str = "",
    body_html: str,
) -> None:
    """
    コンパクト版の情報カードを1枚描画する
    """

    render_info_card(
        title=title,
        body_html=body_html,
        title_font_size=COMPACT_INFO_TITLE_FONT_SIZE,
        body_font_size=COMPACT_INFO_BODY_FONT_SIZE,
        body_line_height=COMPACT_INFO_BODY_LINE_HEIGHT,
        card_padding=COMPACT_INFO_CARD_PADDING,
        title_margin_bottom=COMPACT_INFO_TITLE_MARGIN_BOTTOM,
        body_margin_top=COMPACT_INFO_BODY_MARGIN_TOP,
        body_margin_bottom=COMPACT_INFO_BODY_MARGIN_BOTTOM,
    )


# =============================================================================
# compact info card 描画（終了）
# =============================================================================


# =============================================================================
# compact bullet info card 描画
# =============================================================================
def render_info_card_bullets_compact(
    *,
    items: list[str],
    title: str = "",
) -> None:
    """
    文章リストをコンパクトな箇条書きカードとして描画する。
    """

    # -------------------------------------------------------------------------
    # 行HTML
    # -------------------------------------------------------------------------
    li_html = "\n".join(
        (
            f'<div style="'
            f'display:flex; '
            f'align-items:flex-start; '
            f'gap:0.18rem; '
            f'margin:0 0 {COMPACT_INFO_ITEM_MARGIN_BOTTOM} 0; '
            f'padding:0; '
            f'font-size:{COMPACT_INFO_BODY_FONT_SIZE}; '
            f'line-height:{COMPACT_INFO_BODY_LINE_HEIGHT};'
            f'">'
            f'<span style="flex:0 0 1.0em;">•</span>'
            f'<span style="flex:1;">{item}</span>'
            f'</div>'
        )
        for item in items
    )

    # -------------------------------------------------------------------------
    # body HTML
    # -------------------------------------------------------------------------
    body_html = (
        f'<div style="'
        f'margin:0; '
        f'padding-left:0.35rem;'
        f'">'
        f'{li_html}'
        f'</div>'
    )

    # -------------------------------------------------------------------------
    # render
    # -------------------------------------------------------------------------
    render_info_card(
        title=title,
        body_html=body_html,
        title_font_size=COMPACT_INFO_TITLE_FONT_SIZE,
        body_font_size=COMPACT_INFO_BODY_FONT_SIZE,
        body_line_height=COMPACT_INFO_BODY_LINE_HEIGHT,
        card_padding=COMPACT_INFO_CARD_PADDING,
        title_margin_bottom=COMPACT_INFO_TITLE_MARGIN_BOTTOM,
        body_margin_top=COMPACT_INFO_BODY_MARGIN_TOP,
        body_margin_bottom=COMPACT_INFO_BODY_MARGIN_BOTTOM,
    )


# =============================================================================
# compact bullet info card 描画（終了）
# =============================================================================


# =============================================================================
# compact bullet info card（行ごと bullet 指定版）
# -----------------------------------------------------------------------------
# 機能:
# - 行ごとに bullet を変更できる
# - compact info card の箇条書き版
# - bullet は tuple の 1要素目で指定する
#
# 使用例:
# render_info_card_bullets_custom(
#     title="処理フロー",
#     items=[
#         ("①", "Word解析"),
#         ("②", "中間テキスト保存"),
#         ("③", "AI校正"),
#         ("✅", "Word/PDFダウンロード"),
#     ],
# )
# =============================================================================
def render_info_card_bullets_compact_custom(
    *,
    items: list[tuple[str, str]],
    title: str = "",
) -> None:
    """
    行ごとに bullet を変更できる compact bullet card

    Parameters
    ----------
    items:
        [
            ("✅", "Word解析"),
            ("📄", "中間テキスト保存"),
            ("🤖", "AI校正"),
        ]
    """

    li_html = "\n".join(
        (
            f'<div style="'
            f'display:flex; '
            f'align-items:flex-start; '
            f'gap:0.18rem; '
            f'margin:0 0 {COMPACT_INFO_ITEM_MARGIN_BOTTOM} 0; '
            f'padding:0; '
            f'font-size:{COMPACT_INFO_BODY_FONT_SIZE}; '
            f'line-height:{COMPACT_INFO_BODY_LINE_HEIGHT};'
            f'">'
            f'<span style="flex:0 0 1.2em;">{bullet}</span>'
            f'<span style="flex:1;">{text}</span>'
            f'</div>'
        )
        for bullet, text in items
    )
    # -------------------------------------------------------------------------
    # body HTML
    # -------------------------------------------------------------------------
    body_html = (
        f'<ul style="'
        f'margin-top:{COMPACT_INFO_UL_MARGIN_TOP}; '
        f'margin-bottom:{COMPACT_INFO_UL_MARGIN_BOTTOM}; '
        f'margin-left:0; '
        f'padding-left:0.3rem; '
        f'">'
        f'{li_html}'
        '</ul>'
    )

    # -------------------------------------------------------------------------
    # render
    # -------------------------------------------------------------------------
    render_info_card(
        title=title,
        body_html=body_html,
        title_font_size=COMPACT_INFO_TITLE_FONT_SIZE,
        body_font_size=COMPACT_INFO_BODY_FONT_SIZE,
        body_line_height=COMPACT_INFO_BODY_LINE_HEIGHT,
        card_padding="4px 6px",
        title_margin_bottom=COMPACT_INFO_TITLE_MARGIN_BOTTOM,
        body_margin_top=COMPACT_INFO_BODY_MARGIN_TOP,
        body_margin_bottom=COMPACT_INFO_BODY_MARGIN_BOTTOM,
    )