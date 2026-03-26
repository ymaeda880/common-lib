# common_lib/pdf_catalog/scan.py
# =============================================================================
# 汎用PDFカタログ：source pdf scan
#
# 役割：
# - Archive/<collection_id>/pdfs 配下を走査する
# - collection_id 一覧 / shard_id 一覧 / source pdf 一覧を返す
#
# 方針：
# - 原本PDFの正本は Archive/<collection_id>/pdfs/<shard_id>/*.pdf
# - doc_id は pdf拡張子を除いたファイル名
# - shard_id は pdfs 直下のディレクトリ名（stringとして扱う）
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from dataclasses import dataclass
from pathlib import Path


# =============================================================================
# data model
# =============================================================================
@dataclass(frozen=True)
class GenericPdfSourceRecord:
    # -------------------------------------------------------------------------
    # 原本PDF 1件
    # -------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    doc_id: str
    pdf_path: Path
    pdf_filename: str


# =============================================================================
# collection scan
# =============================================================================
def list_collection_ids_with_pdfs(
    archive_root: Path,
) -> list[str]:
    # -------------------------------------------------------------------------
    # Archive 直下から、pdfs フォルダーを持つ collection_id を返す
    # -------------------------------------------------------------------------
    root = Path(archive_root)
    if not root.exists():
        return []

    values: list[str] = []

    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue

        pdfs_dir = p / "pdfs"
        if pdfs_dir.exists() and pdfs_dir.is_dir():
            values.append(p.name)

    return values


# =============================================================================
# shard scan
# =============================================================================
def list_shard_ids_with_source_pdfs(
    archive_root: Path,
    *,
    collection_id: str,
) -> list[str]:
    # -------------------------------------------------------------------------
    # 指定 collection の pdfs 配下にある shard_id 一覧を返す
    # - PDFが1件以上ある shard のみ返す
    # -------------------------------------------------------------------------
    pdfs_root = Path(archive_root) / str(collection_id) / "pdfs"
    if not pdfs_root.exists():
        return []

    values: list[str] = []

    for shard_dir in sorted(pdfs_root.iterdir()):
        if not shard_dir.is_dir():
            continue

        has_pdf = any(
            p.is_file() and p.suffix.lower() == ".pdf"
            for p in shard_dir.iterdir()
        )
        if has_pdf:
            values.append(shard_dir.name)

    return values


# =============================================================================
# source pdf scan
# =============================================================================
def list_source_pdfs_by_shard(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> list[GenericPdfSourceRecord]:
    # -------------------------------------------------------------------------
    # 指定 collection / shard の原本PDF一覧を返す
    # -------------------------------------------------------------------------
    shard_dir = Path(archive_root) / str(collection_id) / "pdfs" / str(shard_id)
    if not shard_dir.exists():
        return []

    rows: list[GenericPdfSourceRecord] = []

    for pdf_path in sorted(shard_dir.glob("*.pdf")):
        if not pdf_path.is_file():
            continue

        rows.append(
            GenericPdfSourceRecord(
                collection_id=str(collection_id),
                shard_id=str(shard_id),
                doc_id=pdf_path.stem,
                pdf_path=pdf_path,
                pdf_filename=pdf_path.name,
            )
        )

    return rows