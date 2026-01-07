# -*- coding: utf-8 -*-
# common_lib/inbox_ingest/delete.py

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

from ..inbox_common.paths import ensure_user_dirs, items_db_path, resolve_file_path


def _fetch_item_row(items_db: Path, item_id: str) -> Optional[Dict[str, Any]]:
    con = sqlite3.connect(str(items_db))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT item_id, kind, stored_rel, thumb_rel FROM inbox_items WHERE item_id=?",
        (item_id,),
    )
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None


def _delete_item_row(items_db: Path, item_id: str) -> None:
    con = sqlite3.connect(str(items_db))
    cur = con.cursor()
    cur.execute("DELETE FROM inbox_items WHERE item_id=?", (item_id,))
    con.commit()
    con.close()


def delete_item(inbox_root: Path, user_sub: str, item_id: str) -> Tuple[bool, str]:
    """
    Inbox 1件削除（正本：items_db + 実体ファイル + サムネ）
    - last_viewed 等の派生DBには触れない（必要なら別途拡張）
    """
    try:
        paths = ensure_user_dirs(inbox_root, user_sub)
        items_db = items_db_path(inbox_root, user_sub)

        row = _fetch_item_row(items_db, item_id)
        if not row:
            return False, f"DBに存在しません: item_id={item_id}"

        stored_rel = str(row.get("stored_rel") or "")
        thumb_rel = str(row.get("thumb_rel") or "")

        # 1) 実体ファイル削除（あれば）
        if stored_rel:
            p = resolve_file_path(inbox_root, user_sub, stored_rel)
            if p.exists():
                p.unlink()

        # 2) サムネ削除（あれば）
        if thumb_rel:
            t = (paths["root"] / thumb_rel)
            if t.exists():
                t.unlink()

        # 3) DB行削除
        _delete_item_row(items_db, item_id)

        return True, f"削除しました: {item_id}"

    except Exception as e:
        return False, f"削除に失敗しました: {e}"
