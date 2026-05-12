# -*- coding: utf-8 -*-
# common_lib/inbox/inbox_query/query_builder.py

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, date, timezone
from typing import Optional, List, Any


# ============================================================
# 定数
# ============================================================
JST = timezone(timedelta(hours=9))
_WS_RE = re.compile(r"[ \t\u3000]+")


# ============================================================
# テキスト正規化
# ============================================================
def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = unicodedata.normalize("NFC", s)
    s = s.strip()
    s = _WS_RE.sub(" ", s)
    return s


# ============================================================
# AND検索語分解
# ============================================================
def split_terms_and(s: str) -> list[str]:
    """
    AND検索用の検索語分解。
    空白 / カンマ / スラッシュで分割する。
    """

    if not s:
        return []

    s = norm_text(s)
    parts = re.split(r"[,\s/／]+", s)

    terms: list[str] = []
    for p in parts:
        t = norm_text(p)
        if t:
            terms.append(t)

    return terms


# ============================================================
# 最近条件の解釈
# ============================================================
def parse_recent(s: str) -> Optional[timedelta]:
    s = norm_text(s)
    if not s:
        return None

    m = re.fullmatch(r"(\d+)\s*(日|d|時間|h|分|m)", s, flags=re.IGNORECASE)
    if not m:
        return None

    n = int(m.group(1))
    unit = m.group(2).lower()

    if unit in ("日", "d"):
        return timedelta(days=n)
    if unit in ("時間", "h"):
        return timedelta(hours=n)
    if unit in ("分", "m"):
        return timedelta(minutes=n)

    return None


# ============================================================
# 日付 → ISO
# ============================================================
def date_to_iso_start(d: date) -> str:
    return datetime(
        d.year,
        d.month,
        d.day,
        0,
        0,
        0,
        tzinfo=JST,
    ).isoformat(timespec="seconds")


def date_to_iso_end_exclusive(d: date) -> str:
    dt = datetime(
        d.year,
        d.month,
        d.day,
        0,
        0,
        0,
        tzinfo=JST,
    ) + timedelta(days=1)

    return dt.isoformat(timespec="seconds")


# ============================================================
# MB → bytes
# ============================================================
def mb_to_bytes(x: float) -> int:
    try:
        return int(float(x) * 1024 * 1024)
    except Exception:
        return 0


# ============================================================
# WHERE句生成
# ============================================================
def build_where_and_params(
    *,
    kinds_checked: list[str],
    tag_terms: list[str],
    name_terms: list[str],
    added_from: Optional[date],
    added_to: Optional[date],
    size_mode: str,
    size_min_bytes: Optional[int],
    size_max_bytes: Optional[int],
    lv_mode: str,
    lv_from: Optional[date],
    lv_to: Optional[date],
    lv_since_iso: Optional[str],
) -> tuple[str, list[Any]]:

    conds: List[str] = []
    params: List[Any] = []

    # ------------------------------------------------------------
    # 種別
    # ------------------------------------------------------------
    if not kinds_checked:
        conds.append("1=0")
    else:
        ph = ",".join(["?"] * len(kinds_checked))
        conds.append(f"it.kind IN ({ph})")
        params.extend(kinds_checked)

    # ------------------------------------------------------------
    # タグ
    # ------------------------------------------------------------
    for t in tag_terms:
        t = norm_text(t)
        if not t:
            continue

        conds.append("it.tags_json LIKE ?")
        params.append(f"%{t}%")

    # ------------------------------------------------------------
    # ファイル名
    # ------------------------------------------------------------
    for t in name_terms:
        t = norm_text(t)
        if not t:
            continue

        conds.append("it.original_name LIKE ?")
        params.append(f"%{t}%")

    # ------------------------------------------------------------
    # 格納日
    # ------------------------------------------------------------
    if added_from:
        conds.append("it.added_at >= ?")
        params.append(date_to_iso_start(added_from))

    if added_to:
        conds.append("it.added_at < ?")
        params.append(date_to_iso_end_exclusive(added_to))

    # ------------------------------------------------------------
    # サイズ
    # ------------------------------------------------------------
    if size_mode == "以上" and size_min_bytes is not None:
        conds.append("it.size_bytes >= ?")
        params.append(int(size_min_bytes))

    elif size_mode == "以下" and size_max_bytes is not None:
        conds.append("it.size_bytes <= ?")
        params.append(int(size_max_bytes))

    elif size_mode == "範囲":
        if size_min_bytes is not None:
            conds.append("it.size_bytes >= ?")
            params.append(int(size_min_bytes))

        if size_max_bytes is not None:
            conds.append("it.size_bytes <= ?")
            params.append(int(size_max_bytes))

    # ------------------------------------------------------------
    # 最終閲覧
    # ------------------------------------------------------------
    if lv_mode == "未閲覧のみ":
        conds.append("lv.item_id IS NULL")

    elif lv_mode == "期間指定":
        conds.append("lv.item_id IS NOT NULL")

        if lv_from is not None:
            conds.append("lv.last_viewed_at >= ?")
            params.append(date_to_iso_start(lv_from))

        if lv_to is not None:
            conds.append("lv.last_viewed_at < ?")
            params.append(date_to_iso_end_exclusive(lv_to))

    elif lv_mode == "最近":
        if lv_since_iso:
            conds.append("lv.item_id IS NOT NULL")
            conds.append("lv.last_viewed_at >= ?")
            params.append(lv_since_iso)

    where_sql = " AND ".join(conds) if conds else ""
    return where_sql, params