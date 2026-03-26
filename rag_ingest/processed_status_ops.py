# common_lib/rag_ingest/processed_status_ops.py
# =============================================================================
# RAG ingest : processed status 正本API
#
# 役割：
# - processed_files.json を正本として、RAG取込済み状態を判定する
# - shard 単位で processed record を読み込む
# - doc_id 単位で RAG取込済みかどうかを返す
# - 一覧表示用に processed doc_id 集合を返す
#
# 設計方針：
# - RAG取込済み判定の正本は processed_files.json とする
# - page 側では processed_files.json を直接読まない
# - collection_id / shard_id を明示して判定する
# - 将来、内部実装を JSON 以外へ変更しても page 側に影響を出さない
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from pathlib import Path

from .vectorstore_io import load_processed_records


# =============================================================================
# public
# =============================================================================
def get_processed_doc_id_set(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> set[str]:
    processed_path = (
        Path(databases_root)
        / "vectorstore"
        / str(collection_id)
        / str(shard_id)
        / "processed_files.json"
    )

    records = load_processed_records(processed_path)

    out: set[str] = set()

    for rec in records:
        doc_id = str(getattr(rec, "doc_id", "") or "").strip()
        if doc_id:
            out.add(doc_id)

    return out


def is_doc_ingested(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> bool:
    # -------------------------------------------------------------------------
    # 指定 doc_id が processed_files.json に存在するかを返す
    # -------------------------------------------------------------------------
    target_doc_id = str(doc_id or "").strip()
    if not target_doc_id:
        return False

    doc_id_set = get_processed_doc_id_set(
        databases_root,
        collection_id=str(collection_id),
        shard_id=str(shard_id),
    )

    return target_doc_id in doc_id_set