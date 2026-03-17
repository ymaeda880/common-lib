# -*- coding: utf-8 -*-
# common_lib/project_master/report_check_ops.py
# ============================================================
# Project Master: 報告書チェック（103ページ用・正本API）
#
# 役割：
# - 1件の報告書PDFについて
#   - source pdf の sha256 計算
#   - text / image 判定
#   - page_count 取得
#   - processing_status.json 更新
#   - text PDF のみ direct extract → text/report_raw.txt 保存
# - 指定年度の全報告書PDFに対して上記を一括実行
#
# 方針：
# - 103_報告書pdfチェック.py の処理本体を common_lib に寄せる
# - OCR はこのモジュールでは行わない
# - clean / RAG もこのモジュールでは行わない
# - pdf/pdf_status.json は登録情報専用のため、本モジュールでは使わない
# - 判定結果の正本は text/processing_status.json
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import datetime as dt

# ============================================================
# imports（common_lib/project_master）
# ============================================================
from common_lib.project_master.paths import (
    normalize_year_4digits,
    normalize_pno_3digits,
    get_project_text_dir,
)
from common_lib.project_master.pdf_status_ops import (
    list_report_pdfs_by_year,
)
from common_lib.project_master.report_pdf_ops import (
    get_report_pdf_path,
)
from common_lib.project_master.processing_status_ops import (
    read_processing_status,
    upsert_pdf_info_status,
    mark_text_extracted,
)

# ============================================================
# imports（common_lib/pdf_tools）
# ============================================================
from common_lib.pdf_tools.text_extract.fitz_guard import (
    try_import_fitz,
)
from common_lib.pdf_tools.text_extract.detect import (
    detect_pdf_kind_from_bytes,
)
from common_lib.pdf_tools.text_extract.extract import (
    extract_text_direct,
)
from common_lib.pdf_tools.text_extract.utils import (
    sha256_bytes,
)
from common_lib.pdf_tools.pages_json import (
    create_raw_pages_json,
    get_report_raw_pages_json_path,
)

# ============================================================
# constants
# ============================================================
REPORT_RAW_TXT_NAME = "report_raw.txt"

ACTION_SKIPPED = "skipped"
ACTION_PROCESSED_TEXT_PDF = "processed_text_pdf"
ACTION_PROCESSED_IMAGE_PDF = "processed_image_pdf"
ACTION_ERROR = "error"


# ============================================================
# result models
# ============================================================
@dataclass(frozen=True)
class ReportCheckItemResult:
    # ------------------------------------------------------------
    # 1件分の結果
    # ------------------------------------------------------------
    project_year: int
    project_no: str
    pdf_filename: str
    source_pdf_sha256: Optional[str]
    action: str
    pdf_kind: Optional[str]
    page_count: Optional[int]
    raw_text_path: Optional[str]
    processing_status_path: Optional[str]
    message: str
    error_message: Optional[str]


@dataclass(frozen=True)
class ReportCheckYearResult:
    # ------------------------------------------------------------
    # 年度一括結果
    # ------------------------------------------------------------
    project_year: int
    total_count: int
    processed_count: int
    skipped_count: int
    error_count: int
    processed_text_count: int
    processed_image_count: int
    results: List[ReportCheckItemResult]
    message: str


# ============================================================
# helpers（fs）
# ============================================================
def _require_existing_dir(*, dir_path: Path, name: str) -> None:
    # ------------------------------------------------------------
    # ディレクトリ存在前提ガード
    # ------------------------------------------------------------
    if not dir_path.exists():
        raise RuntimeError(f"{name} が存在しません（不整合）。 path={dir_path}")
    if not dir_path.is_dir():
        raise RuntimeError(f"{name} がディレクトリではありません（不整合）。 path={dir_path}")


def _atomic_write_text(dst: Path, text: str) -> None:
    # ------------------------------------------------------------
    # atomic text write
    # ------------------------------------------------------------
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(dst)


