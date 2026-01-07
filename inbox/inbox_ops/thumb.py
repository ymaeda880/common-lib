# -*- coding: utf-8 -*-
# common_lib/inbox_ingest/thumb.py
#
# ✅ サムネ生成の正本（common_lib）
# - 保存先は common_lib.inbox_ingest.paths.thumb_path_for_item() を正本とする
# - 生成結果は inbox_items.db の thumb_rel / thumb_status / thumb_error に反映（update_thumb）
# - 既に ok で実体ファイルも存在する場合は再生成しない
#
# 方針：
# - サムネ生成は image のみ
# - pdf/word/excel/text/other は生成しない（常に none）
#
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, Optional

from common_lib.inbox.inbox_common.paths import resolve_file_path, thumb_path_for_item
from common_lib.inbox.inbox_db.items_db import update_thumb


THUMB_W = 320
THUMB_H = 240


# ============================================================
# internal helpers（image only）
# ============================================================
def _pil_letterbox_to_webp(src_img, out_webp: Path, w: int, h: int, quality: int) -> bool:
    """
    PIL.Image を (w,h) に letterbox（余白付き）で収めて webp 保存
    """
    try:
        from PIL import Image
    except Exception:
        return False

    try:
        img = src_img.convert("RGB")
        sw, sh = img.size
        if sw <= 0 or sh <= 0:
            return False

        scale = min(w / sw, h / sh)
        nw = max(1, int(sw * scale))
        nh = max(1, int(sh * scale))

        img2 = img.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGB", (w, h), (255, 255, 255))  # 白背景
        x = (w - nw) // 2
        y = (h - nh) // 2
        canvas.paste(img2, (x, y))

        out_webp.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(str(out_webp), format="WEBP", quality=int(quality), method=6)
        return out_webp.exists()
    except Exception:
        return False


def make_image_thumb_webp(
    src_path: Path,
    out_webp: Path,
    *,
    w: int,
    h: int,
    quality: int,
) -> Tuple[bool, str]:
    """
    画像ファイル → webp サムネ
    """
    try:
        from PIL import Image
    except Exception:
        return False, "Pillow が必要です（pip install pillow）"

    try:
        with Image.open(str(src_path)) as im:
            ok = _pil_letterbox_to_webp(im, out_webp, w=w, h=h, quality=quality)
        return (ok, "" if ok else "サムネ生成に失敗しました")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ============================================================
# public API（正本）
# ============================================================
def ensure_thumb_for_item(
    *,
    inbox_root: Path,
    user_sub: str,
    paths: Dict[str, Path],
    items_db: Path,
    item_id: str,
    kind: str,
    stored_rel: str,
    w: int = THUMB_W,
    h: int = THUMB_H,
    quality: int = 80,
    current_thumb_rel: Optional[str] = None,
    current_thumb_status: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    1件のサムネを保証して、inbox_items の thumb_* を更新する（正本）。

    Returns:
      (thumb_rel, thumb_status, thumb_error)

    thumb_status:
      - ok     : サムネ生成成功
      - failed : 生成失敗（原因は thumb_error）
      - none   : 対象外（方針として作らない）
    """
    item_id = str(item_id)
    k = (kind or "").lower().strip()
    stored_rel = str(stored_rel or "")

    # ============================================================
    # 方針：image 以外は作らない → none に正規化
    # ============================================================
    if k != "image":
        # 以前の値が残っていたら正規化しておく（DB整合）
        if (current_thumb_status or "") != "none" or (current_thumb_rel or ""):
            update_thumb(items_db, item_id, thumb_rel="", status="none", error="")
        return "", "none", ""

    # ============================================================
    # 既に ok + 実体ありなら再生成しない（軽量化）
    # ============================================================
    if (current_thumb_status or "") == "ok" and (current_thumb_rel or ""):
        try:
            abs_thumb = paths["root"] / str(current_thumb_rel)
            if abs_thumb.exists() and abs_thumb.is_file():
                return str(current_thumb_rel), "ok", ""
        except Exception:
            pass  # 下へ（再生成）

    # ============================================================
    # 原本チェック
    # ============================================================
    src_path = resolve_file_path(inbox_root, user_sub, stored_rel)
    if not src_path.exists():
        msg = "原本が存在しません（不整合）"
        update_thumb(items_db, item_id, thumb_rel="", status="failed", error=msg)
        return "", "failed", msg

    # ============================================================
    # 生成（image のみ）
    # ============================================================
    out_webp = thumb_path_for_item(inbox_root, user_sub, "image", item_id)
    ok, err = make_image_thumb_webp(src_path, out_webp, w=w, h=h, quality=quality)

    if ok and out_webp.exists():
        rel = str(out_webp.relative_to(paths["root"]))
        update_thumb(items_db, item_id, thumb_rel=rel, status="ok", error="")
        return rel, "ok", ""

    msg = err or "サムネ生成に失敗しました"
    update_thumb(items_db, item_id, thumb_rel="", status="failed", error=msg)
    return "", "failed", msg
