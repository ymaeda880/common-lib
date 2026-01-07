# -*- coding: utf-8 -*-
# common_lib/inbox_ingest/query_exec.py
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from common_lib.inbox.inbox_common.utils import bytes_human

JST = timezone(timedelta(hours=9))


def format_dt_jp(dt_str: Any) -> str:
    if dt_str is None:
        return ""
    if isinstance(dt_str, float) and pd.isna(dt_str):
        return ""
    s = str(dt_str)
    try:
        dt = datetime.fromisoformat(s)
        return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return s


def query_items_page(
    *,
    sub: str,
    items_db: str,
    lv_db: str,
    where_sql: str,
    params: list[Any],
    limit: int,
    offset: int,
) -> tuple[pd.DataFrame, int]:
    """
    items_db（inbox_items.db）を主として、
    lv_db（last_viewed.db）を ATTACH して LEFT JOIN し、last_viewed を取得する。

    where_sql は build_where_and_params が返すもので、
    lv_mode をSQLに押し込んだ場合もここでそのまま効く（lvエイリアスを使う）。
    """

    # WHERE句の先頭整形（空ならWHERE無し）
    where_clause = ""
    if where_sql and where_sql.strip():
        where_clause = f"WHERE {where_sql}"

    with sqlite3.connect(items_db) as con:
        con.row_factory = sqlite3.Row

        # lv_db を別DBとしてアタッチ
        con.execute("ATTACH DATABASE ? AS lvdb", (str(lv_db),))

        # ① total（COUNT）
        sql_count = f"""
        SELECT COUNT(*) AS cnt
        FROM inbox_items AS it
        LEFT JOIN lvdb.last_viewed AS lv
          ON lv.user_sub = ?
         AND lv.item_id  = it.item_id
        {where_clause}
        """
        row = con.execute(sql_count, [sub] + list(params)).fetchone()
        total = int(row["cnt"] if row and row["cnt"] is not None else 0)

        # ② page
        sql_page = f"""
        SELECT
          it.item_id,
          it.kind,
          it.tags_json,
          it.original_name,
          it.stored_rel,
          it.added_at,
          it.size_bytes,
          it.thumb_rel,
          it.thumb_status,
          lv.viewed_at AS last_viewed
        FROM inbox_items AS it
        LEFT JOIN lvdb.last_viewed AS lv
          ON lv.user_sub = ?
         AND lv.item_id  = it.item_id
        {where_clause}
        ORDER BY it.added_at DESC
        LIMIT ? OFFSET ?
        """
        df = pd.read_sql_query(
            sql_page,
            con,
            params=[sub] + list(params) + [int(limit), int(offset)],
        )

        # ============================================================
        # 表示用の派生列（UIが前提としている列）
        # ============================================================
        def _tag_from_json_1st(s: Any) -> str:
            try:
                if s is None:
                    return ""
                import json as _json

                arr = _json.loads(str(s))
                if isinstance(arr, list) and arr:
                    v = arr[0]
                    return "" if v is None else str(v)
            except Exception:
                pass
            return ""

        df["tag_disp"] = df["tags_json"].apply(_tag_from_json_1st) if "tags_json" in df.columns else ""

        df["added_at_disp"] = df["added_at"].apply(lambda x: format_dt_jp(x) if x else "") if "added_at" in df.columns else ""
        df["last_viewed_disp"] = (
            df["last_viewed"].apply(lambda x: format_dt_jp(x) if x else "") if "last_viewed" in df.columns else ""
        )
        df["size"] = df["size_bytes"].apply(lambda n: bytes_human(int(n or 0))) if "size_bytes" in df.columns else ""

        # アタッチ解除（念のため）
        con.execute("DETACH DATABASE lvdb")

    return df, total
