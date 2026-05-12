# -*- coding: utf-8 -*-
# common_lib/inbox/inbox_ui/preview.py
# ============================================================
# Inbox preview（共通プレビュー正本へのラッパー）
# ============================================================
# - Inbox専用の file_path 解決
# - last_viewed 更新
# - 実際のプレビュー表示は common_lib.preview.file_preview に集約
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from pathlib import Path
from typing import Dict, Any

# ============================================================
# inbox imports
# ============================================================
from common_lib.inbox.inbox_common.paths import resolve_file_path
from lib.inbox_common.last_viewed import touch_last_viewed

# ============================================================
# common preview 正本
# ============================================================
from common_lib.preview.file_preview import (
    render_file_preview_with_controls,
    normalize_kind,
)


# ============================================================
# public（Inbox用：プレビュー）
# ============================================================
def render_preview(
    *,
    inbox_root: Path,
    sub: str,
    paths: Dict[str, Path],
    lv_db: Path,
    selected: Dict[str, Any],
) -> None:
    # ------------------------------------------------------------
    # Inbox用プレビュー入口
    # ------------------------------------------------------------
    # - selected から item_id / kind / stored_rel を取得する
    # - Inbox内の実体ファイルPathを解決する
    # - last_viewed を更新する
    # - プレビュー本体は common_lib.preview.file_preview に任せる
    # ------------------------------------------------------------

    item_id = str(selected["item_id"])
    raw_kind = normalize_kind(str(selected.get("kind", "")))

    file_path = resolve_file_path(
        inbox_root,
        sub,
        str(selected["stored_rel"]),
    )

    display_name = str(selected.get("original_name") or file_path.name)

    # ------------------------------------------------------------
    # last_viewed 更新
    # ------------------------------------------------------------
    touch_last_viewed(
        lv_db,
        user_sub=sub,
        item_id=item_id,
        kind=raw_kind,
    )

    # ------------------------------------------------------------
    # Inbox側のキャッシュ保存先
    # ------------------------------------------------------------
    # Word:
    #   paths["word_preview"] / item_id / preview.pdf
    #
    # PPT:
    #   paths["ppt_preview"] / item_id / preview.pdf
    #
    # PDF / Text / Excel / Image:
    #   preview_root は実質使わないが、共通関数の引数として渡す
    # ------------------------------------------------------------
    if raw_kind == "word":
        preview_root = paths["word_preview"]
    elif raw_kind == "ppt":
        preview_root = paths["ppt_preview"]
    else:
        preview_root = paths["root"] / "_preview_cache"

    # ------------------------------------------------------------
    # 共通プレビュー呼び出し
    # ------------------------------------------------------------
    render_file_preview_with_controls(
        file_path=file_path,
        kind=raw_kind,
        preview_root=preview_root,
        preview_id=item_id,
        original_name=display_name,
        title="プレビュー",
    )