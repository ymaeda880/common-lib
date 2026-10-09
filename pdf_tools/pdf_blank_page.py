# -*- coding: utf-8 -*-
# common_lib/pdf_tools/pdf_blank_page.py
# ============================================================
# PDF白紙ページ判定
#
# 目的：
# - PDFページが実質的な完全白紙かを機械判定する
# - 報告書・契約書・白紙チェック画面で同じ判定基準を使用する
#
# 方針：
# - OCR・AIは使用しない
# - PDFを低解像度グレースケールで描画して判定する
# - 少量文字やページ番号を誤って白紙にしないよう厳しく判定する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from typing import Any


# ============================================================
# public：PDF白紙ページ判定
# ============================================================
# ============================================================
# public：PDF白紙ページ詳細判定
# ============================================================
def inspect_effectively_blank_pdf_page(
    *,
    fitz: Any,
    pdf_bytes: bytes,
    page_no: int,
    render_dpi: int = 72,
    dark_threshold: int = 245,
    max_dark_pixels: int = 20,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # PDFの指定ページを低解像度グレースケールで描画し，
    # 白紙判定と，判定に使用した詳細情報を返す．
    #
    # dark_pixel_count：
    # - 画素値が dark_threshold 未満の画素数
    #
    # 判定：
    # - dark_pixel_count <= max_dark_pixels → 白紙
    # - dark_pixel_count >  max_dark_pixels → 非白紙
    #
    # 非白紙の場合は，判定に必要な上限超過を確認した時点で
    # 走査を終了するため，dark_pixel_count は
    # max_dark_pixels + 1 となる．
    # ------------------------------------------------------------
    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    try:
        target_page_no = int(page_no)

        if (
            target_page_no < 1
            or target_page_no > int(document.page_count)
        ):
            raise ValueError(
                "白紙判定対象ページが"
                "PDFのページ範囲外です．"
                f" page_no={target_page_no}"
            )

        page = document.load_page(
            target_page_no - 1
        )

        scale = (
            float(render_dpi)
            / 72.0
        )

        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(
                scale,
                scale,
            ),
            colorspace=fitz.csGRAY,
            alpha=False,
        )

        samples = pixmap.samples

        if not samples:
            return {
                "is_blank": True,
                "dark_pixel_count": 0,
                "dark_pixel_count_exceeded": False,
                "max_dark_pixels": int(max_dark_pixels),
                "dark_threshold": int(dark_threshold),
                "render_dpi": int(render_dpi),
            }

        dark_pixel_count = 0

        for value in samples:
            if int(value) < int(
                dark_threshold
            ):
                dark_pixel_count += 1

                if dark_pixel_count > int(
                    max_dark_pixels
                ):
                    return {
                        "is_blank": False,
                        "dark_pixel_count": dark_pixel_count,
                        "dark_pixel_count_exceeded": True,
                        "max_dark_pixels": int(max_dark_pixels),
                        "dark_threshold": int(dark_threshold),
                        "render_dpi": int(render_dpi),
                    }

        return {
            "is_blank": True,
            "dark_pixel_count": dark_pixel_count,
            "dark_pixel_count_exceeded": False,
            "max_dark_pixels": int(max_dark_pixels),
            "dark_threshold": int(dark_threshold),
            "render_dpi": int(render_dpi),
        }

    finally:
        document.close()


# ============================================================
# public：PDF白紙ページ判定
# ============================================================
def is_effectively_blank_pdf_page(
    *,
    fitz: Any,
    pdf_bytes: bytes,
    page_no: int,
    render_dpi: int = 72,
    dark_threshold: int = 245,
    max_dark_pixels: int = 20,
) -> bool:
    # ------------------------------------------------------------
    # 既存コードとの互換用．
    # 詳細判定を実行し，白紙かどうかだけを返す．
    # ------------------------------------------------------------
    result = inspect_effectively_blank_pdf_page(
        fitz=fitz,
        pdf_bytes=pdf_bytes,
        page_no=page_no,
        render_dpi=render_dpi,
        dark_threshold=dark_threshold,
        max_dark_pixels=max_dark_pixels,
    )

    return bool(
        result["is_blank"]
    )