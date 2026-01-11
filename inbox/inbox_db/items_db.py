# -*- coding: utf-8 -*-
# common_lib/inbox_db/items_db.py


"""
inbox_items 正本DB 管理モジュール

Inbox に格納される全アイテム（PDF / 画像 / Word / Excel / Text 等）の
メタデータを管理するための正本データベース
`inbox_items.db` を扱う唯一の共通ライブラリ。

本モジュールは以下を強く保証する：

- inbox_items.db のスキーマ定義・進化（migration）の正本はここ
- ページ側（20 / 21 / 22 / 35 ...）に DDL を散らさない
- すべての CRUD は ensure_items_db を経由する
- 古い DB が存在しても「壊さず」「追加列で吸収」する

設計方針（確定）
----------------
- inbox_items.db は「正本DB」
- スキーマ変更は ALTER TABLE ADD COLUMN による後方互換方式
- 既存列の削除・型変更は行わない
- migration ロジックは ensure_items_db に集約する

これにより、
- 古い端末・古い DB を持つユーザーでも即座に動作する
- DB 初期化漏れによる page 側エラーを防ぐ
- schema の所在が常に一箇所に固定される

DB スキーマ概要
---------------
テーブル：
    inbox_items

主キー：
    item_id TEXT PRIMARY KEY

主要列：
    kind            TEXT    # 種別（pdf / image / word / excel / text ...）
    stored_rel      TEXT    # ストレージ内の相対パス
    original_name   TEXT    # 元ファイル名
    added_at        TEXT    # 格納日時（ISO文字列）
    size_bytes      INTEGER # ファイルサイズ
    note            TEXT    # ユーザー用メモ
    tags_json       TEXT    # タグ（JSON配列文字列）
    thumb_rel       TEXT    # サムネイル相対パス
    thumb_status    TEXT    # none / done / error
    thumb_error     TEXT    # エラー内容（短縮）

送付・コピー由来情報：
    origin_user     TEXT    # 元のユーザー sub
    origin_item_id  TEXT    # 元 item_id
    origin_type     TEXT    # 送付種別

スキーマ保証関数
----------------
ensure_items_db(items_db)

    - DB / ディレクトリが無ければ作成
    - テーブルが無ければ作成
    - 既存 DB に不足列があれば ALTER TABLE ADD COLUMN
    - index を最低限保証

    ※ inbox_items.db を触るすべての関数が内部で必ず呼ぶ。

insert / read / update / delete API
-----------------------------------
insert_item(...)
    inbox_items への INSERT 正本。
    - 通常アップロード：origin_* は空文字
    - 送付コピー：origin_* を明示的に指定

fetch_item_by_id(...)
    item_id で 1 件取得（dict 形式）

load_items_df(...)
    全件を DataFrame で取得（added_at DESC）

count_items(...)
    WHERE 条件付き件数取得
    - where_sql は "WHERE ..." を含む前提

load_items_page(...)
    ページング取得（LIMIT / OFFSET）
    - where_sql / order_sql を外部から注入

update_item_tag_single(...)
    単一タグ運用用の簡易更新
    - tags_json は常に JSON 配列文字列で保存

update_item_note(...)
    note 列の更新

update_thumb(...)
    サムネイル生成結果の反映
    - error は最大 500 文字に切り詰める

delete_item_row(...)
    inbox_items から 1 行削除
    ※ 実ファイル削除は別レイヤの責務

責務分離の考え方
----------------
- 本モジュール：DB の正当性・一貫性
- query_builder / query_exec：検索条件・JOIN・表示用整形
- pages：UI / ユーザー操作
- 実ファイル操作（削除・コピー）：storage / ops 側

注意事項
--------
- tags_json は JSON 配列文字列として扱う（LIKE 検索前提）
- 日時はすべて ISO 文字列で保持（timezone 解釈は上位層）
- 本モジュールは UI や権限制御を一切持たない
"""



from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

"""
========================================
📌 覚書（2025-12-31 / 康男さん + ChatGPT）
========================================
- inbox_items.db の schema/migration 正本はこのファイル（ensure_items_db）。
- 20/21/22…はページ側にDDLを散らさず、必ず ensure_items_db を呼ぶ。
- 追加の列が必要になったら「ここに ALTER TABLE ADD COLUMN を追記」する。
========================================
"""


