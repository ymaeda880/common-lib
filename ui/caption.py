# common_lib/ui/caption.py
# ============================================================
# caption UI
#
# 機能：
# - 小さい説明文を共通UIとして表示
# - st.caption より行間を詰める
# - captionデザインを共通化
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from html import escape

import streamlit as st


# ============================================================
# base caption renderer
# ============================================================
def _render_caption_base(
    lines: list[str],
    *,
    font_size: str,
    line_height: str,
    color: str,
    font_weight: str = "normal",
) -> None:
    html_lines = "<br>".join(
        escape(line)
        for line in lines
    )

    st.markdown(
        f"""
        <div style="
            font-size:{font_size};
            line-height:{line_height};
            color:{color};
            font-weight:{font_weight};
        ">
        {html_lines}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# compact caption
#
# 用途：
# - 通常の小さい説明
# - 検索ヒント
# - 補足説明
# ============================================================
def render_compact_caption(
    lines: list[str],
) -> None:
    _render_caption_base(
        lines,
        font_size="0.80rem",
        line_height="1.15",
        color="rgba(49, 51, 63, 0.78)",
    )


# ============================================================
# memo caption
#
# 用途：
# - 管理用覚書
# - 内部仕様
# - fallback条件
# - 開発者向け補足
# ============================================================
def render_memo_caption(
    lines: list[str],
) -> None:
    _render_caption_base(
        lines,
        font_size="0.72rem",
        line_height="1.05",
        color="rgba(90, 90, 90, 0.62)",
    )


# ============================================================
# info caption
#
# 用途：
# - 補足情報
# - 状態説明
# - 案内
# ============================================================
def render_info_caption(
    lines: list[str],
) -> None:
    _render_caption_base(
        lines,
        font_size="0.80rem",
        line_height="1.15",
        color="#1f77b4",
    )


# ============================================================
# success caption
#
# 用途：
# - 成功
# - 完了
# - 正常終了
# ============================================================
def render_success_caption(
    lines: list[str],
) -> None:
    _render_caption_base(
        lines,
        font_size="0.80rem",
        line_height="1.15",
        color="#2e8b57",
    )


# ============================================================
# warning caption
#
# 用途：
# - 注意事項
# - 制約説明
# - 未実行警告
# ============================================================
def render_warning_caption(
    lines: list[str],
) -> None:
    _render_caption_base(
        lines,
        font_size="0.80rem",
        line_height="1.15",
        color="#d97706",
        font_weight="500",
    )


# ============================================================
# error caption
#
# 用途：
# - エラー
# - 不足
# - 失敗
# ============================================================
def render_error_caption(
    lines: list[str],
) -> None:
    _render_caption_base(
        lines,
        font_size="0.80rem",
        line_height="1.15",
        color="#dc2626",
        font_weight="500",
    )