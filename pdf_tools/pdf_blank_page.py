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
    # PDFの指定ページを低解像度グレースケールで描画し，
    # 明確に白ではない画素がほぼ存在しなければ白紙と判定する．
    #
    # 注意：
    # - OCR用AIには送らない機械判定
    # - Page 5 / Page 9のような少量文字ページを
    #   白紙扱いしないよう，非常に厳しい条件にする
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
            return True

        dark_pixel_count = 0

        for value in samples:
            if int(value) < int(
                dark_threshold
            ):
                dark_pixel_count += 1

                if dark_pixel_count > int(
                    max_dark_pixels
                ):
                    return False

        return True

    finally:
        document.close()