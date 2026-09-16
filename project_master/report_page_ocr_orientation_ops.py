# -*- coding: utf-8 -*-
# common_lib/project_master/report_page_ocr_orientation_ops.py
# ============================================================
# 報告書 image頁 OCR方向設定
#
# 役割：
# - report_pages.json の image頁にOCR用回転角を保存する
# - OCR用回転角は 0 / 90 / 180 / 270 のみ許可する
# - PDF本体，page_kind，OCR状態は変更しない
#
# 方針：
# - 正本は text/report_pages.json
# - report_pages.json の既存フィールドは変更しない
# - ocr_rotation_deg フィールドだけを追加・更新する
# - 保存は report_pages_v2_ops.save_report_pages() を使用する
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================

from pathlib import Path
from typing import Any


# ============================================================
# project_master
# ============================================================

from common_lib.project_master.report_pages_v2_ops import (
    read_report_pages,
    save_report_pages,
)


# ============================================================
# constants
# ============================================================

OCR_ROTATION_FIELD = "ocr_rotation_deg"

VALID_OCR_ROTATIONS = (
    0,
    90,
    180,
    270,
)


# ============================================================
# helpers
# ============================================================

def _find_page_row(
    payload: dict[str, Any],
    *,
    page_no: int,
) -> dict[str, Any]:
    pages = payload.get(
        "pages",
        [],
    )

    if not isinstance(
        pages,
        list,
    ):
        raise RuntimeError(
            "report_pages.json の pages がlistではありません．"
        )

    target_page_no = int(
        page_no
    )

    for row in pages:
        if not isinstance(
            row,
            dict,
        ):
            continue

        current_page_no = int(
            row.get(
                "page_no",
                0,
            )
            or 0
        )

        if current_page_no == target_page_no:
            return row

    raise RuntimeError(
        f"PDF Page {target_page_no} が"
        "report_pages.json にありません．"
    )


def _validate_image_page(
    row: dict[str, Any],
    *,
    page_no: int,
) -> None:
    page_kind = str(
        row.get(
            "page_kind",
            "",
        )
        or ""
    ).strip().lower()

    if page_kind != "image":
        raise RuntimeError(
            f"PDF Page {page_no} は"
            "image頁ではありません．"
        )


def _normalize_rotation_deg(
    rotation_deg: int,
) -> int:
    value = int(
        rotation_deg
    )

    if value not in VALID_OCR_ROTATIONS:
        raise ValueError(
            "OCR回転角は "
            "0 / 90 / 180 / 270 "
            "のいずれかを指定してください．"
        )

    return value


# ============================================================
# public：複数image頁のOCR方向を保存
# ============================================================

def set_report_image_pages_ocr_rotation(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    rotation_by_page: dict[int, int],
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # 例：
    #
    # rotation_by_page = {
    #     12: 0,
    #     15: 90,
    #     18: 270,
    # }
    #
    # 指定されたページだけを更新する．
    # OCR状態・本文・manual_ocr_skip等には触れない．
    # ------------------------------------------------------------

    if not rotation_by_page:
        return {
            "status": "skip",
            "processed_pages": [],
            "rotation_by_page": {},
        }

    payload = read_report_pages(
        projects_root,
        project_year=int(
            project_year
        ),
        project_no=str(
            project_no
        ),
    )

    normalized_rotation_by_page: dict[
        int,
        int,
    ] = {}

    for page_no, rotation_deg in (
        rotation_by_page.items()
    ):
        normalized_page_no = int(
            page_no
        )

        normalized_rotation_deg = (
            _normalize_rotation_deg(
                rotation_deg
            )
        )

        normalized_rotation_by_page[
            normalized_page_no
        ] = normalized_rotation_deg

    processed_pages: list[int] = []

    for page_no in sorted(
        normalized_rotation_by_page
    ):
        page_row = _find_page_row(
            payload,
            page_no=int(
                page_no
            ),
        )

        _validate_image_page(
            page_row,
            page_no=int(
                page_no
            ),
        )

        rotation_deg = int(
            normalized_rotation_by_page[
                page_no
            ]
        )

        page_row[
            OCR_ROTATION_FIELD
        ] = rotation_deg

        processed_pages.append(
            int(
                page_no
            )
        )

    save_report_pages(
        projects_root,
        project_year=int(
            project_year
        ),
        project_no=str(
            project_no
        ),
        payload=payload,
    )

    return {
        "status": "ok",
        "processed_pages": processed_pages,
        "rotation_by_page": {
            int(page_no): int(rotation_deg)
            for page_no, rotation_deg
            in normalized_rotation_by_page.items()
        },
    }

# ============================================================
# public：任意ページのOCR方向を保存
# ============================================================

def set_report_pages_ocr_rotation(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    rotation_by_page: dict[int, int],
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # 150_pdf空白頁置換.py 等で使用する．
    #
    # page_kind は問わない．
    # 指定されたページの ocr_rotation_deg だけを更新する．
    # 本文・page_kind・OCR状態等には触れない．
    # ------------------------------------------------------------

    if not rotation_by_page:
        return {
            "status": "skip",
            "processed_pages": [],
            "rotation_by_page": {},
        }

    payload = read_report_pages(
        projects_root,
        project_year=int(
            project_year
        ),
        project_no=str(
            project_no
        ),
    )

    normalized_rotation_by_page: dict[
        int,
        int,
    ] = {}

    for page_no, rotation_deg in (
        rotation_by_page.items()
    ):
        normalized_page_no = int(
            page_no
        )

        normalized_rotation_deg = (
            _normalize_rotation_deg(
                rotation_deg
            )
        )

        normalized_rotation_by_page[
            normalized_page_no
        ] = normalized_rotation_deg

    processed_pages: list[int] = []

    for page_no in sorted(
        normalized_rotation_by_page
    ):
        page_row = _find_page_row(
            payload,
            page_no=int(
                page_no
            ),
        )

        rotation_deg = int(
            normalized_rotation_by_page[
                page_no
            ]
        )

        page_row[
            OCR_ROTATION_FIELD
        ] = rotation_deg

        processed_pages.append(
            int(
                page_no
            )
        )

    save_report_pages(
        projects_root,
        project_year=int(
            project_year
        ),
        project_no=str(
            project_no
        ),
        payload=payload,
    )

    return {
        "status": "ok",
        "processed_pages": processed_pages,
        "rotation_by_page": {
            int(page_no): int(rotation_deg)
            for page_no, rotation_deg
            in normalized_rotation_by_page.items()
        },
    }