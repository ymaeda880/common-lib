# common_lib/rag_ingest/generic/status_ops.py
# =============================================================================
# RAG ingest : generic（汎用PDF）用 status ops
#
# 役割：
# - 730_汎用DB作成.py の一覧表示に必要な状態判定をまとめる
# - generic PDF 1件について
#   - ingest 可能か
#   - 既に取り込み済みか
#   - row label 表示
#   を構築する
#
# 設計方針：
# - 判定の正本は processing_status.json と processed_files.json
# - collection_id / shard_id / doc_id で識別する
# - page 側で個別ロジックを書かない
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from dataclasses import dataclass
from pathlib import Path

from common_lib.pdf_catalog.processing_status_ops import (
    read_processing_status,
)
from common_lib.rag_ingest.processed_status_ops import (
    get_processed_doc_id_set,
)

from .source_adapter import (
    resolve_generic_pdf_source,
)


# =============================================================================
# row status
# =============================================================================
@dataclass(slots=True)
class GenericRagRowStatus:
    # -------------------------------------------------------------------------
    # 一覧1行の状態
    # -------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    doc_id: str
    pdf_filename: str

    pdf_kind: str
    page_count: int | None

    ocr_done: bool
    text_extracted: bool
    cleaned: bool

    raw_exists: bool
    clean_exists: bool

    source_resolved: bool
    source_text_kind: str

    rag_done: bool
    ok_ready: bool

    message: str

    def to_dict(self) -> dict:
        # ---------------------------------------------------------------------
        # dict 変換
        # ---------------------------------------------------------------------
        return {
            "collection_id": self.collection_id,
            "shard_id": self.shard_id,
            "doc_id": self.doc_id,
            "pdf_filename": self.pdf_filename,
            "pdf_kind": self.pdf_kind,
            "page_count": self.page_count,
            "ocr_done": self.ocr_done,
            "text_extracted": self.text_extracted,
            "cleaned": self.cleaned,
            "raw_exists": self.raw_exists,
            "clean_exists": self.clean_exists,
            "source_resolved": self.source_resolved,
            "source_text_kind": self.source_text_kind,
            "rag_done": self.rag_done,
            "ok_ready": self.ok_ready,
            "message": self.message,
        }


# =============================================================================
# helpers
# =============================================================================
def _normalize_collection_id(value: object) -> str:
    # -------------------------------------------------------------------------
    # collection_id 正規化
    # -------------------------------------------------------------------------
    return str(value or "").strip()


def _normalize_shard_id(value: object) -> str:
    # -------------------------------------------------------------------------
    # shard_id 正規化
    # -------------------------------------------------------------------------
    return str(value or "").strip()


def _normalize_doc_id(value: object) -> str:
    # -------------------------------------------------------------------------
    # doc_id 正規化
    # -------------------------------------------------------------------------
    return str(value or "").strip()


def _normalize_pdf_filename(value: object) -> str:
    # -------------------------------------------------------------------------
    # pdf_filename 正規化
    # -------------------------------------------------------------------------
    return str(value or "").strip()


def _safe_pdf_kind(value: object) -> str:
    # -------------------------------------------------------------------------
    # pdf_kind 表示用
    # -------------------------------------------------------------------------
    s = str(value or "").strip().lower()
    if s in ("text", "image"):
        return s
    return "未判定"


def _safe_page_count(value: object) -> int | None:
    # -------------------------------------------------------------------------
    # page_count 安全変換
    # -------------------------------------------------------------------------
    try:
        n = int(value)
        if n > 0:
            return n
        return None
    except Exception:
        return None


def _page_count_display(page_count: int | None) -> str:
    # -------------------------------------------------------------------------
    # page_count 表示用
    # -------------------------------------------------------------------------
    if page_count is None:
        return "未計算"
    return f"{int(page_count)}p"


def _row_icons(
    *,
    pdf_kind: str,
    ocr_done: bool,
    text_extracted: bool,
    cleaned: bool,
    rag_done: bool,
) -> str:
    # -------------------------------------------------------------------------
    # 一覧用アイコン
    # -------------------------------------------------------------------------
    if pdf_kind == "text":
        pdfkind_icon = "📄"
    elif pdf_kind == "image":
        pdfkind_icon = "🖼️"
    else:
        pdfkind_icon = "❓"

    if pdf_kind == "text":
        ocr_icon = "➖"
    else:
        ocr_icon = "📝" if bool(ocr_done) else "◻️"

    raw_icon = "📃" if bool(text_extracted) else "◻️"
    clean_icon = "✨" if bool(cleaned) else "◻️"
    rag_icon = "🧠" if bool(rag_done) else "◻️"

    return " ".join([pdfkind_icon, ocr_icon, raw_icon, clean_icon, rag_icon])


