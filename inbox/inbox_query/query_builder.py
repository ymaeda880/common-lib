# -*- coding: utf-8 -*-
# common_lib/inbox/inbox_query/query_builder.py


"""
Inbox 検索クエリ用 WHERE 句ビルダー

このモジュールは、Inbox（inbox_items）検索画面で指定された
各種フィルタ条件（種別・タグ・名前・格納日・サイズ・最終閲覧）
をもとに、

- WHERE 句の SQL 断片（"it.kind IN (...) AND ..."）
- 対応するプレースホルダ引数（params）

を生成するための補助関数群を提供する。

設計方針
--------
- SQL 文の組み立ては *exec 側* が責務を持つ
  （本モジュールは WHERE 句と params だけを返す）
- 条件が未指定の場合は「絞らない」
- UI 側での入力検証（警告表示など）を前提とし、
  ここでは *機械的に* SQL 条件へ変換する
- JST（UTC+9）を前提に日付条件を ISO 文字列へ変換する

前提となる SQL 構造
-------------------
query_exec 側では、以下のような FROM / JOIN を前提とする。

    FROM inbox_items AS it
    LEFT JOIN lvdb.last_viewed AS lv
           ON lv.item_id = it.item_id

- inbox_items は `it` エイリアス
- last_viewed は `lv` エイリアス
- 未閲覧判定は `lv.item_id IS NULL` で行う

主な利用関数
------------
build_where_and_params(...)

    where_sql, params = build_where_and_params(
        kinds_checked=[...],
        tag_terms=[...],
        name_terms=[...],
        added_from=date | None,
        added_to=date | None,
        size_mode="以上" | "以下" | "範囲",
        size_min_bytes=int | None,
        size_max_bytes=int | None,
        lv_mode="未閲覧のみ" | "期間指定" | "最近" | "",
        lv_from=date | None,
        lv_to=date | None,
        lv_since_iso=str | None,
    )

戻り値
------
where_sql : str
    WHERE 句の中身のみを返す（先頭の "WHERE" は含まない）

    例:
        "it.kind IN (?, ?) AND it.original_name LIKE ? AND lv.item_id IS NULL"

params : list[Any]
    where_sql 内の `?` に対応する値を、順序通りに並べた配列

    例:
        ["pdf", "image", "%report%"]

呼び出し側での典型的な使い方
----------------------------
    where_sql, params = build_where_and_params(...)

    sql = (
        "SELECT it.* "
        "FROM inbox_items AS it "
        "LEFT JOIN lvdb.last_viewed AS lv ON lv.item_id = it.item_id "
    )
    if where_sql:
        sql += " WHERE " + where_sql

    cur.execute(sql, params)

補助関数について
----------------
- norm_text(s)
    検索語の正規化（NFKC・空白正規化）

- split_terms_and(s)
    AND 検索用の語分解
    空白・カンマ・スラッシュ（/／）を区切りとして分割

- parse_recent(s)
    「3日」「12h」「30分」などの表記を timedelta に変換

- date_to_iso_start / date_to_iso_end_exclusive
    date → JST ISO 文字列（[start, end) 形式）

注意点
------
- タグ検索は tags_json に対する LIKE 検索（現行仕様）
- last_viewed 条件は *必ず LEFT JOIN が存在すること*
- 本モジュールは SQL を実行しない（純粋なクエリ構築専用）
"""


from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, date, timezone
from typing import Optional, Tuple, List, Any


# JST は search 側でも使う（pages側でもJSTを持つなら冗長でもOK）
JST = timezone(timedelta(hours=9))

_WS_RE = re.compile(r"[ \t\u3000]+")


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.strip()
    s = _WS_RE.sub(" ", s)
    return s


def split_terms_and(s: str) -> list[str]:
    """
    AND検索用の検索語分解
    - 空白 / カンマ に加えて、/（全角／も）を区切りとして扱う
    - 連続区切りは無視
    - 空要素は除去
    """
    import re

    if not s:
        return []

    # 区切りとして扱うもの：空白類、カンマ類、スラッシュ類
    # ※ 必要なら後から '-' を追加できるが、今回要件は '/' なので入れない
    parts = re.split(r"[,\s/／]+", s.strip())

    terms: list[str] = []
    for p in parts:
        t = (p or "").strip()
        if t:
            terms.append(t)

    return terms



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


def date_to_iso_start(d: date) -> str:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=JST).isoformat(timespec="seconds")


def date_to_iso_end_exclusive(d: date) -> str:
    dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=JST) + timedelta(days=1)
    return dt.isoformat(timespec="seconds")


def mb_to_bytes(x: float) -> int:
    try:
        return int(float(x) * 1024 * 1024)
    except Exception:
        return 0

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

    # --- 追加：last_viewed 条件 ---
    lv_mode: str,
    lv_from: Optional[date],
    lv_to: Optional[date],
    lv_since_iso: Optional[str],
) -> tuple[str, list[Any]]:

    conds: List[str] = []
    params: List[Any] = []

    # ----------------------------
    # 種別
    # ----------------------------
    if not kinds_checked:
        conds.append("1=0")
    else:
        ph = ",".join(["?"] * len(kinds_checked))
        conds.append(f"it.kind IN ({ph})")
        params.extend(kinds_checked)

    # ----------------------------
    # タグ（JSON文字列LIKE：現行仕様）
    # ----------------------------
    for t in tag_terms:
        conds.append("it.tags_json LIKE ?")
        params.append(f"%{t}%")

    # ----------------------------
    # ファイル名
    # ----------------------------
    for t in name_terms:
        conds.append("it.original_name LIKE ?")
        params.append(f"%{t}%")

    # ----------------------------
    # 格納日
    # ----------------------------
    if added_from:
        conds.append("it.added_at >= ?")
        params.append(date_to_iso_start(added_from))
    if added_to:
        conds.append("it.added_at < ?")
        params.append(date_to_iso_end_exclusive(added_to))

    # ----------------------------
    # サイズ
    # ----------------------------
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

    # ============================================================
    # last_viewed（SQLに押し込む）
    # 前提：
    #   query_exec 側で
    #     FROM inbox_items AS items
    #     LEFT JOIN lvdb.last_viewed AS lv ON ...
    #   のように lv エイリアスが存在すること
    # ============================================================
    if lv_mode == "未閲覧のみ":
        # lv が無いもの＝未閲覧
        conds.append("lv.item_id IS NULL")

    elif lv_mode == "期間指定":
        # 期間指定が実質「閲覧済み」だけを対象にしたいなら、まず存在条件
        conds.append("lv.item_id IS NOT NULL")

        if lv_from is not None:
            conds.append("lv.last_viewed_at >= ?")
            params.append(date_to_iso_start(lv_from))
        if lv_to is not None:
            conds.append("lv.last_viewed_at < ?")
            params.append(date_to_iso_end_exclusive(lv_to))

    elif lv_mode == "最近":
        # 「最近」は since が取れたときだけ絞る（取れないなら絞らない：UI側でwarning済み想定）
        if lv_since_iso:
            conds.append("lv.item_id IS NOT NULL")
            conds.append("lv.last_viewed_at >= ?")
            params.append(lv_since_iso)

    # ★重要：ここでは WHERE を付けない（呼び出し側/exec側で付ける）
    where_sql = " AND ".join(conds) if conds else ""
    return where_sql, params
