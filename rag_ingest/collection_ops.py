# common_lib/rag_ingest/collection_ops.py
# =============================================================================
# collection operations（RAG ingest 共通ライブラリ）
#
# 役割：
# - Databases/vectorstore/ 配下の collection_id 一覧を取得する
# - collection_id の存在確認を行う
# - collection_id 配下の shard_id 一覧を取得する
#
# 方針：
# - vectorstore ディレクトリ構造を正本とする
# - collection_id は設定ファイル固定ではなく、フォルダ構造から動的取得する
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from pathlib import Path


# =============================================================================
# helper：vectorstore root
# =============================================================================
def _resolve_vectorstore_root(databases_root: Path) -> Path:
    # -------------------------------------------------------------------------
    # vectorstore ルートを返す
    # -------------------------------------------------------------------------
    return Path(databases_root) / "vectorstore"


# =============================================================================
# public：collection 一覧
# =============================================================================
def list_collection_ids(databases_root: Path) -> list[str]:
    # -------------------------------------------------------------------------
    # Databases/vectorstore/ 配下の collection_id 一覧を返す
    # -------------------------------------------------------------------------
    root = _resolve_vectorstore_root(databases_root)

    if not root.exists():
        return []

    ids: list[str] = []

    for p in root.iterdir():
        if not p.is_dir():
            continue

        name = p.name.strip()
        if not name:
            continue

        if name.startswith("_"):
            continue

        ids.append(name)

    ids.sort()
    return ids


# =============================================================================
# public：collection 存在判定
# =============================================================================
def collection_exists(
    databases_root: Path,
    collection_id: str,
) -> bool:
    # -------------------------------------------------------------------------
    # collection_id が存在するか判定する
    # -------------------------------------------------------------------------
    root = _resolve_vectorstore_root(databases_root)
    return (root / str(collection_id)).exists()


# =============================================================================
# public：collection path
# =============================================================================
def resolve_collection_path(
    databases_root: Path,
    collection_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # collection ディレクトリの Path を返す
    # -------------------------------------------------------------------------
    root = _resolve_vectorstore_root(databases_root)
    return root / str(collection_id)


# =============================================================================
# public：shard 一覧
# =============================================================================
def list_shard_ids(
    databases_root: Path,
    collection_id: str,
) -> list[str]:
    # -------------------------------------------------------------------------
    # collection 配下の shard_id 一覧を返す
    # -------------------------------------------------------------------------
    collection_dir = resolve_collection_path(databases_root, collection_id)

    if not collection_dir.exists():
        return []

    shard_ids: list[str] = []

    for p in collection_dir.iterdir():
        if not p.is_dir():
            continue

        name = p.name.strip()
        if not name:
            continue

        if name.startswith("_"):
            continue

        shard_ids.append(name)

    shard_ids.sort()
    return shard_ids