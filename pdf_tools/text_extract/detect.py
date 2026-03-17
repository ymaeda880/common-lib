# common_lib/pdf_tools/text_extract/detect.py
# ============================================================
# PDF text extract（共通ライブラリ）
#
# 機能：
# - PDF bytes から「text PDF」か「image PDF」かを軽量に判定する
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from typing import Any, Tuple


# ============================================================
# public api
# ============================================================
def detect_pdf_kind_from_bytes(
    *,
    fitz: Any,
    pdf_bytes: bytes,
    sample_pages: int = 3,
    min_text_chars: int = 40,
) -> Tuple[str, int]:
    """
    ざっくり判定：
    - 先頭数ページで抽出テキストが一定以上なら text
    - ほぼ空なら image

    戻り値：
    - pdf_kind: "text" or "image"
    - page_count
    """
    # ------------------------------------------------------------
    # open
    # ------------------------------------------------------------
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        # --------------------------------------------------------
        # guard: encrypted
        # --------------------------------------------------------
        if getattr(doc, "is_encrypted", False):
            raise RuntimeError("このPDFは暗号化されています（パスワード付き）。")

        # --------------------------------------------------------
        # page count
        # --------------------------------------------------------
        page_count = int(getattr(doc, "page_count", 0) or 0)
        if page_count <= 0:
            raise RuntimeError("PDFのページ数を取得できませんでした。")

        # --------------------------------------------------------
        # sample scan（軽量）
        # --------------------------------------------------------
        n = min(int(sample_pages), page_count)
        total_chars = 0
        for i in range(n):
            txt = doc.load_page(i).get_text("text") or ""
            total_chars += len((txt or "").strip())

        # --------------------------------------------------------
        # decision
        # --------------------------------------------------------
        pdf_kind = "text" if total_chars >= int(min_text_chars) else "image"
        return pdf_kind, page_count

    finally:
        # --------------------------------------------------------
        # close
        # --------------------------------------------------------
        doc.close()