# ------------------------------------------------------------
# schema utilities
# ------------------------------------------------------------
def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    # (cid, name, type, notnull, dflt_value, pk)
    return {r[1] for r in rows}


def ensure_items_db(items_db: Path) -> None:
    """
    inbox_items.db を“壊れないように”初期化/補修する（正本）。
    - 既存DBが古くても必要列を追加して整合させる
    - ALTER TABLE ADD COLUMN による後方互換マイグレーション方式
    """
    items_db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(items_db) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS inbox_items (
              item_id       TEXT PRIMARY KEY,
              kind          TEXT NOT NULL,
              stored_rel    TEXT NOT NULL,
              original_name TEXT NOT NULL,
              added_at      TEXT NOT NULL,
              size_bytes    INTEGER NOT NULL,
              note          TEXT DEFAULT '',
              tags_json     TEXT DEFAULT '[]',
              thumb_rel     TEXT DEFAULT '',
              thumb_status  TEXT DEFAULT 'none',
              thumb_error   TEXT DEFAULT '',
              origin_user     TEXT DEFAULT '',
              origin_item_id  TEXT DEFAULT '',
              origin_type     TEXT DEFAULT ''
            )
            """
        )

        cols = _table_columns(con, "inbox_items")

        # --- 過去DB向けの列補修 ---
        def _add(col: str, ddl: str) -> None:
            if col not in cols:
                con.execute(ddl)

        _add("note", "ALTER TABLE inbox_items ADD COLUMN note TEXT DEFAULT ''")
        _add("tags_json", "ALTER TABLE inbox_items ADD COLUMN tags_json TEXT DEFAULT '[]'")
        _add("thumb_rel", "ALTER TABLE inbox_items ADD COLUMN thumb_rel TEXT DEFAULT ''")
        _add("thumb_status", "ALTER TABLE inbox_items ADD COLUMN thumb_status TEXT DEFAULT 'none'")
        _add("thumb_error", "ALTER TABLE inbox_items ADD COLUMN thumb_error TEXT DEFAULT ''")

        # --- 送付（コピー）由来 ---
        _add("origin_user", "ALTER TABLE inbox_items ADD COLUMN origin_user TEXT DEFAULT ''")
        _add("origin_item_id", "ALTER TABLE inbox_items ADD COLUMN origin_item_id TEXT DEFAULT ''")
        _add("origin_type", "ALTER TABLE inbox_items ADD COLUMN origin_type TEXT DEFAULT ''")

        # --- index（最小） ---
        con.execute("CREATE INDEX IF NOT EXISTS idx_inbox_kind  ON inbox_items(kind)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_inbox_added ON inbox_items(added_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_inbox_name  ON inbox_items(original_name)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_inbox_thumb ON inbox_items(thumb_status)")

        con.commit()


# ------------------------------------------------------------
# insert helper（正本）
# ------------------------------------------------------------
def insert_item(items_db: Path, item: Dict[str, Any]) -> None:
    """
    inbox_items への insert 正本。
    - 通常アップロード：origin_* は空文字
    - 送付コピー：origin_* を明示的に渡す
    """
    ensure_items_db(items_db)

    with sqlite3.connect(items_db) as con:
        con.execute(
            """
            INSERT INTO inbox_items(
              item_id, kind, stored_rel, original_name, added_at, size_bytes,
              note, tags_json,
              thumb_rel, thumb_status, thumb_error,
              origin_user, origin_item_id, origin_type
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(item["item_id"]),
                str(item["kind"]),
                str(item["stored_rel"]),
                str(item["original_name"]),
                str(item["added_at"]),
                int(item.get("size_bytes", 0) or 0),
                str(item.get("note", "") or ""),
                str(item.get("tags_json", "[]") or "[]"),
                str(item.get("thumb_rel", "") or ""),
                str(item.get("thumb_status", "none") or "none"),
                str(item.get("thumb_error", "") or ""),
                str(item.get("origin_user", "") or ""),
                str(item.get("origin_item_id", "") or ""),
                str(item.get("origin_type", "") or ""),
            ),
        )
        con.commit()


