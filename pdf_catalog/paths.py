# common_lib/pdf_catalog/paths.py
# =============================================================================
# 汎用PDFカタログ：path 解決
#
# 役割：
# - Archive/<collection_id>/pdfs/<shard_id>/ 配下の原本PDFのpathを解決する
# - Archive/<collection_id>/<shard_id>/<doc_id>/ 配下の展開先pathを解決する
# - processing_status.json / pdf_status.json の配置を project と揃える
#
# 前提：
# - 原本PDF:
#   Archive/<collection_id>/pdfs/<shard_id>/<doc_id>.pdf
#
# - 展開先:
#   Archive/<collection_id>/<shard_id>/<doc_id>/
#       pdf/
#       text/
#       ocr/
#       others/
#
# - processing_status.json:
#   Archive/<collection_id>/<shard_id>/<doc_id>/text/processing_status.json
#
# - pdf_status.json:
#   Archive/<collection_id>/<shard_id>/<doc_id>/pdf/pdf_status.json
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from pathlib import Path


# =============================================================================
# collection / source pdf paths
# =============================================================================
def get_collection_root(
    archive_root: Path,
    *,
    collection_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # collection root
    # -------------------------------------------------------------------------
    return Path(archive_root) / str(collection_id)


def get_pdfs_root(
    archive_root: Path,
    *,
    collection_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # 原本PDFルート
    # -------------------------------------------------------------------------
    return get_collection_root(
        archive_root,
        collection_id=collection_id,
    ) / "pdfs"


def get_shard_pdfs_dir(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # 原本PDFの shard directory
    # -------------------------------------------------------------------------
    return get_pdfs_root(
        archive_root,
        collection_id=collection_id,
    ) / str(shard_id)


def get_source_pdf_path(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    extension: str = ".pdf",
) -> Path:
    # -------------------------------------------------------------------------
    # 原本PDF path
    # - extension は ".pdf" を想定
    # -------------------------------------------------------------------------
    ext = str(extension or ".pdf")
    if not ext.startswith("."):
        ext = f".{ext}"

    return get_shard_pdfs_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
    ) / f"{doc_id}{ext}"


# =============================================================================
# doc layout paths
# =============================================================================
def get_doc_root(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # 展開後 doc root
    # -------------------------------------------------------------------------
    return (
        get_collection_root(
            archive_root,
            collection_id=collection_id,
        )
        / str(shard_id)
        / str(doc_id)
    )


def get_doc_pdf_dir(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # 展開後 pdf directory
    # -------------------------------------------------------------------------
    return get_doc_root(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "pdf"


def get_doc_text_dir(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # 展開後 text directory
    # -------------------------------------------------------------------------
    return get_doc_root(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "text"


def get_doc_ocr_dir(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # 展開後 ocr directory
    # -------------------------------------------------------------------------
    return get_doc_root(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "ocr"


def get_doc_others_dir(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # 展開後 others directory
    # -------------------------------------------------------------------------
    return get_doc_root(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "others"


# =============================================================================
# status file paths
# =============================================================================
def get_doc_pdf_status_path(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # pdf/pdf_status.json
    # -------------------------------------------------------------------------
    return get_doc_pdf_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "pdf_status.json"


def get_doc_processing_status_path(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # text/processing_status.json
    # - project と完全一致
    # -------------------------------------------------------------------------
    return get_doc_text_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "processing_status.json"


# =============================================================================
# directory prepare
# =============================================================================
def ensure_doc_layout_dirs(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> dict[str, Path]:
    # -------------------------------------------------------------------------
    # doc layout の各directoryを作成して返す
    # -------------------------------------------------------------------------
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
    text_dir = get_doc_text_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    ocr_dir = get_doc_ocr_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    others_dir = get_doc_others_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    for p in (doc_root, pdf_dir, text_dir, ocr_dir, others_dir):
        p.mkdir(parents=True, exist_ok=True)

    return {
        "doc_root": doc_root,
        "pdf_dir": pdf_dir,
        "text_dir": text_dir,
        "ocr_dir": ocr_dir,
        "others_dir": others_dir,
    }


def get_raw_text_path(archive_root, *, collection_id, shard_id, doc_id):
    return get_doc_text_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "report_raw.txt"


def get_raw_pages_json_path(archive_root, *, collection_id, shard_id, doc_id):
    return get_doc_text_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "report_raw_pages.json"


def get_clean_text_path(archive_root, *, collection_id, shard_id, doc_id):
    return get_doc_text_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "report_clean.txt"