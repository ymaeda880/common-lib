# common_lib/rag_ingest/project/status_ops.py
# =============================================================================
# RAG ingest : project（報告書）用 一覧状態判定
#
# 役割：
# - 160_報告書DB作成.py の一覧表示に必要な状態をまとめて返す
# - 報告書1件について
#     - pdf_kind
#     - lock状態
#     - OCR済みか
#     - RAG取込済みか
#     - source 解決可否
#     - source_text_kind
#     - source_text_path
#     - source_pdf_path
#     - skip理由
#   を判定する
#
# 設計方針：
# - 一覧UIのための判定を page 側に置かない
# - source の正本解決は source_adapter.py に寄せる
# - processed 済み判定は vectorstore_io.py を使う
# - 報告書固有の attrs（year / pno / ocr）は source_adapter 側で組み立てる
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from common_lib.project_master import read_processing_status

from ..vectorstore_io import get_processed_record
from .source_adapter import resolve_project_report_source


# =============================================================================
# row status
# =============================================================================
@dataclass(slots=True)
class ProjectRagRowStatus:
    # -----------------------------------------------------------------------------
    # 160ページの一覧1行に対応する状態
    # -----------------------------------------------------------------------------
    project_year: int
    project_no: str
    pdf_filename: str

    pdf_kind: str
    page_count_display: str

    locked: bool
    ocr_done: bool

    rag_done: bool
    rag_embed_model: Optional[str]

    source_ok: bool
    source_message: str

    source_text_kind: Optional[str] = None
    source_text_path: Optional[str] = None
    source_pdf_path: Optional[str] = None
    sha256: Optional[str] = None

    doc_id: Optional[str] = None
    shard_id: Optional[str] = None

    def to_dict(self) -> dict:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return {
            "project_year": self.project_year,
            "project_no": self.project_no,
            "pdf_filename": self.pdf_filename,
            "pdf_kind": self.pdf_kind,
            "page_count_display": self.page_count_display,
            "locked": self.locked,
            "ocr_done": self.ocr_done,
            "rag_done": self.rag_done,
            "rag_embed_model": self.rag_embed_model,
            "source_ok": self.source_ok,
            "source_message": self.source_message,
            "source_text_kind": self.source_text_kind,
            "source_text_path": self.source_text_path,
            "source_pdf_path": self.source_pdf_path,
            "sha256": self.sha256,
            "doc_id": self.doc_id,
            "shard_id": self.shard_id,
        }


# =============================================================================
# helper
# =============================================================================
def _normalize_pno(project_no: object) -> str:
    # -----------------------------------------------------------------------------
    # pno を 3桁ゼロ埋め
    # -----------------------------------------------------------------------------
    s = str(project_no or "").strip()
    if not s:
        return ""
    return s.zfill(3)


def _pdf_kind_label(rec) -> str:
    # -----------------------------------------------------------------------------
    # processing_status から pdf_kind を表示用に正規化
    # -----------------------------------------------------------------------------
    v = str(getattr(rec, "pdf_kind", "") or "").strip().lower()
    if v in ("text", "image"):
        return v
    return "未判定"


def _page_count_display(rec) -> str:
    # -----------------------------------------------------------------------------
    # processing_status から page_count 表示を作る
    # -----------------------------------------------------------------------------
    page_count = getattr(rec, "page_count", None)

    try:
        n = int(page_count)
        if n > 0:
            return f"{n}p"
    except Exception:
        pass

    return "未計算"


def _ocr_done_flag(rec) -> bool:
    # -----------------------------------------------------------------------------
    # processing_status から OCR済み判定
    # -----------------------------------------------------------------------------
    return bool(getattr(rec, "ocr_done", False))


def _build_source_message_for_ui(
    *,
    source_ok: bool,
    source_message: str,
    rag_done: bool,
) -> str:
    # -----------------------------------------------------------------------------
    # 一覧表示向けの source / rag 状態メッセージ
    # -----------------------------------------------------------------------------
    msg = str(source_message or "").strip()

    if source_ok and rag_done:
        return "取込済み"

    if source_ok and not rag_done:
        return "取込可能"

    return msg or "取込不可"


