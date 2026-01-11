# ============================================================
# 1) common_lib/inbox/inbox_query/query_exec.py
#    「必要部分だけ」差し替え
#
# 置換範囲：
# - import 部分（ensure_last_viewed_db の import 追加）
# - query_items_page(...) 関数を丸ごと置換
# ============================================================


"""
Inbox 検索クエリ実行（ページング対応）

このモジュールは、Inbox 検索において

- inbox_items.db（正本）
- last_viewed.db（正本）

を組み合わせて検索・並び替え・ページングを行い、
UI がそのまま利用できる pandas.DataFrame を返す責務を持つ。

設計上の位置づけ
----------------
- WHERE 句の構築：query_builder 側の責務
- SQL の実行・JOIN・ORDER・LIMIT/OFFSET：本モジュールの責務
- UI 表示用の派生列生成（*_disp など）：本モジュールで実施

重要な前提・方針（確定事項）
----------------------------
- last_viewed.db は「正本 DB」
- last_viewed テーブルの日時列は last_viewed_at で固定
- 旧スキーマ互換（列名推定・migration 吸収）は一切行わない
- スキーマ保証は common_lib.inbox.inbox_db.last_viewed_db.ensure_last_viewed_db
  に一本化する

このため、本モジュールでは：
- クエリ実行前に必ず ensure_last_viewed_db(lv_db) を呼び出す
- ATTACH/JOIN 時に例外が出ないことを前提に処理を進める

前提となる DB / SQL 構造
------------------------
- items_db : inbox_items.db
    テーブル：inbox_items

- lv_db : last_viewed.db
    テーブル：last_viewed
    主な列：
        - user_sub
        - item_id
        - last_viewed_at

JOIN 形態：
    LEFT JOIN lvdb.last_viewed AS lv
      ON lv.user_sub = ?
     AND lv.item_id  = it.item_id

未閲覧アイテムは lv.last_viewed_at が NULL になる。

query_items_page(...) の役割
-----------------------------
- 検索条件（where_sql / params）を受け取る
- 総件数（total）を COUNT で取得
- 並び替え（sort_mode）を適用
- LIMIT / OFFSET によるページング
- last_viewed 情報を含めた DataFrame を返す

COUNT クエリの注意点
--------------------
件数（total）は inbox_items 側のみで決定する。

- COUNT クエリでは last_viewed を JOIN しない
- JOIN を入れると、last_viewed 側の不整合で COUNT まで失敗するため
- 検索条件（where_sql）は items 基準でそのまま適用する

sort_mode 仕様
--------------
sort_mode は以下をサポートする（大小文字・空白は正規化される）：

- "newest"（デフォルト）
    it.added_at DESC

- "viewed"
    1) 未閲覧（NULL）を最後
    2) last_viewed_at が新しい順
    3) 同順位は added_at DESC で安定化

- "name"
    it.original_name ASC, it.added_at DESC

その他の値は "newest" として扱う。

返り値
------
(df, total)

df : pandas.DataFrame
    UI が直接利用する前提の列を含む。

    主な列：
        - item_id
        - kind
        - tags_json
        - tag_disp            # tags_json 先頭要素（簡易表示用）
        - original_name
        - stored_rel
        - added_at
        - added_at_disp       # JST 表示文字列
        - size_bytes
        - size                # human readable
        - thumb_rel
        - thumb_status
        - last_viewed
        - last_viewed_disp    # JST 表示文字列

total : int
    WHERE 条件を満たす総件数（ページング前）

呼び出し側での典型例
--------------------
    where_sql, params = build_where_and_params(...)

    df, total = query_items_page(
        sub=user_sub,
        items_db=items_db_path,
        lv_db=last_viewed_db_path,
        where_sql=where_sql,
        params=params,
        limit=20,
        offset=0,
        sort_mode="viewed",
    )

注意事項
--------
- where_sql は "WHERE" を含まない前提
- params は where_sql 内の ? に対応する順序で渡す
- last_viewed.db は ATTACH されるため、ファイルパスは必ず存在可能であること
- 本モジュールは UI ロジックを持たない（表示判断は pages 側）
"""



