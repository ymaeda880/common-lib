# common_lib/rag_ingest/generic/selectors.py
# =============================================================================
# RAG ingest : generic（汎用PDF）用 selectors
#
# 役割：
# - 730_汎用DB作成.py から使う generic 用の一覧取得入口をまとめる
# - shard 一覧取得
# - shard 内の原本PDF一覧取得
# - 一覧 item から RAG 用の表示情報へ変換しやすい形を返す
#
# 設計方針：
# - page 側から common_lib.pdf_catalog の関数を直接たくさん呼ばない
# - generic RAG 用の一覧取得入口を本ファイルに寄せる
# - 既存の pdf_catalog 正本 API を利用する
# - 識別子は collection_id / shard_id / doc_id を使う
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from common_lib.pdf_catalog import (
    list_shard_ids_with_source_pdfs,
    list_source_pdfs_by_shard,
)

from .status_ops import (
    GenericRagRowStatus,
    build_generic_rag_row_label,
    get_generic_rag_row_status,
)


# =============================================================================
# row view model
# =============================================================================
@dataclass(slots=True)
class GenericRagSelectableItem:
    # -----------------------------------------------------------------------------
    # 730ページの一覧表示と選択に使う view model
    #
    # raw item（pdf_catalog の一覧 item）に依存しすぎないように、
    # page 側で必要になる情報をここへまとめる。
    # -----------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    doc_id: str
    pdf_filename: str

    row_status: GenericRagRowStatus
    row_label: str

    def to_dict(self) -> dict:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return {
            "collection_id": self.collection_id,
            "shard_id": self.shard_id,
            "doc_id": self.doc_id,
            "pdf_filename": self.pdf_filename,
            "row_status": self.row_status.to_dict(),
            "row_label": self.row_label,
        }


# =============================================================================
# helper
# =============================================================================
def _normalize_collection_id(collection_id: object) -> str:
    # -----------------------------------------------------------------------------
    # collection_id を文字列正規化
    # -----------------------------------------------------------------------------
    return str(collection_id or "").strip()


def _normalize_shard_id(shard_id: object) -> str:
    # -----------------------------------------------------------------------------
    # shard_id を文字列正規化
    # -----------------------------------------------------------------------------
    return str(shard_id or "").strip()


def _normalize_doc_id(doc_id: object) -> str:
    # -----------------------------------------------------------------------------
    # doc_id を文字列正規化
    # -----------------------------------------------------------------------------
    return str(doc_id or "").strip()


def _safe_pdf_filename(item) -> str:
    # -----------------------------------------------------------------------------
    # item から pdf_filename を取得
    # -----------------------------------------------------------------------------
    return str(getattr(item, "pdf_filename", "") or "").strip()


# =============================================================================
# shard 一覧
# =============================================================================
def list_generic_rag_shards(
    archive_root: Path,
    *,
    collection_id: str,
) -> list[str]:
    # -----------------------------------------------------------------------------
    # collection 内で原本PDFが存在する shard 一覧を返す
    #
    # 既存 pdf_catalog 正本 API を利用する。
    # -----------------------------------------------------------------------------
    shard_ids = list_shard_ids_with_source_pdfs(
        archive_root,
        collection_id=str(collection_id),
    )

    out: list[str] = []
    for shard_id in shard_ids:
        s = _normalize_shard_id(shard_id)
        if s:
            out.append(s)

    return out


# =============================================================================
# raw items 一覧
# =============================================================================
def list_generic_rag_raw_items_by_shard(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
):
    # -----------------------------------------------------------------------------
    # shard 内の原本PDF raw items を返す
    #
    # 戻り値は pdf_catalog 側の item オブジェクト列のまま。
    # 必要なら page 側ではなく build_generic_rag_selectable_items_by_shard()
    # を使う。
    # -----------------------------------------------------------------------------
    return list_source_pdfs_by_shard(
        archive_root,
        collection_id=str(collection_id),
        shard_id=str(shard_id),
    )


