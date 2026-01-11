# -*- coding: utf-8 -*-

# common_lib/inbox/inbox_common/paths.py
# ============================================================
# Inbox パス規約（正本）
# ============================================================
# - Inbox のディレクトリ構造は全ページで一致しているべき「規約」なのでここに集約
# - UI（Streamlit）依存は入れない
# ============================================================

from __future__ import annotations

from pathlib import Path
from typing import Dict

from common_lib.storage.external_ssd_root import resolve_storage_subdir_root


"""
========================================
📌 Inbox directory structure (canonical)
========================================

- InBoxStorages 配下の「物理ディレクトリ構造」を共通で固定する。
- common_lib 側が正本（他アプリからも import される前提）。
- auth_portal_app 側の lib/ は、必要ならこの common_lib の薄いラッパーにする。

サムネ方針：
- サムネ生成は image のみ。
- pdf / word / ppt / other はサムネを作らない前提。

プレビュー派生物（将来含む）：
- pdf:  pdf/preview/<item_id>/p001.png ...
- word: word/preview/<item_id>/preview.pdf
- ppt:  ppt/preview/<item_id>/preview.pdf
========================================
"""


# ============================================================
# Root
# ============================================================
def resolve_inbox_root(projects_root: Path) -> Path:
    """
    InBoxStorages のルートを resolver 経由で解決する（正本）。
    ※ 重要機能の暗黙デフォルト禁止：resolver が決定する。
    """
    return resolve_storage_subdir_root(projects_root, subdir="InBoxStorages")


def user_root(inbox_root: Path, sub: str) -> Path:
    return inbox_root / sub


# ============================================================
# Directory map（共通・固定）
# ============================================================
def ensure_user_dirs(inbox_root: Path, sub: str) -> Dict[str, Path]:
    """
    Inbox のユーザーディレクトリ配下の共通パスを用意する。
    - 返すキーは 20/21/22… で共通利用する前提。
    - ここで作るのは「ディレクトリだけ」。DB は別責務。
    """
    root = user_root(inbox_root, sub)

    paths: Dict[str, Path] = {
        # ---- base ----
        "root": root,
        "_meta": root / "_meta",

        # ---- preview ----
        "pdf_preview": root / "pdf" / "preview",
        "word_preview": root / "word" / "preview",
        "excel_preview": root / "excel" / "preview",
        "ppt_preview": root / "ppt" / "preview",
        "text_preview": root / "text" / "preview",
        "other_preview": root / "other" / "preview",

        # ---- thumbs ----
        # ※ サムネ生成は image のみ
        "image_thumbs": root / "image" / "thumbs",

        # ---- files（原本格納）----
        "pdf_files": root / "pdf" / "files",
        "word_files": root / "word" / "files",
        "excel_files": root / "excel" / "files",
        "ppt_files": root / "ppt" / "files",
        "text_files": root / "text" / "files",
        "image_files": root / "image" / "files",

        # ---- other（何でも受け入れる受け皿）----
        "other_files": root / "other" / "files",

        # ---- thumbs（将来用・互換維持）----
        "pdf_thumbs": root / "pdf" / "thumbs",
        "word_thumbs": root / "word" / "thumbs",

        # ---- work（変換作業領域：表示しない）----
        "word_work": root / "word" / "work",
        "ppt_work": root / "ppt" / "work",
    }

    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    return paths


# ============================================================
# DB paths
# ============================================================
def items_db_path(inbox_root: Path, sub: str) -> Path:
    return user_root(inbox_root, sub) / "_meta" / "inbox_items.db"


def last_viewed_db_path(inbox_root: Path, sub: str) -> Path:
    return user_root(inbox_root, sub) / "_meta" / "last_viewed.db"


# ============================================================
# Resolve stored file path
# ============================================================
def resolve_file_path(inbox_root: Path, sub: str, stored_rel: str) -> Path:
    return user_root(inbox_root, sub) / stored_rel


# ============================================================
# Preview / thumbs helpers
# ============================================================
def thumbs_dir_for_item(inbox_root: Path, sub: str, item_id: str) -> Path:
    """
    【将来用（複数サムネ）】
    item_id ディレクトリ配下に複数サムネを置く場合の保存先。
    現状は単一サムネ運用でも、この関数は残す。
    """
    return user_root(inbox_root, sub) / "image" / "thumbs" / str(item_id)


def preview_dir_for_item(inbox_root: Path, sub: str, kind: str, item_id: str) -> Path:
    """
    変換プレビューの保存先（kind別、item_id 単位）
    """
    k = (kind or "").lower()
    if k == "pdf":
        return user_root(inbox_root, sub) / "pdf" / "preview" / str(item_id)
    if k == "word":
        return user_root(inbox_root, sub) / "word" / "preview" / str(item_id)
    if k == "ppt":
        return user_root(inbox_root, sub) / "ppt" / "preview" / str(item_id)
    if k == "excel":
        return user_root(inbox_root, sub) / "excel" / "preview" / str(item_id)
    if k == "text":
        return user_root(inbox_root, sub) / "text" / "preview" / str(item_id)
    return user_root(inbox_root, sub) / "other" / "preview" / str(item_id)


def thumb_path_for_item(inbox_root: Path, sub: str, kind: str, item_id: str) -> Path:
    """
    【単一サムネ運用】

    注意：
    - サムネ生成は image のみ。
    - pdf / word / ppt / other はサムネを作らない前提。
    - 本関数は「置き場所の正本」を返すだけ。
    """
    base = user_root(inbox_root, sub)
    return base / "image" / "thumbs" / f"{item_id}.webp"
