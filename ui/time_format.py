# common_lib/ui/time_format.py
# =============================================================================
# 日時フォーマット（UI表示専用 / 共通ライブラリ）
# - JST ISO文字列を UI 表示用に変換
# - 表示専用（DB保存・計算用途では使用しない）
# - 表示表記を全画面で統一する
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime


def format_jst_iso(ts: str | None) -> str:
    """
    表示専用（ISO → 簡易表示）：
      '2026-01-20T13:46:40+09:00'
        → '2026-01-20 13:46:40（JST）'
    """
    if not ts:
        return "—"
    s = ts.replace("T", " ")
    s = s.replace("+09:00", "（JST）")
    return s


def format_jst_iso_ja(ts: str | None) -> str:
    """
    表示専用（ISO → 日本語表記）：
      '2026-01-20T13:51:31+09:00'
        → '2026年1月20日　13時51分31秒'
    """
    if not ts:
        return "—"
    try:
        # +09:00 を含む ISO をそのまま parse
        dt = datetime.fromisoformat(ts)
        return (
            f"{dt.year}年{dt.month}月{dt.day}日　"
            f"{dt.hour:02d}時{dt.minute:02d}分{dt.second:02d}秒"
        )
    except Exception:
        # 失敗時は元文字列をそのまま（UI崩壊を防ぐ）
        return ts
