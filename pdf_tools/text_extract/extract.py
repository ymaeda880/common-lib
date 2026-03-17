# common_lib/pdf_tools/text_extract/extract.py
# ============================================================
# PDF text extract（共通ライブラリ）
#
# 機能：
# - テキストPDFの直接抽出
# - 画像PDFの OCR → 抽出（PyMuPDF OCR API）
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from typing import Any


# ============================================================
# public api（extract: text）
# ============================================================
def extract_text_direct(
    *,
    fitz: Any,
    pdf_bytes: bytes,
    page_start_0: int,
    page_end_0_inclusive: int,
) -> str:
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
        # extract
        # --------------------------------------------------------
        out: list[str] = []
        for i in range(int(page_start_0), int(page_end_0_inclusive) + 1):
            page = doc.load_page(i)
            txt = page.get_text("text") or ""
            out.append(txt)

        return "\n".join(out).strip()

    finally:
        # --------------------------------------------------------
        # close
        # --------------------------------------------------------
        doc.close()

# ============================================================
# public api（extract: OCR）
# ============================================================
def extract_text_with_ocr(
    *,
    fitz: Any,
    pdf_bytes: bytes,
    page_start_0: int,
    page_end_0_inclusive: int,
    ocr_lang: str,
    ocr_dpi: int = 300,
    ocr_full: bool = True,
    min_chars_per_page: int = 20,
    max_bad_pages: int = 2,
) -> str:
    """
    PyMuPDF の OCR 経由でテキスト化。
    ※環境によっては Tesseract が必要です。
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
        # extract via OCR
        # --------------------------------------------------------
        out: list[str] = []
        bad_pages = 0

        for i in range(int(page_start_0), int(page_end_0_inclusive) + 1):
            page = doc.load_page(i)

            # ----------------------------------------------------
            # guard: OCR API existence
            # ----------------------------------------------------
            if not hasattr(page, "get_textpage_ocr"):
                raise RuntimeError(
                    "この環境の PyMuPDF では OCR API が利用できません（page.get_textpage_ocr が見つかりません）。"
                )

            # ----------------------------------------------------
            # OCR（dpi 指定 + 品質ガード）
            # ----------------------------------------------------
            lang = str(ocr_lang or "eng")
            try:
                try:
                    tp = page.get_textpage_ocr(
                        language=lang,
                        dpi=int(ocr_dpi),
                        full=bool(ocr_full),
                    )
                except TypeError:
                    tp = page.get_textpage_ocr(language=lang)

                txt = tp.extractText() if tp is not None else ""

            except Exception as e:  # noqa: BLE001
                raise RuntimeError(
                    "OCR に失敗しました。Tesseract 未導入/パス未設定、または言語データ未導入の可能性があります。"
                    f" details={type(e).__name__}: {e}"
                ) from e

            txt = str(txt or "").strip()

            # ----------------------------------------------------
            # 品質ガード
            # ----------------------------------------------------
            if len(txt) < int(min_chars_per_page):
                bad_pages += 1
            else:
                bad_pages = max(0, bad_pages - 1)

            if bad_pages > int(max_bad_pages):
                raise RuntimeError(
                    "OCR結果が極端に短いページが続いています。"
                    "（日本語言語データ 'jpn' 未導入、または OCR 解像度不足の疑い）"
                    f" lang={lang} dpi={int(ocr_dpi)} min_chars_per_page={int(min_chars_per_page)}"
                )

            out.append(txt)

        return "\n".join(out).strip()

    finally:
        # --------------------------------------------------------
        # close
        # --------------------------------------------------------
        doc.close()


# ============================================================
# public api（build OCR PDF bytes）
# ============================================================
def build_ocr_pdf_bytes(
    *,
    fitz: Any,
    pdf_bytes: bytes,
    page_start_0: int,
    page_end_0_inclusive: int,
    ocr_lang: str,
    ocr_dpi: int = 300,
) -> bytes:
    """
    画像PDFから OCR済みPDF（検索可能PDF）の bytes を生成する。
    各ページを画像化し、PyMuPDF / Tesseract 経由で invisible text layer を付与する。
    """
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()

    try:
        if getattr(src, "is_encrypted", False):
            raise RuntimeError("このPDFは暗号化されています（パスワード付き）。")

        lang = str(ocr_lang or "eng")

        for i in range(int(page_start_0), int(page_end_0_inclusive) + 1):
            page = src.load_page(i)

            # ----------------------------------------------------
            # render pixmap
            # ----------------------------------------------------
            scale = float(ocr_dpi) / 72.0
            matrix = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # ----------------------------------------------------
            # guard: OCR PDF API existence
            # ----------------------------------------------------
            if not hasattr(pix, "pdfocr_tobytes"):
                raise RuntimeError(
                    "この環境の PyMuPDF では OCR PDF 生成 API が利用できません（pix.pdfocr_tobytes が見つかりません）。"
                )

            # ----------------------------------------------------
            # one-page OCR PDF bytes
            # ----------------------------------------------------
            try:
                try:
                    one_page_pdf_bytes = pix.pdfocr_tobytes(
                        language=lang,
                        compress=True,
                    )
                except TypeError:
                    one_page_pdf_bytes = pix.pdfocr_tobytes(language=lang)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(
                    "OCR済みPDFの生成に失敗しました。"
                    "Tesseract 未導入/パス未設定、または言語データ未導入の可能性があります。"
                    f" details={type(e).__name__}: {e}"
                ) from e

            # ----------------------------------------------------
            # append into output doc
            # ----------------------------------------------------
            one_page_doc = fitz.open(stream=one_page_pdf_bytes, filetype="pdf")
            try:
                out.insert_pdf(one_page_doc)
            finally:
                one_page_doc.close()

        try:
            return out.tobytes(garbage=4, deflate=True)
        except TypeError:
            return out.tobytes()

    finally:
        out.close()
        src.close()


# ============================================================
# public api（extract from searchable PDF bytes）
# ============================================================
def extract_text_from_pdf_bytes(
    *,
    fitz: Any,
    pdf_bytes: bytes,
    page_start_0: int,
    page_end_0_inclusive: int,
) -> str:
    """
    すでに text layer を持つ PDF bytes から通常抽出する。
    OCR済みPDFからの抽出にも使う。
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if getattr(doc, "is_encrypted", False):
            raise RuntimeError("このPDFは暗号化されています（パスワード付き）。")

        out: list[str] = []
        for i in range(int(page_start_0), int(page_end_0_inclusive) + 1):
            page = doc.load_page(i)
            txt = page.get_text("text") or ""
            out.append(txt)

        return "\n".join(out).strip()

    finally:
        doc.close()    