# ------------------------------------------------------------
# read helpers
# ------------------------------------------------------------
def fetch_item_by_id(items_db: Path, item_id: str) -> Optional[Dict[str, Any]]:
    ensure_items_db(items_db)
    with sqlite3.connect(items_db) as con:
        row = con.execute(
            """
            SELECT
              item_id, kind, stored_rel, original_name, added_at, size_bytes,
              note, tags_json,
              thumb_rel, thumb_status, thumb_error,
              origin_user, origin_item_id, origin_type
            FROM inbox_items
            WHERE item_id = ?
            """,
            (str(item_id),),
        ).fetchone()

    if not row:
        return None

    return {
        "item_id": row[0],
        "kind": row[1],
        "stored_rel": row[2],
        "original_name": row[3],
        "added_at": row[4],
        "size_bytes": int(row[5] or 0),
        "note": row[6] or "",
        "tags_json": row[7] or "[]",
        "thumb_rel": row[8] or "",
        "thumb_status": row[9] or "none",
        "thumb_error": row[10] or "",
        "origin_user": row[11] or "",
        "origin_item_id": row[12] or "",
        "origin_type": row[13] or "",
    }


def load_items_df(items_db: Path) -> pd.DataFrame:
    ensure_items_db(items_db)
    with sqlite3.connect(items_db) as con:
        return pd.read_sql_query(
            """
            SELECT
              item_id, kind, stored_rel, original_name, added_at, size_bytes,
              note, tags_json,
              thumb_rel, thumb_status, thumb_error,
              origin_user, origin_item_id, origin_type
            FROM inbox_items
            ORDER BY added_at DESC
            """,
            con,
        )


def count_items(
    items_db: Path,
    where_sql: str = "",
    params: Optional[List[Any]] = None,
) -> int:
    ensure_items_db(items_db)
    params = params or []
    with sqlite3.connect(items_db) as con:
        row = con.execute(
            f"SELECT COUNT(*) FROM inbox_items items {where_sql}",
            tuple(params),
        ).fetchone()
    return int(row[0] or 0)


def load_items_page(
    items_db: Path,
    *,
    where_sql: str,
    params: List[Any],
    limit: int,
    offset: int,
    order_sql: str = "ORDER BY items.added_at DESC",
) -> pd.DataFrame:
    ensure_items_db(items_db)
    with sqlite3.connect(items_db) as con:
        return pd.read_sql_query(
            f"""
            SELECT
              items.item_id,
              items.kind,
              items.stored_rel,
              items.original_name,
              items.added_at,
              items.size_bytes,
              items.note,
              items.tags_json,
              items.thumb_rel,
              items.thumb_status,
              items.thumb_error,
              items.origin_user,
              items.origin_item_id,
              items.origin_type
            FROM inbox_items items
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            con,
            params=tuple(list(params) + [int(limit), int(offset)]),
        )


# ------------------------------------------------------------
# update helpers
# ------------------------------------------------------------
def update_item_tag_single(items_db: Path, item_id: str, new_tag: str) -> None:
    ensure_items_db(items_db)
    tag = (new_tag or "").strip()
    tags_json = json.dumps([tag] if tag else [], ensure_ascii=False)

    with sqlite3.connect(items_db) as con:
        con.execute(
            "UPDATE inbox_items SET tags_json = ? WHERE item_id = ?",
            (tags_json, str(item_id)),
        )
        con.commit()


def update_item_note(items_db: Path, item_id: str, note: str) -> None:
    ensure_items_db(items_db)
    with sqlite3.connect(items_db) as con:
        con.execute(
            "UPDATE inbox_items SET note = ? WHERE item_id = ?",
            ((note or ""), str(item_id)),
        )
        con.commit()


def update_thumb(items_db: Path, item_id: str, thumb_rel: str, status: str, error: str = "") -> None:
    ensure_items_db(items_db)
    with sqlite3.connect(items_db) as con:
        con.execute(
            """
            UPDATE inbox_items
            SET thumb_rel = ?, thumb_status = ?, thumb_error = ?
            WHERE item_id = ?
            """,
            (thumb_rel or "", status or "none", (error or "")[:500], str(item_id)),
        )
        con.commit()


def delete_item_row(items_db: Path, item_id: str) -> None:
    ensure_items_db(items_db)
    with sqlite3.connect(items_db) as con:
        con.execute("DELETE FROM inbox_items WHERE item_id = ?", (str(item_id),))
        con.commit()
