# -*- coding: utf-8 -*-
# common_lib/inbox_bulk/zip_ops.py
from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Callable


def _fetch_item_meta(items_db: Path, item_id: str) -> Dict[str, Any] | None:
    """
    items_db から ZIP 作成に必要な最小情報だけ取得する。
    """
    try:
        con = sqlite3.connect(str(items_db))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            "SELECT item_id, kind, stored_rel, original_name FROM inbox_items WHERE item_id=?",
            (item_id,),
        )
        row = cur.fetchone()
        con.close()
        if not row:
            return None
        return dict(row)
    except Exception:
        return None


def build_zip_bytes_for_checked(
    *,
    checked_ids: Set[str],
    items_db: Path,
    inbox_root: Path,
    user_sub: str,
    resolve_file_path: Callable[[Path, str, str], Path],
    safe_filename: Callable[[str], str],
) -> Tuple[bytes, List[str], List[str]]:
    """
    選択 item_id 群から ZIP(bytes) を作る。

    戻り値:
      (zip_bytes, ok_ids, ng_ids)
    """
    ok_ids: List[str] = []
    ng_ids: List[str] = []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _id in sorted(checked_ids):
            meta = _fetch_item_meta(items_db, _id)
            if not meta:
                ng_ids.append(_id)
                continue

            stored_rel = str(meta.get("stored_rel") or "")
            orig = str(meta.get("original_name") or "")
            kind = str(meta.get("kind") or "")

            if not stored_rel:
                ng_ids.append(_id)
                continue

            path = resolve_file_path(inbox_root, user_sub, stored_rel)
            if not path.exists():
                ng_ids.append(_id)
                continue

            safe = safe_filename(orig or path.name)
            arcname = f"{kind}/{_id}__{safe}"
            zf.writestr(arcname, path.read_bytes())
            ok_ids.append(_id)

    return buf.getvalue(), ok_ids, ng_ids
