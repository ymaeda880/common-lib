# -*- coding: utf-8 -*-
# common_lib/project_master/report_pages_v2_ops.py
# ============================================================
# report_pages.json 正本API（新方式）
#
# 機能：
# - report_pages.json のパスを取得する
# - report_pages.json を保存する
# - report_pages.json を読み込む
#
# 方針：
# - report_raw.txt / report_raw_pages.json は使用しない
# - ページ単位テキストの正本は report_pages.json
# - original_text：
#     現在の処理サイクルで最初に確定したテキスト
# - text：
#     現在採用しているテキスト
# - 103ではOCRを行わないため，
#   image頁の original_text / text は空文字とする
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================

import json
from pathlib import Path
from typing import Any

# ============================================================
# common_lib
# ============================================================

from common_lib.project_master.paths import (
    get_project_text_dir,
    normalize_pno_3digits,
    normalize_year_4digits,
)


# ============================================================
# constants
# ============================================================

REPORT_PAGES_FILENAME = "report_pages.json"
REPORT_PAGES_VERSION = 1

PAGE_KIND_TEXT = "text"
PAGE_KIND_IMAGE = "image"

PDF_KIND_TEXT = "text"
PDF_KIND_IMAGE = "image"
PDF_KIND_MIXED = "mixed"


# ============================================================
# path
# ============================================================

def get_report_pages_path(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> Path:
    # ------------------------------------------------------------
    # text/report_pages.json
    # ------------------------------------------------------------
    year = normalize_year_4digits(
        project_year
    )

    pno3 = normalize_pno_3digits(
        project_no
    )

    text_dir = get_project_text_dir(
        projects_root,
        project_year=year,
        project_no=pno3,
    )

    return (
        text_dir
        / REPORT_PAGES_FILENAME
    )


# ============================================================
# helpers
# ============================================================

def _write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    # ------------------------------------------------------------
    # atomic write
    # ------------------------------------------------------------
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    try:
        tmp_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        tmp_path.replace(
            path
        )

    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def determine_pdf_kind(
    *,
    text_page_count: int,
    image_page_count: int,
) -> str:
    # ------------------------------------------------------------
    # ページ内訳からPDF全体の種別を決定する
    # ------------------------------------------------------------
    text_count = int(
        text_page_count
    )

    image_count = int(
        image_page_count
    )

    if (
        text_count > 0
        and image_count == 0
    ):
        return PDF_KIND_TEXT

    if (
        text_count == 0
        and image_count > 0
    ):
        return PDF_KIND_IMAGE

    if (
        text_count > 0
        and image_count > 0
    ):
        return PDF_KIND_MIXED

    raise RuntimeError(
        "PDFページ内訳が不正です．"
        f" text={text_count}"
        f" image={image_count}"
    )


# ============================================================
# write
# ============================================================

def write_report_pages(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    pdf_filename: str,
    source_pdf_sha256: str,
    pages: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    # ------------------------------------------------------------
    # report_pages.json を保存する
    # ------------------------------------------------------------
    normalized_pages: list[
        dict[str, Any]
    ] = []

    text_page_count = 0
    image_page_count = 0

    for index, row in enumerate(
        pages,
        start=1,
    ):
        if not isinstance(
            row,
            dict,
        ):
            raise TypeError(
                "pages の要素がdictではありません．"
            )

        page_no = int(
            row.get(
                "page_no",
                index,
            )
            or index
        )

        page_kind = str(
            row.get(
                "page_kind",
                "",
            )
            or ""
        ).strip().lower()

        if page_kind == PAGE_KIND_TEXT:
            text_page_count += 1

        elif page_kind == PAGE_KIND_IMAGE:
            image_page_count += 1

        else:
            raise ValueError(
                f"不正なpage_kindです．"
                f" page_no={page_no}"
                f" page_kind={page_kind}"
            )

        direct_char_count = int(
            row.get(
                "direct_char_count",
                0,
            )
            or 0
        )

        original_text = str(
            row.get(
                "original_text",
                "",
            )
            or ""
        )

        text = str(
            row.get(
                "text",
                "",
            )
            or ""
        )

        normalized_pages.append(
            {
                "page_no": page_no,
                "page_kind": page_kind,
                "direct_char_count": (
                    direct_char_count
                ),
                "original_text": (
                    original_text
                ),
                "text": text,
            }
        )

    normalized_pages.sort(
        key=lambda x: int(
            x["page_no"]
        )
    )

    page_count = len(
        normalized_pages
    )

    if page_count <= 0:
        raise RuntimeError(
            "保存対象ページがありません．"
        )

    pdf_kind = determine_pdf_kind(
        text_page_count=(
            text_page_count
        ),
        image_page_count=(
            image_page_count
        ),
    )

    payload = {
        "version": REPORT_PAGES_VERSION,
        "pdf_filename": str(
            pdf_filename
        ),
        "source_pdf_sha256": str(
            source_pdf_sha256
        ),
        "pdf_kind": pdf_kind,
        "page_count": page_count,
        "text_page_count": (
            text_page_count
        ),
        "image_page_count": (
            image_page_count
        ),
        "pages": normalized_pages,
    }

    path = get_report_pages_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    _write_json_atomic(
        path,
        payload,
    )

    return (
        path,
        payload,
    )


# ============================================================
# update save
# ============================================================

def save_report_pages(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    payload: dict[str, Any],
) -> Path:
    # ------------------------------------------------------------
    # 既存の report_pages.json payload をそのまま保存する
    #
    # OCR状態など，write_report_pages() が新規作成時には
    # 扱わない追加メタデータも保持したまま保存する．
    # ------------------------------------------------------------
    if not isinstance(payload, dict):
        raise TypeError(
            "report_pages.json の payload がdictではありません．"
        )

    pages = payload.get(
        "pages",
        [],
    )

    if not isinstance(pages, list):
        raise TypeError(
            "report_pages.json の pages がlistではありません．"
        )

    path = get_report_pages_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    _write_json_atomic(
        path,
        payload,
    )

    return path

# ============================================================
# read
# ============================================================

def read_report_pages(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # report_pages.json を読み込む
    # ------------------------------------------------------------
    path = get_report_pages_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    if not path.exists():
        raise FileNotFoundError(
            "report_pages.json がありません．"
            f" path={path}"
        )

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

    except Exception as exc:
        raise RuntimeError(
            "report_pages.json の読み込みに失敗しました．"
            f" path={path}"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "report_pages.json がdictではありません．"
        )

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

    return payload