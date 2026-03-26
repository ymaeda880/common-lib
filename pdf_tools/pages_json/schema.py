# common_lib/pdf_tools/pages_json/schema.py
# ============================================================
# ページテキストJSONスキーマ
#
# 目的：
# - report_raw_pages.json / report_clean_pages.json の構造を定義する
# - dataclass を正本として JSON 入出力の型を安定させる
#
# 扱う対象：
# - PDF 由来のページ単位テキスト
# - RAG 用ページ正本
#
# 設計方針：
# - project 専用の project_year / project_no は持たない
# - 文書識別は collection_id / shard_id / doc_id で統一する
# - kind は raw / clean をそのまま使う
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ============================================================
# page record
# ============================================================
@dataclass(frozen=True)
class PageTextRecord:
    # ------------------------------------------------------------
    # ページ単位テキスト
    # ------------------------------------------------------------
    page_no: int
    text: str

    # ------------------------------------------------------------
    # JSON化
    # ------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------
    # JSON復元
    # ------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PageTextRecord":
        return cls(
            page_no=int(data.get("page_no")),
            text=str(data.get("text", "") or ""),
        )


# ============================================================
# document pages json
# ============================================================
@dataclass(frozen=True)
class ReportPagesJson:
    # ------------------------------------------------------------
    # document meta
    # ------------------------------------------------------------
    version: int
    kind: str
    collection_id: str
    shard_id: str
    doc_id: str
    pdf_filename: str
    source_pdf_sha256: Optional[str]

    # ------------------------------------------------------------
    # pages
    # ------------------------------------------------------------
    pages: List[PageTextRecord] = field(default_factory=list)

    # ------------------------------------------------------------
    # JSON化
    # ------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": int(self.version),
            "kind": str(self.kind),
            "collection_id": str(self.collection_id),
            "shard_id": str(self.shard_id),
            "doc_id": str(self.doc_id),
            "pdf_filename": str(self.pdf_filename),
            "source_pdf_sha256": (
                str(self.source_pdf_sha256)
                if self.source_pdf_sha256 is not None
                else None
            ),
            "pages": [page.to_dict() for page in self.pages],
        }

    # ------------------------------------------------------------
    # JSON復元
    # ------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportPagesJson":
        pages_raw = data.get("pages", []) or []
        return cls(
            version=int(data.get("version", 1)),
            kind=str(data.get("kind", "") or ""),
            collection_id=str(data.get("collection_id", "") or ""),
            shard_id=str(data.get("shard_id", "") or ""),
            doc_id=str(data.get("doc_id", "") or ""),
            pdf_filename=str(data.get("pdf_filename", "") or ""),
            source_pdf_sha256=(
                str(data.get("source_pdf_sha256"))
                if data.get("source_pdf_sha256") is not None
                else None
            ),
            pages=[PageTextRecord.from_dict(x) for x in pages_raw],
        )