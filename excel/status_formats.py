# -*- coding: utf-8 -*-
# common_lib/excel/status_formats.py
# ============================================================
# Excel ステータス表示 共通色・共通書式
#
# 機能：
# - Excelで使用する共通色を定義する
# - XlsxWriter の workbook から共通 Format を生成する
# - 各ページから色定数だけを利用することもできる
#
# 色：
# - green  ：正常・一致・OK
# - yellow ：注意・部分一致
# - red    ：エラー・不一致・NG
# - orange ：要確認・警告
# - blue   ：情報・参考
#
# 方針：
# - 各ページで色コードを直接定義しない
# - Excel出力時の色を全アプリで統一する
# ============================================================

from __future__ import annotations

from typing import Any


# ============================================================
# 共通色
# ============================================================

# ------------------------------------------------------------
# 緑
# ------------------------------------------------------------
STATUS_GREEN_BG = "#C6EFCE"
STATUS_GREEN_FONT = "#006100"

# ------------------------------------------------------------
# 黄色
# ------------------------------------------------------------
STATUS_YELLOW_BG = "#FFEB9C"
STATUS_YELLOW_FONT = "#9C6500"

# ------------------------------------------------------------
# 赤
# ------------------------------------------------------------
STATUS_RED_BG = "#FFC7CE"
STATUS_RED_FONT = "#9C0006"

# ------------------------------------------------------------
# 橙色
# ------------------------------------------------------------
STATUS_ORANGE_BG = "#FCE4D6"
STATUS_ORANGE_FONT = "#C65911"

# ------------------------------------------------------------
# 青
# ------------------------------------------------------------
STATUS_BLUE_BG = "#D9EAF7"
STATUS_BLUE_FONT = "#1F4E78"


# ============================================================
# 色情報
#
# 色名から背景色・文字色をまとめて取得したい場合に使用する
# ============================================================
STATUS_COLORS = {
    "green": {
        "bg_color": STATUS_GREEN_BG,
        "font_color": STATUS_GREEN_FONT,
    },
    "yellow": {
        "bg_color": STATUS_YELLOW_BG,
        "font_color": STATUS_YELLOW_FONT,
    },
    "red": {
        "bg_color": STATUS_RED_BG,
        "font_color": STATUS_RED_FONT,
    },
    "orange": {
        "bg_color": STATUS_ORANGE_BG,
        "font_color": STATUS_ORANGE_FONT,
    },
    "blue": {
        "bg_color": STATUS_BLUE_BG,
        "font_color": STATUS_BLUE_FONT,
    },
}


# ============================================================
# 共通ステータス書式を生成
# ============================================================
def create_status_formats(
    workbook: Any,
) -> dict[str, Any]:
    """
    XlsxWriter の workbook から，
    共通ステータス表示用の Format を生成する．

    Returns
    -------
    dict[str, Any]
        green / yellow / red / orange / blue の
        XlsxWriter Format を格納した辞書
    """

    # --------------------------------------------------------
    # 共通設定
    # --------------------------------------------------------
    common = {
        "bold": True,
        "align": "center",
        "valign": "vcenter",
    }

    # --------------------------------------------------------
    # 各色の Format を生成
    # --------------------------------------------------------
    return {
        color_name: workbook.add_format(
            {
                **common,
                **color_values,
            }
        )
        for color_name, color_values in STATUS_COLORS.items()
    }