from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any
from typing import Optional, Sequence


import pandas as pd

from common_lib.inbox.inbox_common.utils import bytes_human

# ✅ last_viewed.db の正本スキーマを保証（旧互換・列名推定なし）
# 配置：common_lib/inbox/inbox_db/last_viewed_db.py
from common_lib.inbox.inbox_db.last_viewed_db import ensure_last_viewed_db  # ←ここが正

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
    sort_mode: str = "newest",  # newest | viewed | name
) -> tuple[pd.DataFrame, int]:

    """
    items_db（inbox_items.db）を主として、
    lv_db（last_viewed.db）を ATTACH して LEFT JOIN し、last_viewed を取得する。

    ✅ 方針（確定）：
    - last_viewed.db は「正本DB」
    - last_viewed テーブルの日時列は last_viewed_at で固定
    - 旧DB互換（列名推定 / migration吸収）はしない
      → スキーマ保証は common_lib の ensure_last_viewed_db に一本化する
    """

    # WHERE句の先頭整形（空ならWHERE無し）
    where_clause = ""
    if where_sql and where_sql.strip():
        where_clause = f"WHERE {where_sql}"

    # sort_mode 正規化
    sm = (sort_mode or "newest").strip().lower()
    if sm not in ("newest", "viewed", "name"):
        sm = "newest"

    # ✅ クエリ側で lv_db のスキーマを保証してから参照する
    # （lv_db が無い/途中で壊れていると ATTACH/JOIN で落ちるため）
    ensure_last_viewed_db(lv_db)

    with sqlite3.connect(items_db) as con:
        con.row_factory = sqlite3.Row

        # lv_db を別DBとしてアタッチ（viewed 以外でも last_viewed 表示用に JOIN する）
        # ※ JOIN 自体は常にしてOK（NULLが返るだけ）
        con.execute("ATTACH DATABASE ? AS lvdb", (str(lv_db),))

        # ① total（COUNT）
        # 件数は inbox_items 側だけで決まるので、last_viewed との JOIN は不要。
        # JOIN を入れると last_viewed 側の不整合で COUNT まで落ちるため、ここでは参照しない。
        sql_count = f"""
        SELECT COUNT(*) AS cnt
        FROM (
        SELECT
            item_id,
            kind,
            tags_json,
            original_name,
            stored_rel,
            added_at,
            size_bytes,
            thumb_rel,
            thumb_status,
            COALESCE(tags_json, '') AS tag_disp
        FROM inbox_items
        ) AS it
        {where_clause}
        """

        row = con.execute(sql_count, list(params)).fetchone()
        total = int(row["cnt"] if row and row["cnt"] is not None else 0)

        # ② ORDER BY
        if sm == "name":
            order_sql = "ORDER BY it.original_name ASC, it.added_at DESC"
        elif sm == "viewed":
            # NULL（未閲覧）を最後、閲覧が新しい順、同点は added_at で安定化
            order_sql = (
                "ORDER BY (lv.last_viewed_at IS NULL) ASC, "
                "lv.last_viewed_at DESC, "
                "it.added_at DESC"
            )
        else:
            order_sql = "ORDER BY it.added_at DESC"

        # ③ page
        sql_page = f"""
        SELECT
        it.item_id,
        it.kind,
        it.tags_json,
        it.tag_disp,
        it.original_name,
        it.stored_rel,
        it.added_at,
        it.size_bytes,
        it.thumb_rel,
        it.thumb_status,
        lv.last_viewed_at AS last_viewed
        FROM (
        SELECT
            item_id,
            kind,
            tags_json,
            original_name,
            stored_rel,
            added_at,
            size_bytes,
            thumb_rel,
            thumb_status,
            COALESCE(tags_json, '') AS tag_disp
        FROM inbox_items
        ) AS it
        LEFT JOIN lvdb.last_viewed AS lv
        ON lv.user_sub = ?
        AND lv.item_id  = it.item_id
        {where_clause}
        {order_sql}
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
        df["last_viewed_disp"] = df["last_viewed"].apply(lambda x: format_dt_jp(x) if x else "") if "last_viewed" in df.columns else ""
        df["size"] = df["size_bytes"].apply(lambda n: bytes_human(int(n or 0))) if "size_bytes" in df.columns else ""

        # アタッチ解除（念のため）
        con.execute("DETACH DATABASE lvdb")

    return df, total


def query_items_page_minimal(
    *,
    items_db: str,
    where_sql: str = "",
    params: Optional[list[Any]] = None,
    limit: int = 20,
    offset: int = 0,
    kinds: Optional[Sequence[str]] = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    ============================================================
    Inbox picker 用：最小クエリ（UIなし / pandasなし / last_viewedなし）
    ============================================================

    目的：
    - Inbox（inbox_items.db）から「一覧表示・選択」に必要な最小情報だけ取る
    - 画像/PDF/text/zip 等 “全ファイル” を対象にできる（kinds で絞り込みも可）
    - last_viewed.db は一切触らない（ensure / ATTACH / JOIN もしない）

    戻り値：
    - rows: [{item_id, kind, original_name, stored_rel, added_at}, ...]
    - total: 条件を満たす総件数（ページング用）

    重要：
    - where_sql は "WHERE" を含まない前提（空なら条件なし）
    - params は where_sql 内の ? に対応する順序
    - UI 用の派生列（*_disp 等）は作らない（呼び出し側責務）
    """

    # ============================================================
    # 0) 引数正規化
    # ============================================================
    if params is None:
        params = []

    where_clause = ""
    if where_sql and where_sql.strip():
        where_clause = f"WHERE {where_sql}"

    # kinds の IN (...) を where_sql に “追加で合成” する
    # - 呼び出し側が where_sql を渡していても併用できるようにする
    kinds_clause = ""
    kinds_params: list[Any] = []
    if kinds and len(kinds) > 0:
        ph = ",".join(["?"] * len(kinds))
        kinds_clause = f"kind IN ({ph})"
        kinds_params = list(kinds)

    # where_sql と kinds_clause を AND で合成
    # - where_sql が空なら kinds_clause だけ
    # - kinds_clause が空なら where_sql だけ
    merged_where = ""
    merged_params: list[Any] = []
    if where_clause and kinds_clause:
        # where_clause は "WHERE ..." なので中身だけ取り出して合成する
        merged_where = f"WHERE ({where_sql}) AND ({kinds_clause})"
        merged_params = list(params) + kinds_params
    elif where_clause:
        merged_where = where_clause
        merged_params = list(params)
    elif kinds_clause:
        merged_where = f"WHERE {kinds_clause}"
        merged_params = kinds_params
    else:
        merged_where = ""
        merged_params = []

    # ============================================================
    # 1) SQLite 実行（items_db だけ）
    # ============================================================
    with sqlite3.connect(items_db) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # ============================================================
        # 2) total（COUNT）
        # - picker のページング計算のために必要
        # ============================================================
        sql_count = f"""
        SELECT COUNT(1) AS cnt
        FROM inbox_items
        {merged_where}
        """
        row = cur.execute(sql_count, merged_params).fetchone()
        total = int(row["cnt"] if row and row["cnt"] is not None else 0)

        # ============================================================
        # 3) rows（ページ取得）
        # - added_at DESC（新しい順）
        # ============================================================
        sql_page = f"""
        SELECT
            item_id,
            kind,
            original_name,
            stored_rel,
            added_at
        FROM inbox_items
        {merged_where}
        ORDER BY added_at DESC
        LIMIT ? OFFSET ?
        """
        page_params = list(merged_params) + [int(limit), int(offset)]
        out_rows: list[dict[str, Any]] = []
        for r in cur.execute(sql_page, page_params).fetchall():
            out_rows.append(
                {
                    "item_id": str(r["item_id"]),
                    "kind": str(r["kind"] or ""),
                    "original_name": str(r["original_name"] or ""),
                    "stored_rel": str(r["stored_rel"] or ""),
                    "added_at": str(r["added_at"] or ""),
                }
            )

    return out_rows, total