# =============================================================================
# selectable items 一覧
# =============================================================================
def build_generic_rag_selectable_items_by_shard(
    archive_root: Path,
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    embed_model: str,
) -> list[GenericRagSelectableItem]:
    # -----------------------------------------------------------------------------
    # shard 内の原本PDF一覧を、730ページ用 selectable item に変換して返す
    #
    # 各 item について
    # - row_status
    # - row_label
    # を組み立てる
    # -----------------------------------------------------------------------------
    raw_items = list_generic_rag_raw_items_by_shard(
        archive_root,
        collection_id=str(collection_id),
        shard_id=str(shard_id),
    )

    out: list[GenericRagSelectableItem] = []

    for item in raw_items:
        c = _normalize_collection_id(getattr(item, "collection_id", collection_id))
        s = _normalize_shard_id(getattr(item, "shard_id", shard_id))
        d = _normalize_doc_id(getattr(item, "doc_id", ""))
        fn = _safe_pdf_filename(item)

        row_status = get_generic_rag_row_status(
            archive_root=archive_root,
            databases_root=databases_root,
            collection_id=c,
            shard_id=s,
            doc_id=d,
            pdf_filename=fn,
            embed_model=str(embed_model),
        )

        row_label = build_generic_rag_row_label(
            status=row_status,
        )

        out.append(
            GenericRagSelectableItem(
                collection_id=c,
                shard_id=s,
                doc_id=d,
                pdf_filename=fn,
                row_status=row_status,
                row_label=row_label,
            )
        )

    return out


# =============================================================================
# 単一 item 取得
# =============================================================================
def find_generic_rag_selectable_item(
    items: list[GenericRagSelectableItem],
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Optional[GenericRagSelectableItem]:
    # -----------------------------------------------------------------------------
    # selectable items から1件検索する
    # -----------------------------------------------------------------------------
    c = _normalize_collection_id(collection_id)
    s = _normalize_shard_id(shard_id)
    d = _normalize_doc_id(doc_id)

    for item in items:
        if (
            str(item.collection_id) == c
            and str(item.shard_id) == s
            and str(item.doc_id) == d
        ):
            return item

    return None


# =============================================================================
# selection helper
# =============================================================================
def selected_items_from_keys(
    items: list[GenericRagSelectableItem],
    *,
    selected_keys: set[str],
) -> list[GenericRagSelectableItem]:
    # -----------------------------------------------------------------------------
    # key 集合から選択 item 一覧を返す
    #
    # key format:
    #   "<collection_id>__<shard_id>__<doc_id>"
    # -----------------------------------------------------------------------------
    out: list[GenericRagSelectableItem] = []

    for item in items:
        key = build_generic_rag_item_key(
            collection_id=item.collection_id,
            shard_id=item.shard_id,
            doc_id=item.doc_id,
        )
        if key in selected_keys:
            out.append(item)

    return out


def build_generic_rag_item_key(
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> str:
    # -----------------------------------------------------------------------------
    # page の checkbox key / 選択管理用 key を作る
    # -----------------------------------------------------------------------------
    c = _normalize_collection_id(collection_id)
    s = _normalize_shard_id(shard_id)
    d = _normalize_doc_id(doc_id)
    return f"{c}__{s}__{d}"


# =============================================================================
# paging helper
# =============================================================================
def slice_items_for_page(
    items: list[GenericRagSelectableItem],
    *,
    current_page: int,
    page_size: int,
) -> list[GenericRagSelectableItem]:
    # -----------------------------------------------------------------------------
    # ページ番号と page_size から表示対象を切り出す
    # -----------------------------------------------------------------------------
    page = max(1, int(current_page))
    size = max(1, int(page_size))

    start = (page - 1) * size
    end = start + size
    return items[start:end]


def calc_max_page(
    total_count: int,
    *,
    page_size: int,
) -> int:
    # -----------------------------------------------------------------------------
    # 最大ページ数を返す
    # -----------------------------------------------------------------------------
    total = max(0, int(total_count))
    size = max(1, int(page_size))

    if total == 0:
        return 1

    return ((total - 1) // size) + 1