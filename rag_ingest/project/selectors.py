# common_lib/rag_ingest/project/selectors.py
# =============================================================================
# RAG ingest : project（報告書）用 selectors
#
# 役割：
# - 160_報告書DB作成.py から使う project 用の一覧取得入口をまとめる
# - 年度一覧取得
# - 年度内の報告書PDF一覧取得
# - 一覧 item から RAG 用の表示情報へ変換しやすい形を返す
#
# 設計方針：
# - page 側から common_lib.project_master の関数を直接たくさん呼ばない
# - project RAG 用の一覧取得入口を本ファイルに寄せる
# - 既存の project_master 正本 API を利用する
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from common_lib.project_master import (
    list_report_pdfs_by_year,
    list_years_with_report_pdf,
)

from .status_ops import (
    ProjectRagRowStatus,
    build_project_rag_row_label,
    get_project_rag_row_status,
)


# =============================================================================
# row view model
# =============================================================================
@dataclass(slots=True)
class ProjectRagSelectableItem:
    # -----------------------------------------------------------------------------
    # 160ページの一覧表示と選択に使う view model
    #
    # raw item（project_master の一覧 item）に依存しすぎないように、
    # page 側で必要になる情報をここへまとめる。
    # -----------------------------------------------------------------------------
    project_year: int
    project_no: str
    pdf_filename: str
    pdf_lock_flag: int

    row_status: ProjectRagRowStatus
    row_label: str

    def to_dict(self) -> dict:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return {
            "project_year": self.project_year,
            "project_no": self.project_no,
            "pdf_filename": self.pdf_filename,
            "pdf_lock_flag": self.pdf_lock_flag,
            "row_status": self.row_status.to_dict(),
            "row_label": self.row_label,
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


def _safe_pdf_filename(item) -> str:
    # -----------------------------------------------------------------------------
    # item から pdf_filename を取得
    # -----------------------------------------------------------------------------
    return str(getattr(item, "pdf_filename", "") or "").strip()


def _safe_pdf_lock_flag(item) -> int:
    # -----------------------------------------------------------------------------
    # item から pdf_lock_flag を取得
    # -----------------------------------------------------------------------------
    try:
        return int(getattr(item, "pdf_lock_flag", 0) or 0)
    except Exception:
        return 0


# =============================================================================
# 年度一覧
# =============================================================================
def list_project_rag_years(
    projects_root: Path,
) -> list[int]:
    # -----------------------------------------------------------------------------
    # 報告書PDFが存在する年度一覧を返す
    #
    # 既存 project_master 正本 API を利用する。
    # -----------------------------------------------------------------------------
    years = list_years_with_report_pdf(projects_root)

    # 念のため int 化して整える
    out: list[int] = []
    for y in years:
        try:
            out.append(int(y))
        except Exception:
            continue

    return out


# =============================================================================
# raw items 一覧
# =============================================================================
def list_project_rag_raw_items_by_year(
    projects_root: Path,
    *,
    project_year: int,
    role: str = "main",
):
    # -----------------------------------------------------------------------------
    # 年度内の報告書PDF raw items を返す
    #
    # 戻り値は project_master 側の item オブジェクト列のまま。
    # 必要なら page 側ではなく build_project_rag_selectable_items_by_year()
    # を使う。
    # -----------------------------------------------------------------------------
    return list_report_pdfs_by_year(
        projects_root,
        project_year=int(project_year),
        role=str(role),
    )


# =============================================================================
# selectable items 一覧
# =============================================================================
def build_project_rag_selectable_items_by_year(
    projects_root: Path,
    databases_root: Path,
    *,
    project_year: int,
    embed_model: str,
    role: str = "main",
) -> list[ProjectRagSelectableItem]:
    # -----------------------------------------------------------------------------
    # 年度内の報告書一覧を、160ページ用 selectable item に変換して返す
    #
    # 各 item について
    # - row_status
    # - row_label
    # を組み立てる
    # -----------------------------------------------------------------------------
    raw_items = list_project_rag_raw_items_by_year(
        projects_root,
        project_year=int(project_year),
        role=str(role),
    )

    out: list[ProjectRagSelectableItem] = []

    for item in raw_items:
        year = int(getattr(item, "project_year"))
        pno = _normalize_pno(getattr(item, "project_no"))
        fn = _safe_pdf_filename(item)
        lock_flag = _safe_pdf_lock_flag(item)

        row_status = get_project_rag_row_status(
            projects_root=projects_root,
            databases_root=databases_root,
            project_year=year,
            project_no=pno,
            pdf_filename=fn,
            embed_model=embed_model,
            pdf_lock_flag=lock_flag,
        )

        row_label = build_project_rag_row_label(
            status=row_status,
        )

        out.append(
            ProjectRagSelectableItem(
                project_year=year,
                project_no=pno,
                pdf_filename=fn,
                pdf_lock_flag=lock_flag,
                row_status=row_status,
                row_label=row_label,
            )
        )

    return out


# =============================================================================
# 単一 item 取得
# =============================================================================
def find_project_rag_selectable_item(
    items: list[ProjectRagSelectableItem],
    *,
    project_year: int,
    project_no: str,
    pdf_filename: str,
) -> Optional[ProjectRagSelectableItem]:
    # -----------------------------------------------------------------------------
    # selectable items から1件検索する
    # -----------------------------------------------------------------------------
    y = int(project_year)
    p = _normalize_pno(project_no)
    fn = str(pdf_filename or "").strip()

    for item in items:
        if (
            int(item.project_year) == y
            and str(item.project_no) == p
            and str(item.pdf_filename) == fn
        ):
            return item

    return None


# =============================================================================
# selection helper
# =============================================================================
def selected_items_from_keys(
    items: list[ProjectRagSelectableItem],
    *,
    selected_keys: set[str],
) -> list[ProjectRagSelectableItem]:
    # -----------------------------------------------------------------------------
    # key 集合から選択 item 一覧を返す
    #
    # key format:
    #   "<year>__<pno>__<pdf_filename>"
    # -----------------------------------------------------------------------------
    out: list[ProjectRagSelectableItem] = []

    for item in items:
        key = build_project_rag_item_key(
            project_year=item.project_year,
            project_no=item.project_no,
            pdf_filename=item.pdf_filename,
        )
        if key in selected_keys:
            out.append(item)

    return out


def build_project_rag_item_key(
    *,
    project_year: int,
    project_no: str,
    pdf_filename: str,
) -> str:
    # -----------------------------------------------------------------------------
    # page の checkbox key / 選択管理用 key を作る
    # -----------------------------------------------------------------------------
    y = int(project_year)
    p = _normalize_pno(project_no)
    fn = str(pdf_filename or "").strip()
    return f"{y}__{p}__{fn}"


# =============================================================================
# paging helper
# =============================================================================
def slice_items_for_page(
    items: list[ProjectRagSelectableItem],
    *,
    current_page: int,
    page_size: int,
) -> list[ProjectRagSelectableItem]:
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