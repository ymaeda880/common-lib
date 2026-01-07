# -*- coding: utf-8 -*-
# common_lib/inbox_ingest/send.py
#
# ✅ Inbox「送付（コピー）」の正本API（UIなし）
# - from_user の item を読み取り、to_user に新規 item としてコピーする
# - タグ保持 / origin_* 記録 / サムネは image のみ
# - 送付ログは _meta/send_log.jsonl に追記

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
import json
import uuid
import sqlite3

from common_lib.inbox.inbox_common.types import (
    InboxNotAvailable,
    QuotaExceeded,
    IngestFailed,
)

from common_lib.inbox.inbox_common.paths import (
    resolve_inbox_root,
    ensure_user_dirs,
    items_db_path,
)

from common_lib.inbox.inbox_db.items_db import (
    ensure_items_db,
    insert_item,
    update_thumb,
)

from common_lib.inbox.inbox_ops.quota import (
    folder_size_bytes,
    quota_bytes_for_user,
)

from common_lib.inbox.inbox_common.utils import (
    now_iso_jst,
    safe_filename,
)

from common_lib.inbox.inbox_ops.thumb import (
    ensure_thumb_for_item,
    THUMB_W,
    THUMB_H,
)



def _read_item_row(items_db: Path, item_id: str) -> Dict[str, Any]:
    """items_db から item_id の行を dict で返す（最低限必要な列のみ）"""
    if not items_db.exists():
        raise IngestFailed(f"items.db not found: {items_db}")

    con = sqlite3.connect(str(items_db))
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(
            """
            SELECT
              item_id,
              kind,
              stored_rel,
              original_name,
              tags_json,
              size_bytes
            FROM inbox_items
            WHERE item_id = ?
            """,
            (item_id,),
        )
        row = cur.fetchone()
        if not row:
            raise IngestFailed(f"item not found: {item_id}")
        return dict(row)
    finally:
        con.close()


def _append_send_log(inbox_root: Path, rec: Dict[str, Any]) -> None:
    meta = inbox_root / "_meta"
    meta.mkdir(parents=True, exist_ok=True)
    log_path = meta / "send_log.jsonl"
    line = json.dumps(rec, ensure_ascii=False)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def send_item_copy(
    *,
    projects_root: Path,
    inbox_root: Path | None = None,
    from_user: str,
    to_user: str,
    item_id: str,
) -> str:
    """
    送付（コピー）の正本API（UIなし）
    戻り値：送付先で作られた new_item_id
    """
    # ------------------------------------------------------------
    # Inbox root 解決
    # ------------------------------------------------------------
    _inbox_root = inbox_root or resolve_inbox_root(projects_root)
    if not _inbox_root.exists():
        raise InboxNotAvailable(f"Inbox root not found: {_inbox_root}")

    if not from_user or not to_user or from_user == to_user:
        raise IngestFailed("invalid from/to user")

    # ------------------------------------------------------------
    # 送付元 item の情報取得
    # ------------------------------------------------------------
    from_items_db = items_db_path(_inbox_root, from_user)
    row = _read_item_row(from_items_db, item_id)

    raw_kind = (row.get("kind") or "other").lower()
    stored_rel = str(row.get("stored_rel") or "")
    if not stored_rel:
        raise IngestFailed("stored_rel missing")

    from_paths = ensure_user_dirs(_inbox_root, from_user)
    src_path = (from_paths["root"] / stored_rel).resolve()

    if not src_path.exists():
        raise IngestFailed(f"source file not found: {src_path}")

    data = src_path.read_bytes()
    incoming = len(data)

    # ------------------------------------------------------------
    # 容量チェック（送付先）
    # ------------------------------------------------------------
    to_paths = ensure_user_dirs(_inbox_root, to_user)
    current = folder_size_bytes(to_paths["root"])
    quota = quota_bytes_for_user(to_user)
    if current + incoming > quota:
        raise QuotaExceeded(current, incoming, quota)

    # ------------------------------------------------------------
    # 送付先へ保存（kind別ベース配下 / YYYY/MM/DD）
    # ------------------------------------------------------------
    base_key = f"{raw_kind}_files"
    base = to_paths.get(base_key, to_paths["other_files"])

    # 例：2026/01/04
    day_dir = Path(base) / now_iso_jst()[:10].replace("-", "/")
    day_dir.mkdir(parents=True, exist_ok=True)

    new_item_id = str(uuid.uuid4())
    safe_name = safe_filename(str(row.get("original_name") or src_path.name))
    filename = f"{new_item_id}__{safe_name}"
    out_path = day_dir / filename

    try:
        out_path.write_bytes(data)
    except Exception as e:
        raise IngestFailed(f"Failed to write file: {type(e).__name__}: {e}")

    new_stored_rel = str(out_path.relative_to(to_paths["root"]))
    added_at = now_iso_jst()
    tags_json_src = str(row.get("tags_json") or "[]")

    # ------------------------------------------------------------
    # DB登録（送付先）
    # ------------------------------------------------------------
    to_items_db = items_db_path(_inbox_root, to_user)
    ensure_items_db(to_items_db)

    try:
        insert_item(
            to_items_db,
            {
                "item_id": new_item_id,
                "kind": raw_kind,
                "stored_rel": new_stored_rel,
                "original_name": str(row.get("original_name") or src_path.name),
                "added_at": added_at,
                "size_bytes": incoming,
                "tags_json": tags_json_src,
                "thumb_rel": "",
                "thumb_status": "none",
                "thumb_error": "",
                "origin_user": from_user,
                "origin_item_id": item_id,
                "origin_type": "copy",
            },
        )
    except Exception as e:
        try:
            out_path.unlink(missing_ok=True)
        finally:
            raise IngestFailed(f"DB insert failed: {type(e).__name__}: {e}")

    # ------------------------------------------------------------
    # サムネ（imageのみ）
    # ------------------------------------------------------------
    if raw_kind == "image":
        thumb_rel, thumb_status, thumb_err = ensure_thumb_for_item(
            inbox_root=_inbox_root,
            user_sub=to_user,
            paths=to_paths,
            items_db=to_items_db,
            item_id=new_item_id,
            kind=raw_kind,
            stored_rel=new_stored_rel,
            w=THUMB_W,
            h=THUMB_H,
        )
        update_thumb(to_items_db, new_item_id, thumb_rel=thumb_rel, status=thumb_status, error=thumb_err)

    # ------------------------------------------------------------
    # 送付ログ（JSONL）
    # ------------------------------------------------------------
    _append_send_log(
        _inbox_root,
        {
            "at": now_iso_jst(),
            "from_user": from_user,
            "to_user": to_user,
            "origin_item_id": item_id,
            "new_item_id": new_item_id,
            "kind": raw_kind,
            "origin_type": "copy",
            "origin_name": str(row.get("original_name") or ""),
            "tags_json": tags_json_src,
        },
    )

    return new_item_id
