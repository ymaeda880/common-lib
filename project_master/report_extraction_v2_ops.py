# -*- coding: utf-8 -*-
# common_lib/project_master/report_extraction_v2_ops.py
# ============================================================
# 報告書テキスト抽出 v2（103専用）
#
# 機能：
# - PDF総ページ数を取得する
# - 全ページを1ページずつ直接テキスト抽出する
# - 20文字以下をimage頁，21文字以上をtext頁と判定する
# - text / image ページ数を集計する
# - PDF全体を text / image / mixed に分類する
# - report_pages.json を作成する
# - processing_status.json を更新する
#
# 再抽出：
# - replace_extracted=True の場合
#   対象報告書の text フォルダ内を全削除してから再処理する
#
# 方針：
# - OCRは行わない
# - cleanは行わない
# - report_raw.txt / report_raw_pages.json は作らない
# - 既存 report_check_ops.py は変更しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any, Callable

# ============================================================
# common_lib
# ============================================================

from common_lib.project_master.paths import (
    get_project_text_dir,
    normalize_pno_3digits,
    normalize_year_4digits,
)

from common_lib.project_master.pdf_status_ops import (
    list_report_pdfs_by_year,
)

from common_lib.project_master.report_pdf_ops import (
    get_report_pdf_path,
)

from common_lib.project_master.processing_status_ops import (
    mark_text_extracted,
    read_processing_status,
    upsert_pdf_info_status,
)

from common_lib.project_master.report_pages_v2_ops import (
    PAGE_KIND_IMAGE,
    PAGE_KIND_TEXT,
    get_report_pages_path,
    write_report_pages,
)

from common_lib.pdf_tools.text_extract.fitz_guard import (
    try_import_fitz,
)

from common_lib.pdf_tools.text_extract.utils import (
    sha256_bytes,
)


# ============================================================
# constants
# ============================================================

IMAGE_PAGE_MAX_TEXT_CHARS = 20

ACTION_PROCESSED = "processed"
ACTION_REPLACED = "replaced"
ACTION_SKIPPED = "skipped"
ACTION_ERROR = "error"


# ============================================================
# callback
# ============================================================

ProgressCallback = Callable[
    [dict[str, Any]],
    None,
]


# ============================================================
# result
# ============================================================

@dataclass(frozen=True)
class ReportExtractionV2ItemResult:
    project_year: int
    project_no: str
    pdf_filename: str

    action: str

    pdf_kind: str | None
    page_count: int

    text_page_count: int
    image_page_count: int

    report_pages_path: str | None
    processing_status_path: str | None

    message: str
    error_message: str | None


@dataclass(frozen=True)
class ReportExtractionV2YearResult:
    project_year: int

    total_count: int

    processed_count: int
    replaced_count: int
    skipped_count: int
    error_count: int

    text_pdf_count: int
    image_pdf_count: int
    mixed_pdf_count: int

    results: tuple[
        ReportExtractionV2ItemResult,
        ...,
    ]


# ============================================================
# helpers（text dir）
# ============================================================

