# -*- coding: utf-8 -*-
# common_lib/project_master/report_display_status_ops.py
# ============================================================
# Project Master: 報告書表示状態集約オペレーション（正本API）
#
# ■ 目的
# - 一覧表示・プレビュー表示に必要な報告書状態を集約して返す
# - page側に業務判定ロジックを散らさない
#
# ■ 集約対象
# - pdf_kind
# - page_count / 表示用 page_count_display
# - ocr_done
# - lock_flag
# - raw_exists / clean_exists
# - ok_ready
#
# ■ OK条件（正本）
# - text PDF  + raw text あり + lock済み
# - image PDF + clean textあり + lock済み
#
# ■ 重要方針
# - RAG取り込み状態は本モジュールでは扱わない
# - RAG取込済み判定の正本は processed_files.json 側とし、
#   必要なページで別途判定する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass
from pathlib import Path

# ============================================================
# project_master imports
# ============================================================
from common_lib.project_master.processing_status_ops import read_processing_status
from common_lib.project_master.report_text_ops import (
    exists_text_raw,
    exists_text_clean,
)


# ============================================================
# dataclass
# ============================================================
@dataclass(frozen=True)
class ReportDisplayStatus:
    # ------------------------------------------------------------
    # basic
    # ------------------------------------------------------------
    project_year: int
    project_no: str
    pdf_filename: str

    # ------------------------------------------------------------
    # status
    # ------------------------------------------------------------
    pdf_kind: str
    page_count: int | None
    page_count_display: str
    ocr_done: bool

    lock_flag: int

    raw_exists: bool
    clean_exists: bool

    # ------------------------------------------------------------
    # business status
    # ------------------------------------------------------------
    ok_ready: bool


# ============================================================
# internal helpers
# ============================================================
def _pdf_kind_label_from_record(rec) -> str:
    # ------------------------------------------------------------
    # pdf_kind 表示用
    # ------------------------------------------------------------
    v = str(getattr(rec, "pdf_kind", "") or "").strip().lower()
    if v in ("text", "image"):
        return v
    return "未判定"


def _page_count_value_from_record(rec) -> int | None:
    # ------------------------------------------------------------
    # page_count 値
    # ------------------------------------------------------------
    page_count = getattr(rec, "page_count", None)
    try:
        n = int(page_count)
        if n > 0:
            return n
    except Exception:
        pass
    return None


def _page_count_display_from_record(rec) -> str:
    # ------------------------------------------------------------
    # page_count 表示用
    # ------------------------------------------------------------
    n = _page_count_value_from_record(rec)
    if n is None:
        return "未計算"
    return f"{n}p"


def _is_ocr_done_from_record(rec) -> bool:
    # ------------------------------------------------------------
    # OCR済み判定
    # ------------------------------------------------------------
    return bool(getattr(rec, "ocr_done", False))


def _is_ok_ready(
    pdf_kind: str,
    lock_flag: int,
    raw_exists: bool,
    clean_exists: bool,
) -> bool:
    # ------------------------------------------------------------
    # OK条件（正本）
    # ------------------------------------------------------------
    return bool(
        lock_flag == 1 and (
            (pdf_kind == "text" and raw_exists) or
            (pdf_kind == "image" and clean_exists)
        )
    )


# ============================================================
# public api
# ============================================================
def build_report_display_status(
    projects_root: Path,
    item,
    role: str = "main",
) -> ReportDisplayStatus:
    # ------------------------------------------------------------
    # 1件分の報告書表示状態を集約して返す
    # ------------------------------------------------------------
    project_year = int(getattr(item, "project_year"))
    project_no = str(getattr(item, "project_no"))
    pdf_filename = str(getattr(item, "pdf_filename", "") or "")
    lock_flag = int(getattr(item, "pdf_lock_flag", 0) or 0)

    rec = read_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    pdf_kind = _pdf_kind_label_from_record(rec)
    page_count = _page_count_value_from_record(rec)
    page_count_display = _page_count_display_from_record(rec)
    ocr_done = _is_ocr_done_from_record(rec)

    raw_exists = exists_text_raw(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    clean_exists = exists_text_clean(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    ok_ready = _is_ok_ready(
        pdf_kind=pdf_kind,
        lock_flag=lock_flag,
        raw_exists=raw_exists,
        clean_exists=clean_exists,
    )

    return ReportDisplayStatus(
        project_year=project_year,
        project_no=project_no,
        pdf_filename=pdf_filename,
        pdf_kind=pdf_kind,
        page_count=page_count,
        page_count_display=page_count_display,
        ocr_done=ocr_done,
        lock_flag=lock_flag,
        raw_exists=raw_exists,
        clean_exists=clean_exists,
        ok_ready=ok_ready,
    )