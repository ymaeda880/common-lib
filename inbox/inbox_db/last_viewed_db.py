# -*- coding: utf-8 -*-
# common_lib/inbox/inbox_db/last_viewed_db.py
#
# ✅ last_viewed 正本DB（_meta/last_viewed.db）
#
# 【確定仕様】
# - last_viewed.db は正本のみ（旧DB互換・列名推定はしない）
# - テーブル: last_viewed
# - 主キー: (user_sub, item_id)
# - 閲覧日時列: last_viewed_at（ISO文字列, JST）
#
# 【提供API】
# - ensure_last_viewed_db(lv_db): スキーマ保証（正本仕様のみ）
# - upsert_last_viewed(...): (user_sub, item_id) で last_viewed_at を upsert


"""
last_viewed 正本DB 管理モジュール

Inbox における「最終閲覧日時」を管理するための
正本データベース（_meta/last_viewed.db）専用モジュール。

本モジュールは、last_viewed.db を

- 単一の正本
- 明確に固定されたスキーマ
- 互換・推測・救済を一切行わない

という方針で管理する。

設計方針（確定事項）
--------------------
- last_viewed.db は「正本DB」のみ
- 旧DB互換・列名推定・自動 migration は行わない
- スキーマがズレていれば例外として顕在化させる
- last_viewed の定義・保証責務は common_lib に一本化する

これにより、
- ページ側やクエリ側で「列名が何か」を考えなくてよい
- ATTACH / JOIN 時の不整合を早期に検出できる
- 暗黙の仕様変化を防ぐ

スキーマ仕様（固定）
--------------------
DB ファイル：
    _meta/last_viewed.db

テーブル：
    last_viewed

列：
    user_sub        TEXT NOT NULL   # ユーザー識別子（JWT sub）
    item_id         TEXT NOT NULL   # inbox_items.item_id
    kind            TEXT NOT NULL   # アイテム種別（検索・集計用）
    last_viewed_at  TEXT NOT NULL   # ISO文字列（JST）

主キー：
    (user_sub, item_id)

索引：
    idx_last_viewed_user_kind
        (user_sub, kind)

    idx_last_viewed_last_viewed_at
        (last_viewed_at)

提供 API
--------
ensure_last_viewed_db(lv_db)

    last_viewed.db を「確定仕様」で作成・検証する。

    - DB が存在しない場合：作成
    - テーブルや索引が無い場合：作成
    - 必須列が欠けている場合：RuntimeError

    ※ 旧仕様吸収や列名変換は行わない。

upsert_last_viewed(...)

    指定された (user_sub, item_id) に対して
    last_viewed_at を upsert する。

    - プレビュー表示が「成立した」タイミングで呼ぶ想定
    - INSERT / UPDATE の両対応
    - NOT NULL 制約を破る値は即座に例外

利用想定フロー
--------------
1. 検索・一覧表示
    - query_exec 側で ensure_last_viewed_db(lv_db) を呼び出し
    - LEFT JOIN により last_viewed を参照

2. プレビュー表示
    - ファイル表示が成功した時点で
      upsert_last_viewed(...) を呼ぶ
    - 「見ようとした」ではなく「見えた」を記録する

注意事項
--------
- last_viewed_at は必ず非空の ISO 文字列を渡す
- None や空文字は ValueError で即時失敗させる
- DB パスはファイル単位で渡す（ディレクトリではない）
- 本モジュールは UI / 検索条件ロジックを持たない
"""



from __future__ import annotations

import sqlite3
from pathlib import Path


def ensure_last_viewed_db(lv_db: str | Path) -> None:
    """
    last_viewed.db を「確定仕様」で作成・保証する。

    重要：
    - 旧DB互換は捨てる（列名推定・移行・救済をしない）
    - 既存DBが仕様とズレている場合は、静かに吸収せずエラーで顕在化させる
    """
    lv_db = Path(lv_db)
    lv_db.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(lv_db))
    try:
        cur = con.cursor()

        # ✅ 正本スキーマ（確定）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS last_viewed (
                user_sub       TEXT NOT NULL,
                item_id        TEXT NOT NULL,
                kind           TEXT NOT NULL,
                last_viewed_at TEXT NOT NULL,
                PRIMARY KEY (user_sub, item_id)
            )
            """
        )

        # ✅ 索引（閲覧順・集計のため）
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_last_viewed_user_kind ON last_viewed(user_sub, kind)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_last_viewed_last_viewed_at ON last_viewed(last_viewed_at)"
        )

        con.commit()

        # ✅ 仕様チェック（ズレはエラーで顕在化）
        cur.execute("PRAGMA table_info(last_viewed)")
        cols = {str(r[1]) for r in cur.fetchall()}
        required = {"user_sub", "item_id", "kind", "last_viewed_at"}
        missing = required - cols
        if missing:
            raise RuntimeError(
                f"last_viewed.db schema mismatch: missing columns: {sorted(missing)}"
            )

    finally:
        con.close()


def upsert_last_viewed(
    *,
    lv_db: str | Path,
    user_sub: str,
    item_id: str,
    kind: str,
    viewed_at_iso: str,
) -> None:
    """
    last_viewed を upsert する（プレビュー表示が成立した時点で呼ぶ想定）。

    重要：
    - last_viewed_at は NOT NULL（空文字や None を入れない）
    - (user_sub, item_id) で upsert
    """
    if viewed_at_iso is None or str(viewed_at_iso).strip() == "":
        # ここで落として原因をはっきりさせる（NOT NULL を踏みに行かない）
        raise ValueError("viewed_at_iso is empty. last_viewed_at must be a non-empty ISO string.")

    ensure_last_viewed_db(lv_db)

    con = sqlite3.connect(str(Path(lv_db)))
    try:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO last_viewed (user_sub, item_id, kind, last_viewed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_sub, item_id)
            DO UPDATE SET
              kind = excluded.kind,
              last_viewed_at = excluded.last_viewed_at
            """,
            (str(user_sub), str(item_id), str(kind), str(viewed_at_iso)),
        )
        con.commit()
    finally:
        con.close()
