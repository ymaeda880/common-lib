# -*- coding: utf-8 -*-
# common_lib/inbox_ingest/ingest.py
#
# ✅ 他アプリ → Inbox 保存（正本API）
# - common_lib だけに依存（auth_portal_app の lib/ に依存しない）
# - Inbox未存在 / 容量超過 を例外で通知（UI側で st.warning 等にする）
# - サムネは image のみ（ensure_thumb_for_item が方針を担保）

from __future__ import annotations

from pathlib import Path
import uuid


from common_lib.inbox.inbox_common.types import (
    IngestRequest,
    IngestResult,
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
)

from common_lib.inbox.inbox_common.utils import (
    detect_kind,
    safe_filename,
    now_iso_jst,
)

from common_lib.inbox.inbox_ops.quota import (
    folder_size_bytes,
    quota_bytes_for_user,
)

# ✅ サムネ正本（imageのみ作る／他は none に揃える）
from common_lib.inbox.inbox_ops.thumb import (
    ensure_thumb_for_item,
    THUMB_W,
    THUMB_H,
)



def ingest_to_inbox(
    *,
    projects_root: Path,
    req: IngestRequest,
) -> IngestResult:
    """
    他アプリ → Inbox 保存の正本API（UIなし）
    - 失敗時は例外（UI側で捕捉して warning/error 表示）
    """

    # ------------------------------------------------------------
    # Inbox 解決（存在しないなら UI 側で警告できるように例外）
    # ------------------------------------------------------------
    inbox_root = resolve_inbox_root(projects_root)
    if not inbox_root.exists():
        raise InboxNotAvailable(f"Inbox root not found: {inbox_root}")

    # ------------------------------------------------------------
    # ユーザー配下準備（ディレクトリ＋DB）
    # ------------------------------------------------------------
    paths = ensure_user_dirs(inbox_root, req.user_sub)
    items_db = items_db_path(inbox_root, req.user_sub)
    ensure_items_db(items_db)

    # ------------------------------------------------------------
    # 容量チェック（保存前に判定）
    # ------------------------------------------------------------
    current = folder_size_bytes(paths["root"])
    incoming = len(req.data or b"")
    quota = quota_bytes_for_user(req.user_sub)

    if current + incoming > quota:
        raise QuotaExceeded(current, incoming, quota)

    # ------------------------------------------------------------
    # 保存先決定（kind → kind_files、無ければ other_files）
    # ------------------------------------------------------------
    kind = detect_kind(req.filename)
    base = paths.get(f"{kind}_files", paths["other_files"])

    # 例：2026/01/04
    day_dir = Path(base) / now_iso_jst()[:10].replace("-", "/")
    day_dir.mkdir(parents=True, exist_ok=True)

    item_id = str(uuid.uuid4())
    safe_name = safe_filename(req.filename)
    filename = f"{item_id}__{safe_name}"
    out_path = day_dir / filename

    # ------------------------------------------------------------
    # 実体保存
    # ------------------------------------------------------------
    try:
        out_path.write_bytes(req.data or b"")
    except Exception as e:
        raise IngestFailed(f"Failed to write file: {type(e).__name__}: {e}")

    stored_rel = str(out_path.relative_to(paths["root"]))
    added_at = now_iso_jst()

    # ------------------------------------------------------------
    # DB登録（失敗したらロールバック：ファイル削除）
    # ------------------------------------------------------------
    # origin_* は「送付/コピー」等の出自がある場合のみ埋める
    origin_user = getattr(req, "origin_user", "") or ""
    origin_item_id = getattr(req, "origin_item_id", "") or ""
    origin_type = getattr(req, "origin_type", "") or ""

    try:
        insert_item(
            items_db,
            {
                "item_id": item_id,
                "kind": kind,
                "stored_rel": stored_rel,
                "original_name": req.filename,
                "added_at": added_at,
                "size_bytes": incoming,
                "tags_json": getattr(req, "tags_json", "[]") or "[]",
                "thumb_rel": "",
                "thumb_status": "none",
                "thumb_error": "",
                "origin_user": origin_user,
                "origin_item_id": origin_item_id,
                "origin_type": origin_type,
            },
        )
    except Exception as e:
        try:
            out_path.unlink(missing_ok=True)
        finally:
            raise IngestFailed(f"DB insert failed: {type(e).__name__}: {e}")

    # ------------------------------------------------------------
    # サムネ（imageのみ。その他は none に正規化）
    # ------------------------------------------------------------
    _thumb_rel, thumb_status, _thumb_err = ensure_thumb_for_item(
        inbox_root=inbox_root,
        user_sub=req.user_sub,
        paths=paths,
        items_db=items_db,
        item_id=item_id,
        kind=kind,
        stored_rel=stored_rel,
        w=THUMB_W,
        h=THUMB_H,
    )

    return IngestResult(
        item_id=item_id,
        kind=kind,
        stored_rel=stored_rel,
        size_bytes=incoming,
        thumb_status=thumb_status,
    )