def _get_text_dir(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> Path:
    year = normalize_year_4digits(
        project_year
    )

    pno3 = normalize_pno_3digits(
        project_no
    )

    return get_project_text_dir(
        projects_root,
        project_year=year,
        project_no=pno3,
    )


def _clear_text_dir(
    text_dir: Path,
) -> None:
    # ------------------------------------------------------------
    # textフォルダ自体は残し，中身をすべて削除する
    # ------------------------------------------------------------
    text_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for child in text_dir.iterdir():

        if child.is_dir():
            shutil.rmtree(
                child
            )

        else:
            child.unlink()


# ============================================================
# helpers（処理済み判定）
# ============================================================

def _is_v2_extracted(
    *,
    current_pdf_sha256: str,
    processing_status: Any,
    report_pages_path: Path,
) -> bool:
    saved_sha256 = str(
        getattr(
            processing_status,
            "source_pdf_sha256",
            "",
        )
        or ""
    ).strip()

    pdf_kind = str(
        getattr(
            processing_status,
            "pdf_kind",
            "",
        )
        or ""
    ).strip().lower()

    page_count = int(
        getattr(
            processing_status,
            "page_count",
            0,
        )
        or 0
    )

    text_extracted = bool(
        getattr(
            processing_status,
            "text_extracted",
            False,
        )
    )

    return bool(
        saved_sha256
        == str(
            current_pdf_sha256
        )
        and pdf_kind
        in {
            "text",
            "image",
            "mixed",
        }
        and page_count > 0
        and text_extracted
        and report_pages_path.exists()
        and report_pages_path.is_file()
    )


# ============================================================
# helpers（PDF直接抽出）
# ============================================================

def _extract_all_pages(
    *,
    pdf_bytes: bytes,
) -> tuple[
    list[dict[str, Any]],
    int,
]:
    # ------------------------------------------------------------
    # PDFを1回開き，全ページを順番に直接抽出する
    # ------------------------------------------------------------
    fitz_result = try_import_fitz()

    if (
        not fitz_result.ok
        or fitz_result.fitz is None
    ):
        raise RuntimeError(
            "PyMuPDF（fitz）を利用できません．"
            f" error={fitz_result.error}"
        )

    fitz = fitz_result.fitz

    doc = fitz.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    try:
        if getattr(
            doc,
            "is_encrypted",
            False,
        ):
            raise RuntimeError(
                "PDFが暗号化されています．"
            )

        page_count = int(
            getattr(
                doc,
                "page_count",
                0,
            )
            or 0
        )

        if page_count <= 0:
            raise RuntimeError(
                "PDFページ数を取得できませんでした．"
            )

        pages: list[
            dict[str, Any]
        ] = []

        for page_index in range(
            page_count
        ):
            page = doc.load_page(
                page_index
            )

            direct_text = str(
                page.get_text(
                    "text"
                )
                or ""
            )

            direct_char_count = len(
                direct_text.strip()
            )

            # ----------------------------------------------------
            # 21文字以上：text
            # ----------------------------------------------------
            if (
                direct_char_count
                > IMAGE_PAGE_MAX_TEXT_CHARS
            ):
                page_kind = (
                    PAGE_KIND_TEXT
                )

                original_text = (
                    direct_text
                )

                current_text = (
                    direct_text
                )

            # ----------------------------------------------------
            # 20文字以下：image
            #
            # 103ではOCRしないのでテキストは空
            # direct_char_countだけ残す
            # ----------------------------------------------------
            else:
                page_kind = (
                    PAGE_KIND_IMAGE
                )

                original_text = ""

                current_text = ""

            pages.append(
                {
                    "page_no": (
                        page_index + 1
                    ),
                    "page_kind": (
                        page_kind
                    ),
                    "direct_char_count": (
                        direct_char_count
                    ),
                    "original_text": (
                        original_text
                    ),
                    "text": (
                        current_text
                    ),
                }
            )

        return (
            pages,
            page_count,
        )

    finally:
        doc.close()


# ============================================================
# public（1件）
# ============================================================

def extract_one_report_v2(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
    role: str = "main",
    replace_extracted: bool = False,
) -> ReportExtractionV2ItemResult:
    # ------------------------------------------------------------
    # normalize
    # ------------------------------------------------------------
    year = normalize_year_4digits(
        project_year
    )

    pno3 = normalize_pno_3digits(
        project_no
    )

    # ------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------
    pdf_path = get_report_pdf_path(
        projects_root,
        project_year=year,
        project_no=pno3,
        role=role,
    )

    if (
        pdf_path is None
        or not pdf_path.exists()
        or not pdf_path.is_file()
    ):
        raise RuntimeError(
            "報告書PDFが存在しません．"
            f" {year}-{pno3}"
        )

    pdf_bytes = pdf_path.read_bytes()

    pdf_sha256 = sha256_bytes(
        pdf_bytes
    )

    # ------------------------------------------------------------
    # path
    # ------------------------------------------------------------
    text_dir = _get_text_dir(
        projects_root,
        project_year=year,
        project_no=pno3,
    )

    report_pages_path = (
        get_report_pages_path(
            projects_root,
            project_year=year,
            project_no=pno3,
        )
    )

    # ------------------------------------------------------------
    # 既存状態
    # ------------------------------------------------------------
    current_status = (
        read_processing_status(
            projects_root,
            project_year=year,
            project_no=pno3,
        )
    )

    already_extracted = (
        _is_v2_extracted(
            current_pdf_sha256=(
                pdf_sha256
            ),
            processing_status=(
                current_status
            ),
            report_pages_path=(
                report_pages_path
            ),
        )
    )

    # ------------------------------------------------------------
    # 再抽出OFF
    # ------------------------------------------------------------
    if (
        already_extracted
        and not replace_extracted
    ):
        return ReportExtractionV2ItemResult(
            project_year=int(
                year
            ),
            project_no=str(
                pno3
            ),
            pdf_filename=(
                pdf_path.name
            ),
            action=ACTION_SKIPPED,
            pdf_kind=str(
                current_status.pdf_kind
                or ""
            ),
            page_count=int(
                current_status.page_count
                or 0
            ),
            text_page_count=0,
            image_page_count=0,
            report_pages_path=str(
                report_pages_path
            ),
            processing_status_path=str(
                current_status.path
            ),
            message=(
                "新方式で抽出済みのため"
                "スキップしました．"
            ),
            error_message=None,
        )

    # ------------------------------------------------------------
    # 再抽出ON
    #
    # text内をすべて削除
    # ------------------------------------------------------------
    if replace_extracted:
        _clear_text_dir(
            text_dir
        )

    else:
        text_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ------------------------------------------------------------
    # 全ページ直接抽出
    # ------------------------------------------------------------
    pages, page_count = (
        _extract_all_pages(
            pdf_bytes=pdf_bytes
        )
    )

    # ------------------------------------------------------------
    # report_pages.json
    # ------------------------------------------------------------
    (
        saved_report_pages_path,
        report_payload,
    ) = write_report_pages(
        projects_root,
        project_year=year,
        project_no=pno3,
        pdf_filename=(
            pdf_path.name
        ),
        source_pdf_sha256=(
            pdf_sha256
        ),
        pages=pages,
    )

    pdf_kind = str(
        report_payload[
            "pdf_kind"
        ]
    )

    text_page_count = int(
        report_payload[
            "text_page_count"
        ]
    )

    image_page_count = int(
        report_payload[
            "image_page_count"
        ]
    )

    # ------------------------------------------------------------
    # processing_status.json
    #
    # 既存APIをそのまま利用する
    # ------------------------------------------------------------
    processing_status_path = (
        upsert_pdf_info_status(
            projects_root,
            project_year=year,
            project_no=pno3,
            source_pdf_filename=(
                pdf_path.name
            ),
            source_pdf_sha256=(
                pdf_sha256
            ),
            pdf_kind=pdf_kind,
            page_count=page_count,
            done_by=str(
                done_by
            ),
        )
    )

    mark_text_extracted(
        projects_root,
        project_year=year,
        project_no=pno3,
        done_by=str(
            done_by
        ),
    )

    # ------------------------------------------------------------
    # result
    # ------------------------------------------------------------
    action = (
        ACTION_REPLACED
        if replace_extracted
        else ACTION_PROCESSED
    )

    return ReportExtractionV2ItemResult(
        project_year=int(
            year
        ),
        project_no=str(
            pno3
        ),
        pdf_filename=(
            pdf_path.name
        ),
        action=action,
        pdf_kind=pdf_kind,
        page_count=page_count,
        text_page_count=(
            text_page_count
        ),
        image_page_count=(
            image_page_count
        ),
        report_pages_path=str(
            saved_report_pages_path
        ),
        processing_status_path=str(
            processing_status_path
        ),
        message=(
            f"PDF種別={pdf_kind} ／ "
            f"総頁={page_count} ／ "
            f"text頁={text_page_count} ／ "
            f"image頁={image_page_count}"
        ),
        error_message=None,
    )


# ============================================================
# public（年度一括）
# ============================================================

def extract_reports_by_year_v2(
    projects_root: Path,
    *,
    project_year: int | str,
    done_by: str,
    role: str = "main",
    replace_extracted: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> ReportExtractionV2YearResult:
    # ------------------------------------------------------------
    # 年度内報告書一覧
    # ------------------------------------------------------------
    year = normalize_year_4digits(
        project_year
    )

    items = list_report_pdfs_by_year(
        projects_root,
        project_year=year,
    )

    total_count = len(
        items
    )

    results: list[
        ReportExtractionV2ItemResult
    ] = []

    processed_count = 0
    replaced_count = 0
    skipped_count = 0
    error_count = 0

    text_pdf_count = 0
    image_pdf_count = 0
    mixed_pdf_count = 0

    # ------------------------------------------------------------
    # loop
    # ------------------------------------------------------------
    for index, item in enumerate(
        items,
        start=1,
    ):
        if progress_callback is not None:
            progress_callback(
                {
                    "current": index,
                    "total": total_count,
                    "project_year": (
                        item.project_year
                    ),
                    "project_no": (
                        item.project_no
                    ),
                    "pdf_filename": str(
                        getattr(
                            item,
                            "pdf_filename",
                            "",
                        )
                        or ""
                    ),
                }
            )

        lock_flag = int(
            getattr(
                item,
                "pdf_lock_flag",
                0,
            )
            or 0
        )

        # --------------------------------------------------------
        # ロック未済
        # --------------------------------------------------------
        if lock_flag != 1:
            result = (
                ReportExtractionV2ItemResult(
                    project_year=int(
                        item.project_year
                    ),
                    project_no=str(
                        item.project_no
                    ),
                    pdf_filename=str(
                        getattr(
                            item,
                            "pdf_filename",
                            "",
                        )
                        or ""
                    ),
                    action=ACTION_SKIPPED,
                    pdf_kind=None,
                    page_count=0,
                    text_page_count=0,
                    image_page_count=0,
                    report_pages_path=None,
                    processing_status_path=None,
                    message=(
                        "ロック未済のため"
                        "スキップしました．"
                    ),
                    error_message=None,
                )
            )

            skipped_count += 1
            results.append(
                result
            )

            continue

        # --------------------------------------------------------
        # execute
        # --------------------------------------------------------
        try:
            result = (
                extract_one_report_v2(
                    projects_root,
                    project_year=(
                        item.project_year
                    ),
                    project_no=(
                        item.project_no
                    ),
                    done_by=done_by,
                    role=role,
                    replace_extracted=(
                        replace_extracted
                    ),
                )
            )

        except Exception as exc:
            result = (
                ReportExtractionV2ItemResult(
                    project_year=int(
                        item.project_year
                    ),
                    project_no=str(
                        item.project_no
                    ),
                    pdf_filename=str(
                        getattr(
                            item,
                            "pdf_filename",
                            "",
                        )
                        or ""
                    ),
                    action=ACTION_ERROR,
                    pdf_kind=None,
                    page_count=0,
                    text_page_count=0,
                    image_page_count=0,
                    report_pages_path=None,
                    processing_status_path=None,
                    message=(
                        "テキスト抽出に"
                        "失敗しました．"
                    ),
                    error_message=str(
                        exc
                    ),
                )
            )

        results.append(
            result
        )

        # --------------------------------------------------------
        # action集計
        # --------------------------------------------------------
        if (
            result.action
            == ACTION_PROCESSED
        ):
            processed_count += 1

        elif (
            result.action
            == ACTION_REPLACED
        ):
            processed_count += 1
            replaced_count += 1

        elif (
            result.action
            == ACTION_SKIPPED
        ):
            skipped_count += 1

        elif (
            result.action
            == ACTION_ERROR
        ):
            error_count += 1

        # --------------------------------------------------------
        # PDF種別集計
        # --------------------------------------------------------
        if result.action in {
            ACTION_PROCESSED,
            ACTION_REPLACED,
        }:
            if result.pdf_kind == "text":
                text_pdf_count += 1

            elif result.pdf_kind == "image":
                image_pdf_count += 1

            elif result.pdf_kind == "mixed":
                mixed_pdf_count += 1

    return ReportExtractionV2YearResult(
        project_year=int(
            year
        ),
        total_count=total_count,
        processed_count=(
            processed_count
        ),
        replaced_count=(
            replaced_count
        ),
        skipped_count=(
            skipped_count
        ),
        error_count=(
            error_count
        ),
        text_pdf_count=(
            text_pdf_count
        ),
        image_pdf_count=(
            image_pdf_count
        ),
        mixed_pdf_count=(
            mixed_pdf_count
        ),
        results=tuple(
            results
        ),
    )