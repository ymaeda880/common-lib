# -*- coding: utf-8 -*-
# common_lib/project_master/report_page_ocr_skip_ops.py
# ============================================================
# 報告書 image頁 手動OCR不要処理
#
# 機能：
# - text/report_pages.json の image頁を手動でOCR不要にする
# - manual_ocr_skip を解除する
# - OCR不要頁の判定を共通化する
# - ページ状態に応じて報告書全体のOCR状態を同期する
#
# 方針：
# - page_kind="image" は変更しない
# - OCR不要頁は ocr_done=True とする
# - original_text / text は空文字にする
# - OCR不要解除後は再び140_pdfOCR.pyのOCR対象へ戻す
# - cleaning状態はこの処理では変更しない
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

from common_lib.project_master.processing_status_ops import (
    clear_ocr_done,
    mark_ocr_done,
)

from common_lib.project_master.report_pages_v2_ops import (
    read_report_pages,
    save_report_pages,
)


# ============================================================
# constants
# ============================================================

OCR_SKIP_METHOD = "manual_ocr_skip"
OCR_SKIP_REASON = "manual_ocr_not_required"


# ============================================================
# public：手動OCR不要判定
# ============================================================

def is_report_manual_ocr_skip(
    row: dict[str, Any],
) -> bool:
    return bool(
        row.get(
            "ocr_skip",
            False,
        )
    ) or (
        str(
            row.get(
                "ocr_method",
                "",
            )
            or ""
        )
        .strip()
        .lower()
        == OCR_SKIP_METHOD
    )


# ============================================================
# helpers：page取得
# ============================================================

def _find_page_row(
    payload: dict[str, Any],
    *,
    page_no: int,
) -> dict[str, Any]:
    for row in payload.get(
        "pages",
        [],
    ):
        if int(
            row.get(
                "page_no",
                0,
            )
            or 0
        ) == int(
            page_no
        ):
            return row

    raise RuntimeError(
        "report_pages.json に "
        f"PDF Page {page_no} がありません．"
    )


# ============================================================
# helpers：OCR状態同期
# ============================================================

def _sync_report_ocr_status(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    payload: dict[str, Any],
    done_by: str,
) -> bool:
    image_rows = [
        row
        for row in payload.get(
            "pages",
            [],
        )
        if (
            str(
                row.get(
                    "page_kind",
                    "",
                )
                or ""
            )
            .strip()
            .lower()
            == "image"
        )
    ]

    ocr_done = (
        bool(image_rows)
        and all(
            bool(
                row.get(
                    "ocr_done",
                    False,
                )
            )
            for row in image_rows
        )
    )

    if ocr_done:
        mark_ocr_done(
            projects_root,
            project_year=int(project_year),
            project_no=str(project_no),
            done_by=str(done_by),
        )
    else:
        clear_ocr_done(
            projects_root,
            project_year=int(project_year),
            project_no=str(project_no),
        )

    return bool(
        ocr_done
    )


# ============================================================
# public：手動OCR不要設定
# ============================================================

def mark_report_image_pages_ocr_skip(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    page_numbers: list[int],
    done_by: str,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # 実行時に最新のreport_pages.jsonを再読込する．
    # 未処理のimage頁だけをmanual_ocr_skipへ変更する．
    # ------------------------------------------------------------
    payload = read_report_pages(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
    )

    target_pages = sorted({
        int(page_no)
        for page_no in page_numbers
        if int(page_no) > 0
    })

    if not target_pages:
        raise RuntimeError(
            "テキスト化不要にするページが選択されていません．"
        )

    processed_pages: list[int] = []
    skipped_pages: list[int] = []

    for page_no in target_pages:
        page_row = _find_page_row(
            payload,
            page_no=int(page_no),
        )

        if (
            str(
                page_row.get(
                    "page_kind",
                    "",
                )
                or ""
            )
            .strip()
            .lower()
            != "image"
        ):
            raise RuntimeError(
                f"PDF Page {page_no} はimage頁ではありません．"
            )

        # --------------------------------------------------------
        # 既にOCR・白紙・手動skip等で処理済みなら上書きしない
        # --------------------------------------------------------
        if bool(
            page_row.get(
                "ocr_done",
                False,
            )
        ):
            skipped_pages.append(
                int(page_no)
            )
            continue

        page_row["original_text"] = ""
        page_row["text"] = ""

        page_row["ocr_done"] = True
        page_row["ocr_method"] = OCR_SKIP_METHOD
        page_row["ocr_by"] = str(
            done_by
            or ""
        )

        page_row["blank_page"] = False
        page_row["ocr_skip"] = True
        page_row["ocr_skip_reason"] = OCR_SKIP_REASON

        processed_pages.append(
            int(page_no)
        )

    if processed_pages:
        save_report_pages(
            projects_root,
            project_year=int(project_year),
            project_no=str(project_no),
            payload=payload,
        )

    ocr_done = _sync_report_ocr_status(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        payload=payload,
        done_by=str(done_by),
    )

    return {
        "processed_pages": processed_pages,
        "skipped_pages": skipped_pages,
        "processed_page_count": len(
            processed_pages
        ),
        "ocr_done": bool(
            ocr_done
        ),
    }


# ============================================================
# public：手動OCR不要解除
# ============================================================

def clear_report_image_pages_ocr_skip(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    page_numbers: list[int],
    done_by: str,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # manual_ocr_skipだけを解除する．
    # page_kind="image" は維持する．
    # OCR本文は自動復元せず空文字のままOCR待ちへ戻す．
    # ------------------------------------------------------------
    payload = read_report_pages(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
    )

    target_pages = sorted({
        int(page_no)
        for page_no in page_numbers
        if int(page_no) > 0
    })

    if not target_pages:
        raise RuntimeError(
            "テキスト化不要を解除するページが選択されていません．"
        )

    released_pages: list[int] = []
    skipped_pages: list[int] = []

    for page_no in target_pages:
        page_row = _find_page_row(
            payload,
            page_no=int(page_no),
        )

        if not is_report_manual_ocr_skip(
            page_row
        ):
            skipped_pages.append(
                int(page_no)
            )
            continue

        page_row["original_text"] = ""
        page_row["text"] = ""

        page_row["ocr_done"] = False
        page_row["blank_page"] = False

        page_row.pop(
            "ocr_method",
            None,
        )
        page_row.pop(
            "ocr_by",
            None,
        )
        page_row.pop(
            "ocr_skip",
            None,
        )
        page_row.pop(
            "ocr_skip_reason",
            None,
        )

        released_pages.append(
            int(page_no)
        )

    if released_pages:
        save_report_pages(
            projects_root,
            project_year=int(project_year),
            project_no=str(project_no),
            payload=payload,
        )

    ocr_done = _sync_report_ocr_status(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        payload=payload,
        done_by=str(done_by),
    )

    return {
        "released_pages": released_pages,
        "skipped_pages": skipped_pages,
        "released_page_count": len(
            released_pages
        ),
        "ocr_done": bool(
            ocr_done
        ),
    }