# =============================================================================
# public（row status）
# =============================================================================
def get_generic_rag_row_status(
    *,
    archive_root: Path,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    pdf_filename: str,
    embed_model: str,
) -> GenericRagRowStatus:
    # -------------------------------------------------------------------------
    # generic PDF 1件の RAG一覧状態を返す
    #
    # 判定方針：
    # - processing_status.json を読む
    # - source_adapter で ingest source を解決
    # - processed_files.json で rag_done を判定
    # - ok_ready は source 解決できるかで判定
    # -------------------------------------------------------------------------
    c = _normalize_collection_id(collection_id)
    s = _normalize_shard_id(shard_id)
    d = _normalize_doc_id(doc_id)
    fn = _normalize_pdf_filename(pdf_filename)

    rec = read_processing_status(
        archive_root,
        collection_id=c,
        shard_id=s,
        doc_id=d,
    )

    pdf_kind = _safe_pdf_kind(rec.pdf_kind)
    page_count = _safe_page_count(rec.page_count)

    source_res = resolve_generic_pdf_source(
        archive_root,
        collection_id=c,
        shard_id=s,
        doc_id=d,
        pdf_filename=fn,
        embed_model=str(embed_model or ""),
    )

    source_resolved = bool(getattr(source_res, "ok", False)) and (getattr(source_res, "source", None) is not None)

    source_text_kind = ""
    rag_done = False

    if source_resolved:
        source = source_res.source
        source_text_kind = str(getattr(source, "source_text_kind", "") or "")

        processed_doc_id_set = get_processed_doc_id_set(
            databases_root,
            collection_id=c,
            shard_id=s,
        )

        source_doc_id = str(getattr(source, "doc_id", "") or "").strip()
        if source_doc_id:
            rag_done = source_doc_id in processed_doc_id_set

    # -------------------------------------------------------------------------
    # ingest 可能条件
    # - source 解決できること
    # -------------------------------------------------------------------------
    ok_ready = bool(source_resolved)

    # -------------------------------------------------------------------------
    # message
    # -------------------------------------------------------------------------
    if pdf_kind == "未判定":
        message = "pdf_kind が未判定です。先にPDF解析/OCRを実行してください。"
    elif not source_resolved:
        message = "取り込み元テキストが未整備です。raw/clean と processing_status を確認してください。"
    elif rag_done:
        message = "RAG取り込み済みです。"
    else:
        message = "取り込み可能です。"

    return GenericRagRowStatus(
        collection_id=c,
        shard_id=s,
        doc_id=d,
        pdf_filename=fn,
        pdf_kind=pdf_kind,
        page_count=page_count,
        ocr_done=bool(rec.ocr_done),
        text_extracted=bool(rec.text_extracted),
        cleaned=bool(rec.cleaned),
        raw_exists=bool(rec.text_extracted),
        clean_exists=bool(rec.cleaned),
        source_resolved=bool(source_resolved),
        source_text_kind=str(source_text_kind or ""),
        rag_done=bool(rag_done),
        ok_ready=bool(ok_ready),
        message=str(message),
    )


# =============================================================================
# public（row label）
# =============================================================================
def build_generic_rag_row_label(
    *,
    status: GenericRagRowStatus,
) -> str:
    # -------------------------------------------------------------------------
    # 一覧表示用ラベルを返す
    # -------------------------------------------------------------------------
    icons = _row_icons(
        pdf_kind=str(status.pdf_kind),
        ocr_done=bool(status.ocr_done),
        text_extracted=bool(status.text_extracted),
        cleaned=bool(status.cleaned),
        rag_done=bool(status.rag_done),
    )

    page_disp = _page_count_display(status.page_count)

    return (
        f"{icons} | "
        f"{status.shard_id} | "
        f"{status.doc_id} | "
        f"{page_disp} | "
        f"{status.pdf_filename}"
    )