# =============================================================================
# icons / label
# =============================================================================
def build_project_rag_row_icons(
    *,
    pdf_kind: str,
    locked: bool,
    ocr_done: bool,
    rag_done: bool,
) -> str:
    # -----------------------------------------------------------------------------
    # 一覧用アイコン列
    #
    # ルール：
    # - pdf_kind
    #     text  -> 📄
    #     image -> 🖼️
    #     else  -> ❓
    #
    # - lock
    #     True  -> 🔐
    #     False -> ◻️
    #
    # - ocr
    #     text PDF は OCR不要なので ➖
    #     image PDF は done / 未done を表示
    #
    # - rag
    #     done  -> 🧠
    #     未done -> ◻️
    # -----------------------------------------------------------------------------
    if pdf_kind == "text":
        pdf_icon = "📄"
    elif pdf_kind == "image":
        pdf_icon = "🖼️"
    else:
        pdf_icon = "❓"

    lock_icon = "🔐" if locked else "◻️"

    if pdf_kind == "text":
        ocr_icon = "➖"
    else:
        ocr_icon = "📝" if ocr_done else "◻️"

    rag_icon = "🧠" if rag_done else "◻️"

    return " ".join([pdf_icon, lock_icon, ocr_icon, rag_icon])


def build_project_rag_row_label(
    *,
    status: ProjectRagRowStatus,
) -> str:
    # -----------------------------------------------------------------------------
    # checkbox 一覧表示用ラベル
    # -----------------------------------------------------------------------------
    icons = build_project_rag_row_icons(
        pdf_kind=status.pdf_kind,
        locked=status.locked,
        ocr_done=status.ocr_done,
        rag_done=status.rag_done,
    )

    msg = _build_source_message_for_ui(
        source_ok=status.source_ok,
        source_message=status.source_message,
        rag_done=status.rag_done,
    )

    return (
        f"{icons} | "
        f"{status.project_year}-{status.project_no} | "
        f"{status.page_count_display} | "
        f"{status.pdf_filename} | "
        f"{msg}"
    )


# =============================================================================
# main
# =============================================================================
def get_project_rag_row_status(
    projects_root: Path,
    databases_root: Path,
    *,
    project_year: int,
    project_no: str,
    pdf_filename: str,
    embed_model: str,
    pdf_lock_flag: int = 0,
) -> ProjectRagRowStatus:
    # -----------------------------------------------------------------------------
    # 報告書1件の一覧表示用状態を返す
    #
    # flow:
    # 1. processing_status を読む
    # 2. source_adapter で source 解決
    # 3. source が解決できたら processed 判定を行う
    # -----------------------------------------------------------------------------
    year = int(project_year)
    pno = _normalize_pno(project_no)
    fn = str(pdf_filename or "").strip()

    rec = read_processing_status(
        projects_root,
        project_year=year,
        project_no=pno,
    )

    pdf_kind = _pdf_kind_label(rec)
    page_count_disp = _page_count_display(rec)
    ocr_done = _ocr_done_flag(rec)
    locked = int(pdf_lock_flag or 0) == 1

    # -------------------------------------------------------------------------
    # source 解決
    # -------------------------------------------------------------------------
    src_res = resolve_project_report_source(
        projects_root,
        project_year=year,
        project_no=pno,
        pdf_filename=fn,
        embed_model=embed_model,
        pdf_lock_flag=int(pdf_lock_flag or 0),
    )

    rag_done = False
    rag_embed_model: Optional[str] = None
    doc_id: Optional[str] = None
    shard_id: Optional[str] = None

    if src_res.ok and src_res.source is not None:
        doc_id = str(src_res.source.doc_id)
        shard_id = str(src_res.source.shard_id)

        processed = get_processed_record(
            databases_root=databases_root,
            collection_id=str(src_res.source.collection_id),
            shard_id=str(src_res.source.shard_id),
            doc_id=str(src_res.source.doc_id),
        )

        if processed is not None:
            rag_done = True
            rag_embed_model = str(processed.embed_model or "") or None

    return ProjectRagRowStatus(
        project_year=year,
        project_no=pno,
        pdf_filename=fn,
        pdf_kind=pdf_kind,
        page_count_display=page_count_disp,
        locked=locked,
        ocr_done=ocr_done,
        rag_done=rag_done,
        rag_embed_model=rag_embed_model,
        source_ok=bool(src_res.ok),
        source_message=str(src_res.message or ""),
        source_text_kind=src_res.source_text_kind,
        source_text_path=src_res.source_text_path,
        source_pdf_path=src_res.source_pdf_path,
        sha256=src_res.sha256,
        doc_id=doc_id,
        shard_id=shard_id,
    )