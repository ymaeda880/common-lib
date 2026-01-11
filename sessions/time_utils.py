# common_lib/sessions/time_utils.py
from __future__ import annotations

from datetime import datetime, timezone, timedelta

# JST固定（運用方針）
JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    """現在時刻（JST, aware datetime）"""
    return datetime.now(JST)


def floor_to_minute(dt: datetime) -> datetime:
    """
    分単位に切り下げ（YYYY-MM-DD HH:MM:00 JST）
    例：09:05:59 → 09:05:00
    """
    return dt.replace(second=0, microsecond=0)


def date_str_jst(dt: datetime) -> str:
    """JST日付（YYYY-MM-DD）"""
    return dt.astimezone(JST).strftime("%Y-%m-%d")


def dt_to_iso(dt: datetime) -> str:
    """DB格納用 ISO 文字列（timezone付き）"""
    return dt.astimezone(JST).isoformat(timespec="seconds")