def _get_report_raw_txt_path(*, text_dir: Path) -> Path:
    # ------------------------------------------------------------
    # raw text 正本パス
    # ------------------------------------------------------------
    return text_dir / REPORT_RAW_TXT_NAME

def _get_report_raw_pages_json_path(
    *,
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # raw pages json 正本パス
    # ------------------------------------------------------------
    return get_report_raw_pages_json_path(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        role=role,
    )

# ============================================================
# helpers（status / skip 判定）
# ============================================================
def _has_valid_page_count(value: object) -> bool:
    # ------------------------------------------------------------
    # page_count が 1以上の整数か
    # ------------------------------------------------------------
    try:
        return int(value) > 0
    except Exception:
        return False


def _is_processed_image_pdf(
    *,
    current_sha256: str,
    rec,
) -> bool:
    # ------------------------------------------------------------
    # image PDF の処理済み判定
    # ------------------------------------------------------------
    saved_sha = str(getattr(rec, "source_pdf_sha256", "") or "").strip()
    pdf_kind = str(getattr(rec, "pdf_kind", "") or "").strip().lower()
    page_count = getattr(rec, "page_count", None)

    return (
        bool(saved_sha)
        and saved_sha == str(current_sha256)
        and pdf_kind == "image"
        and _has_valid_page_count(page_count)
    )

def _is_processed_text_pdf(
    *,
    current_sha256: str,
    rec,
    raw_txt_path: Path,
    raw_pages_json_path: Path,
) -> bool:
    # ------------------------------------------------------------
    # text PDF の処理済み判定
    # ------------------------------------------------------------
    saved_sha = str(getattr(rec, "source_pdf_sha256", "") or "").strip()
    pdf_kind = str(getattr(rec, "pdf_kind", "") or "").strip().lower()
    page_count = getattr(rec, "page_count", None)
    text_extracted = bool(getattr(rec, "text_extracted", False))

    return (
        bool(saved_sha)
        and saved_sha == str(current_sha256)
        and pdf_kind == "text"
        and _has_valid_page_count(page_count)
        and text_extracted
        and raw_txt_path.exists()
        and raw_txt_path.is_file()
        and raw_pages_json_path.exists()
        and raw_pages_json_path.is_file()
    )

# ============================================================
# public（1件チェック）
# ============================================================
def check_one_report_pdf(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
    role: str = "main",
) -> ReportCheckItemResult:
    # ------------------------------------------------------------
    # 1件の報告書PDFをチェックする
    #
    # やること：
    # - sha256 計算
    # - text / image 判定
    # - page_count 取得
    # - processing_status.json 更新
    # - text PDF のみ direct extract → report_raw.txt 保存
    #
    # やらないこと：
    # - OCR
    # - clean
    # - RAG
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    pdf_path = get_report_pdf_path(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    if pdf_path is None or (not pdf_path.exists()):
        raise RuntimeError(f"報告書PDFが存在しません。 year={y} pno={pno3}")

    pdf_filename = str(pdf_path.name)
    pdf_bytes = pdf_path.read_bytes()
    pdf_sha256 = str(sha256_bytes(pdf_bytes))

    text_dir = get_project_text_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    _require_existing_dir(dir_path=text_dir, name="text_dir")

    raw_txt_path = _get_report_raw_txt_path(text_dir=text_dir)

    raw_pages_json_path = _get_report_raw_pages_json_path(
        projects_root=projects_root,
        project_year=int(y),
        project_no=str(pno3),
        role=role,
    )

    rec = read_processing_status(
        projects_root,
        project_year=y,
        project_no=pno3,
    )

    # ------------------------------------------------------------
    # 既処理判定
    # - text PDF / image PDF どちらかで条件を満たせば skip
    # ------------------------------------------------------------
    if _is_processed_text_pdf(
        current_sha256=pdf_sha256,
        rec=rec,
        raw_txt_path=raw_txt_path,
        raw_pages_json_path=raw_pages_json_path,
    ):

        return ReportCheckItemResult(
            project_year=int(y),
            project_no=str(pno3),
            pdf_filename=pdf_filename,
            source_pdf_sha256=pdf_sha256,
            action=ACTION_SKIPPED,
            pdf_kind="text",
            page_count=int(getattr(rec, "page_count", 0) or 0),
            raw_text_path=str(raw_txt_path),
            processing_status_path=str(getattr(rec, "path", "")),
            message="すでに処理済み（text PDF・report_raw.txt / report_raw_pages.json 作成済み）",
            error_message=None,
        )

    if _is_processed_image_pdf(
        current_sha256=pdf_sha256,
        rec=rec,
    ):
        return ReportCheckItemResult(
            project_year=int(y),
            project_no=str(pno3),
            pdf_filename=pdf_filename,
            source_pdf_sha256=pdf_sha256,
            action=ACTION_SKIPPED,
            pdf_kind="image",
            page_count=int(getattr(rec, "page_count", 0) or 0),
            raw_text_path=None,
            processing_status_path=str(getattr(rec, "path", "")),
            message="すでに処理済み（image PDF）",
            error_message=None,
        )

    # ------------------------------------------------------------
    # fitz import
    # ------------------------------------------------------------
    fitz_res = try_import_fitz()
    if (not fitz_res.ok) or (fitz_res.fitz is None):
        raise RuntimeError(f"PyMuPDF（fitz）が利用できません。 import error: {fitz_res.error}")
    fitz = fitz_res.fitz

    # ------------------------------------------------------------
    # PDF種別 / ページ数判定
    # ------------------------------------------------------------
    pdf_kind, page_count = detect_pdf_kind_from_bytes(
        fitz=fitz,
        pdf_bytes=pdf_bytes,
        sample_pages=3,
        min_text_chars=40,
    )

    # ------------------------------------------------------------
    # processing_status.json に pdf基本情報を書き込む
    # ------------------------------------------------------------
    processing_status_path = upsert_pdf_info_status(
        projects_root,
        project_year=y,
        project_no=pno3,
        source_pdf_filename=pdf_filename,
        source_pdf_sha256=pdf_sha256,
        pdf_kind=str(pdf_kind),
        page_count=int(page_count),
        done_by=str(done_by),
    )

    if str(pdf_kind) == "text":
        # ------------------------------------------------------------
        # 全文抽出
        # ------------------------------------------------------------
        raw_text = extract_text_direct(
            fitz=fitz,
            pdf_bytes=pdf_bytes,
            page_start_0=0,
            page_end_0_inclusive=max(0, int(page_count) - 1),
        )

        _atomic_write_text(raw_txt_path, str(raw_text or ""))

        # ------------------------------------------------------------
        # ページ単位抽出
        # - report_raw_pages.json 用
        # ------------------------------------------------------------
        page_texts: List[str] = []

        for page_idx in range(int(page_count)):
            one_page_text = extract_text_direct(
                fitz=fitz,
                pdf_bytes=pdf_bytes,
                page_start_0=int(page_idx),
                page_end_0_inclusive=int(page_idx),
            )
            page_texts.append(str(one_page_text or ""))

        create_raw_pages_json(
            projects_root,
            project_year=int(y),
            project_no=str(pno3),
            pdf_filename=str(pdf_filename),
            source_pdf_sha256=str(pdf_sha256),
            pages_text_list=page_texts,
            role=role,
        )

        mark_text_extracted(
            projects_root,
            project_year=y,
            project_no=pno3,
            done_by=str(done_by),
        )

        return ReportCheckItemResult(
            project_year=int(y),
            project_no=str(pno3),
            pdf_filename=pdf_filename,
            source_pdf_sha256=pdf_sha256,
            action=ACTION_PROCESSED_TEXT_PDF,
            pdf_kind="text",
            page_count=int(page_count),
            raw_text_path=str(raw_txt_path),
            processing_status_path=str(processing_status_path),
            message="text PDF を判定し、page_count取得・text抽出・report_raw_pages.json 作成を実行しました。",
            error_message=None,
        )


    # ------------------------------------------------------------
    # image PDF の場合：ここでは OCR しない
    # ------------------------------------------------------------
    return ReportCheckItemResult(
        project_year=int(y),
        project_no=str(pno3),
        pdf_filename=pdf_filename,
        source_pdf_sha256=pdf_sha256,
        action=ACTION_PROCESSED_IMAGE_PDF,
        pdf_kind="image",
        page_count=int(page_count),
        raw_text_path=None,
        processing_status_path=str(processing_status_path),
        message="image PDF を判定し、page_count取得まで実行しました（OCRは未実施）。",
        error_message=None,
    )


# ============================================================
# public（年度一括チェック）
# ============================================================
def check_report_pdfs_by_year(
    projects_root: Path,
    *,
    project_year: int | str,
    done_by: str,
    role: str = "main",
) -> ReportCheckYearResult:
    # ------------------------------------------------------------
    # 指定年度の全報告書PDFを一括チェックする
    # - 対象は「ロック済み」の報告書PDFのみ
    # - 未ロックは skip として結果に残す
    # - 1件失敗しても次へ進む
    # - 集計結果を返す
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)

    items = list_report_pdfs_by_year(
        projects_root,
        project_year=y,
        role=role,
    )

    results: List[ReportCheckItemResult] = []

    processed_count = 0
    skipped_count = 0
    error_count = 0
    processed_text_count = 0
    processed_image_count = 0

    for item in items:
        # ------------------------------------------------------------
        # ロック済みのみ処理
        # ------------------------------------------------------------
        lock_flag = int(getattr(item, "pdf_lock_flag", 0) or 0)
        if lock_flag != 1:
            one = ReportCheckItemResult(
                project_year=int(item.project_year),
                project_no=str(item.project_no),
                pdf_filename=str(getattr(item, "pdf_filename", "") or ""),
                source_pdf_sha256=None,
                action=ACTION_SKIPPED,
                pdf_kind=None,
                page_count=None,
                raw_text_path=None,
                processing_status_path=None,
                message="ロック未済のため処理対象外としてskipしました。",
                error_message=None,
            )
            results.append(one)
            skipped_count += 1
            continue

        try:
            one = check_one_report_pdf(
                projects_root,
                project_year=int(item.project_year),
                project_no=str(item.project_no),
                done_by=str(done_by),
                role=role,
            )
        except Exception as e:
            one = ReportCheckItemResult(
                project_year=int(item.project_year),
                project_no=str(item.project_no),
                pdf_filename=str(getattr(item, "pdf_filename", "") or ""),
                source_pdf_sha256=None,
                action=ACTION_ERROR,
                pdf_kind=None,
                page_count=None,
                raw_text_path=None,
                processing_status_path=None,
                message="処理中にエラーが発生しました。",
                error_message=str(e),
            )

        results.append(one)

        if one.action == ACTION_SKIPPED:
            skipped_count += 1
        elif one.action == ACTION_PROCESSED_TEXT_PDF:
            processed_count += 1
            processed_text_count += 1
        elif one.action == ACTION_PROCESSED_IMAGE_PDF:
            processed_count += 1
            processed_image_count += 1
        elif one.action == ACTION_ERROR:
            error_count += 1

    total_count = len(items)

    if total_count == 0:
        message = "この年度には報告書PDFがありません。"
    elif skipped_count == total_count:
        message = "この年度のPDFはすべてスキップでした（未ロックまたは処理済み）。"
    else:
        message = (
            f"完了: 全PDF={total_count} / "
            f"今回処理={processed_count} "
            f"(text={processed_text_count}, image={processed_image_count}) / "
            f"スキップ={skipped_count} / "
            f"エラー={error_count}"
        )

    return ReportCheckYearResult(
        project_year=int(y),
        total_count=int(total_count),
        processed_count=int(processed_count),
        skipped_count=int(skipped_count),
        error_count=int(error_count),
        processed_text_count=int(processed_text_count),
        processed_image_count=int(processed_image_count),
        results=results,
        message=message,
    )