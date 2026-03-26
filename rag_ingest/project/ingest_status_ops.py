# common_lib/rag_ingest/project/ingest_status_ops.py
# =============================================================================
# RAG ingest : project（報告書）用 取込状態判定
#
# 役割：
# - project 報告書1件について、RAG取込済みかを判定する
# - 正本は Databases/vectorstore/<collection_id>/<shard_id>/processed_files.json
# - page 側に doc_id 解決 + processed_files.json 照合ロジックを散らさない
#
# 設計方針：
# - collection_id は project 固定
# - shard_id は year
# - doc_id は source_adapter.py の正本ロジックで解決する
# - source 解決不可のときは False を返す
# - 例外は原則握らず、上位で扱えるようにする
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from pathlib import Path
from typing import Optional

from common_lib.project_master.models import Project

from ..processed_status_ops import get_processed_doc_id_set
from .source_adapter import resolve_project_report_source


# =============================================================================
# constants
# =============================================================================
COLLECTION_ID = "project"


# =============================================================================
# helpers
# =============================================================================
def _safe_report_pdf_filename(project: Optional[Project]) -> str:
    # -------------------------------------------------------------------------
    # Project から報告書PDFファイル名を安全に取り出す
    # -------------------------------------------------------------------------
    if project is None:
        return ""

    return str(getattr(project, "report_pdf_original_filename", "") or "").strip()


def _safe_pdf_lock_flag(project: Optional[Project]) -> int:
    # -------------------------------------------------------------------------
    # Project から pdf_lock_flag を安全に取り出す
    # -------------------------------------------------------------------------
    if project is None:
        return 0

    try:
        return int(getattr(project, "pdf_lock_flag", 0) or 0)
    except Exception:
        return 0


# =============================================================================
# public
# =============================================================================
def get_project_processed_doc_id_set(
    databases_root: Path,
    *,
    project_year: int,
) -> set[str]:
    # -------------------------------------------------------------------------
    # project collection / 年度shard の processed doc_id 集合を返す
    # -------------------------------------------------------------------------
    return get_processed_doc_id_set(
        databases_root,
        collection_id=COLLECTION_ID,
        shard_id=str(int(project_year)),
    )


def resolve_project_report_doc_id(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    pdf_filename: str,
    pdf_lock_flag: int = 0,
) -> Optional[str]:
    # -------------------------------------------------------------------------
    # project 報告書1件の doc_id を解決する
    #
    # 戻り値：
    # - 解決成功: doc_id
    # - 解決失敗: None
    # -------------------------------------------------------------------------
    src_res = resolve_project_report_source(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        pdf_filename=str(pdf_filename),
        embed_model="",
        pdf_lock_flag=int(pdf_lock_flag or 0),
    )

    if (not src_res.ok) or (src_res.source is None):
        return None

    doc_id = str(src_res.source.doc_id or "").strip()
    if not doc_id:
        return None

    return doc_id


def is_project_report_ingested(
    projects_root: Path,
    databases_root: Path,
    *,
    project_year: int,
    project_no: str,
    pdf_filename: str,
    pdf_lock_flag: int = 0,
) -> bool:
    # -------------------------------------------------------------------------
    # project 報告書1件が RAG取込済みかを返す
    #
    # 判定ロジック：
    # 1. source_adapter 正本で doc_id を解決
    # 2. processed_files.json の doc_id 集合に存在するかを見る
    # -------------------------------------------------------------------------
    doc_id = resolve_project_report_doc_id(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        pdf_filename=str(pdf_filename),
        pdf_lock_flag=int(pdf_lock_flag or 0),
    )

    if not doc_id:
        return False

    processed_doc_id_set = get_project_processed_doc_id_set(
        databases_root,
        project_year=int(project_year),
    )

    return doc_id in processed_doc_id_set


def is_project_ingested(
    projects_root: Path,
    databases_root: Path,
    *,
    project: Optional[Project],
    project_year: int,
    project_no: str,
) -> bool:
    # -------------------------------------------------------------------------
    # Project オブジェクトに対応する報告書が RAG取込済みかを返す
    #
    # 用途：
    # - project_hub_app/pages/120_プロジェクト管理.py
    # - project_hub_app/pages/125_報告書管理.py
    # など、Project を既に持っている画面用
    # -------------------------------------------------------------------------
    if project is None:
        return False

    pdf_filename = _safe_report_pdf_filename(project)
    if not pdf_filename:
        return False

    pdf_lock_flag = _safe_pdf_lock_flag(project)

    return is_project_report_ingested(
        projects_root,
        databases_root,
        project_year=int(project_year),
        project_no=str(project_no),
        pdf_filename=pdf_filename,
        pdf_lock_flag=pdf_lock_flag,
    )