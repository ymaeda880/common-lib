# -*- coding: utf-8 -*-
# common_lib/inbox_ingest/last_viewed_db.py
#
# ✅ last_viewed 正本DB（_meta/last_viewed.db）
# - 既存DBのスキーマ差（列名違い）を吸収する
# - pages/30 から呼ばれる最小APIだけ提供

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {str(r[1]) for r in cur.fetchall()}  # r[1] = column name
    return cols


def _first_existing(cols: set[str], candidates: Iterable[str]) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None


def ensure_last_viewed_db(lv_db: Path) -> None:
    """
    last_viewed.db を作成し、必要テーブル/列/索引を保証する。

    重要：
    - 既に last_viewed テーブルが存在する場合、
      その列構成が古い/別名でも壊れないように migration する。
    """
    lv_db = Path(lv_db)
    lv_db.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(lv_db))
    try:
        cur = con.cursor()

        # 1) テーブルが無ければ「新スキーマ」で作る
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS last_viewed (
              user_sub   TEXT NOT NULL,
              item_id    TEXT NOT NULL,
              kind       TEXT NOT NULL,
              viewed_at  TEXT NOT NULL,
              PRIMARY KEY (user_sub, item_id)
            )
            """
        )

        # 2) 既存テーブルの列を調べ、viewed_at が無ければ追加する（migration）
        cols = _table_columns(con, "last_viewed")

        if "viewed_at" not in cols:
            cur.execute("ALTER TABLE last_viewed ADD COLUMN viewed_at TEXT")
            con.commit()

            # 既存DBで使われていた可能性のある「日時列」からコピーして埋める（あれば）
            cols2 = _table_columns(con, "last_viewed")
            src_col = _first_existing(
                cols2,
                [
                    "last_viewed_at",
                    "viewed",
                    "viewed_at_iso",
                    "last_viewed",
                    "viewed_time",
                    "timestamp",
                    "ts",
                ],
            )
            if src_col and src_col != "viewed_at":
                # viewed_at が NULL の行だけ埋める
                cur.execute(
                    f"UPDATE last_viewed SET viewed_at = {src_col} WHERE viewed_at IS NULL"
                )
                con.commit()

        # 3) kind が無いケースも一応吸収（古いDB対策）
        cols3 = _table_columns(con, "last_viewed")
        if "kind" not in cols3:
            cur.execute("ALTER TABLE last_viewed ADD COLUMN kind TEXT")
            con.commit()

        # 4) 必要な索引（列が揃ってから作る）
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_last_viewed_user_kind ON last_viewed(user_sub, kind)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_last_viewed_viewed_at ON last_viewed(viewed_at)"
        )
        con.commit()

    finally:
        con.close()


def upsert_last_viewed(
    lv_db: Path,
    user_sub: str,
    item_id: str,
    kind: str,
    viewed_at_iso: str,
) -> None:
    """
    last_viewed を upsert（プレビュー表示が成立した時点で呼ぶ想定）
    """
    con = sqlite3.connect(str(Path(lv_db)))
    try:
        cur = con.cursor()

        # 既存DBで列が欠けていても、ここで確実に揃える
        ensure_last_viewed_db(Path(lv_db))

        cur.execute(
            """
            INSERT INTO last_viewed(user_sub, item_id, kind, viewed_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(user_sub, item_id)
            DO UPDATE SET kind=excluded.kind, viewed_at=excluded.viewed_at
            """,
            (str(user_sub), str(item_id), str(kind), str(viewed_at_iso)),
        )
        con.commit()
    finally:
        con.close()
