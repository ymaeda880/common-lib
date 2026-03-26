# common_lib/pdf_catalog/status.py
# =============================================================================
# 汎用PDFカタログ：status 読み取り / 表示用status構築
#
# 役割：
# - pdf/pdf_status.json を読む
# - text/processing_status.json を読む
# - 710ページ一覧表示用の display status を構築する
#
# 方針：
# - 一覧表示の正本は processing_status.json を優先する
# - pdf_status.json は登録情報のみ
# - RAG取込済み判定は processed_files.json 側の doc_id set で受け取る
# - project と違い lock_flag は持たない
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .paths import (
    get_doc_pdf_dir,
    get_doc_text_dir,
    get_doc_root,
    get_doc_pdf_status_path,
    get_doc_processing_status_path,
    get_source_pdf_path,
)


# =============================================================================
# data model
# =============================================================================
@dataclass(frozen=True)
class GenericPdfDisplayStatus:
    # -------------------------------------------------------------------------
    # 一覧表示用 status
    # -------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    doc_id: str
    pdf_filename: str

    source_pdf_exists: bool
    expanded_exists: bool

    pdf_kind: str
    page_count: Optional[int]
    page_count_display: object

    ocr_done: bool
    text_extracted: bool
    cleaned: bool

    raw_exists: bool
    clean_exists: bool

    ok_ready: bool
    rag_done: bool

    pdf_status_exists: bool
    processing_status_exists: bool


# =============================================================================
# json read helpers
# =============================================================================
def _read_json_dict_or_none(path: Path) -> Optional[dict[str, Any]]:
    # -------------------------------------------------------------------------
    # JSON dict を読む
    # - 無ければ None
    # - 壊れていれば例外
    # -------------------------------------------------------------------------
    p = Path(path)
    if not p.exists():
        return None

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"JSON object ではありません: {p}")

    return data


# =============================================================================
# public readers
# =============================================================================
def read_generic_pdf_status(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Optional[dict[str, Any]]:
    # -------------------------------------------------------------------------
    # pdf/pdf_status.json を読む
    # -------------------------------------------------------------------------
    return _read_json_dict_or_none(
        get_doc_pdf_status_path(
            archive_root,
            collection_id=collection_id,
            shard_id=shard_id,
            doc_id=doc_id,
        )
    )


def read_generic_processing_status(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Optional[dict[str, Any]]:
    # -------------------------------------------------------------------------
    # text/processing_status.json を読む
    # -------------------------------------------------------------------------
    return _read_json_dict_or_none(
        get_doc_processing_status_path(
            archive_root,
            collection_id=collection_id,
            shard_id=shard_id,
            doc_id=doc_id,
        )
    )


# =============================================================================
# display helpers
# =============================================================================
def _normalize_pdf_kind(value: Any) -> str:
    # -------------------------------------------------------------------------
    # pdf_kind を一覧表示用に整える
    # -------------------------------------------------------------------------
    v = str(value or "").strip().lower()
    if v in ("text", "image"):
        return v
    return ""


def _normalize_positive_int(value: Any) -> Optional[int]:
    # -------------------------------------------------------------------------
    # 正の int へ正規化
    # -------------------------------------------------------------------------
    try:
        n = int(value)
        if n > 0:
            return n
    except Exception:
        pass
    return None


def _get_page_count_display(page_count: Optional[int]) -> object:
    # -------------------------------------------------------------------------
    # page_count 表示用
    # -------------------------------------------------------------------------
    if page_count is None:
        return "未計算"
    return page_count


def _get_raw_text_path(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # report_raw 相当
    # -------------------------------------------------------------------------
    return get_doc_text_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "report_raw.txt"


def _get_clean_text_path(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # report_clean 相当
    # -------------------------------------------------------------------------
    return get_doc_text_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "report_clean.txt"


# =============================================================================
# display status builder
# =============================================================================
def build_generic_pdf_display_status(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    processed_doc_id_set: Optional[set[str]] = None,
) -> GenericPdfDisplayStatus:
    # -------------------------------------------------------------------------
    # 一覧表示用 status を構築する
    # -------------------------------------------------------------------------
    processed_set = processed_doc_id_set or set()

    source_pdf_path = get_source_pdf_path(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
        extension=".pdf",
    )
    doc_root = get_doc_root(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    pdf_dir = get_doc_pdf_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    pdf_status = read_generic_pdf_status(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    proc = read_generic_processing_status(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    pdf_kind = _normalize_pdf_kind((proc or {}).get("pdf_kind"))
    page_count = _normalize_positive_int((proc or {}).get("page_count"))

    ocr_done = bool((proc or {}).get("ocr_done", False))
    text_extracted = bool((proc or {}).get("text_extracted", False))
    cleaned = bool((proc or {}).get("cleaned", False))

    raw_path = _get_raw_text_path(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    clean_path = _get_clean_text_path(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    raw_exists = raw_path.exists()
    clean_exists = clean_path.exists()

    # -------------------------------------------------------------------------
    # 汎用版の OK 判定
    # - text  : raw があれば OK
    # - image : clean があれば OK
    # -------------------------------------------------------------------------
    if pdf_kind == "text":
        ok_ready = raw_exists or text_extracted
    elif pdf_kind == "image":
        ok_ready = clean_exists or cleaned
    else:
        ok_ready = False

    rag_done = str(doc_id) in processed_set

    return GenericPdfDisplayStatus(
        collection_id=str(collection_id),
        shard_id=str(shard_id),
        doc_id=str(doc_id),
        pdf_filename=source_pdf_path.name,
        source_pdf_exists=source_pdf_path.exists(),
        expanded_exists=doc_root.exists() and pdf_dir.exists(),
        pdf_kind=pdf_kind,
        page_count=page_count,
        page_count_display=_get_page_count_display(page_count),
        ocr_done=ocr_done,
        text_extracted=text_extracted,
        cleaned=cleaned,
        raw_exists=raw_exists,
        clean_exists=clean_exists,
        ok_ready=ok_ready,
        rag_done=rag_done,
        pdf_status_exists=pdf_status is not None,
        processing_status_exists=proc is not None,
    )