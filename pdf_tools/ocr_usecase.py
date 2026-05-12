# -*- coding: utf-8 -*-
# common_lib/pdf_tools/ocr_usecase.py
# ============================================================
# OCR Usecase（正本）
#
# 役割：
# - PDF bytes を入力として OCR を実行
# - PDF種別判定
# - ページ指定OCR
# - OCR済みPDF bytes からページ単位テキスト抽出
# - clean_ocr_text によるクリーニング
# - 結果を返却（保存はしない）
#
# 設計方針：
# - project 前提を持たない
# - UIを持たない
# - ファイル保存をしない
# - OCR / text抽出 / clean は common_lib.pdf_tools の正本を使う
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from typing import Any

# ============================================================
# imports（common_lib/pdf_tools）
# ============================================================
from common_lib.pdf_tools.text_extract.fitz_guard import try_import_fitz
from common_lib.pdf_tools.text_extract.detect import detect_pdf_kind_from_bytes
from common_lib.pdf_tools.text_extract.extract import (
    build_ocr_pdf_bytes,
    extract_text_from_pdf_bytes,
)
from common_lib.pdf_tools.text_clean import (
    CleanOptions,
    clean_ocr_text,
)

# ============================================================
# imports（common_lib/ai）
# ============================================================
from common_lib.ai.routing import call_vision_text


# ============================================================
# clean options（正本）
# ============================================================
def _build_default_clean_options() -> CleanOptions:
    # ------------------------------------------------------------
    # report_ocr_ops.py と同じ既定値
    # ------------------------------------------------------------
    return CleanOptions(
        remove_jp_in_sentence_spaces=True,
        drop_toc_block=True,
        toc_min_run=6,
        drop_repeated_lines=True,
        repeated_min_count=3,
        repeated_max_len=40,
        join_wrapped_lines=True,
        drop_garbage_english_lines=True,
        drop_decoration_lines=True,
        drop_tiny_noise_lines=True,
    )


# ============================================================
# helper：fitz取得
# ============================================================
def _require_fitz():
    # ------------------------------------------------------------
    # PyMuPDF import guard
    # ------------------------------------------------------------
    fitz_res = try_import_fitz()
    if (not fitz_res.ok) or (fitz_res.fitz is None):
        raise RuntimeError(
            f"PyMuPDF（fitz）が利用できません。 import error: {fitz_res.error}"
        )

    return fitz_res.fitz


# ============================================================
# helper：PDFページ数取得
# ============================================================
def _get_pdf_page_count(*, fitz, pdf_bytes: bytes) -> int:
    # ------------------------------------------------------------
    # PDF bytes からページ数を取得
    # ------------------------------------------------------------
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return int(doc.page_count)
    finally:
        doc.close()


# ============================================================
# helper：ページ番号正規化
# ============================================================
def _normalize_page_numbers(
    *,
    page_numbers: list[int] | None,
    page_count: int,
) -> list[int]:
    # ------------------------------------------------------------
    # 1始まりページ番号を正規化
    # ------------------------------------------------------------
    if int(page_count) <= 0:
        raise RuntimeError(f"page_count が不正です。 page_count={page_count}")

    if page_numbers is None:
        return list(range(1, int(page_count) + 1))

    normalized: list[int] = []

    for x in page_numbers:
        n = int(x)
        if n < 1 or n > int(page_count):
            raise RuntimeError(
                f"ページ番号が範囲外です。 page={n} page_count={page_count}"
            )
        if n not in normalized:
            normalized.append(n)

    if not normalized:
        raise RuntimeError("OCR対象ページが空です。")

    return normalized


# ============================================================
# helper：単一ページOCR
# ============================================================
def _build_one_page_ocr_pdf_bytes(
    *,
    fitz,
    pdf_bytes: bytes,
    page_no_1based: int,
    ocr_lang: str,
    ocr_dpi: int,
) -> bytes:
    # ------------------------------------------------------------
    # 1ページだけOCR済みPDF bytesを生成
    # ------------------------------------------------------------
    page_idx = int(page_no_1based) - 1

    return build_ocr_pdf_bytes(
        fitz=fitz,
        pdf_bytes=pdf_bytes,
        page_start_0=int(page_idx),
        page_end_0_inclusive=int(page_idx),
        ocr_lang=str(ocr_lang or "jpn+eng"),
        ocr_dpi=int(ocr_dpi),
    )


# ============================================================
# helper：単一ページテキスト抽出
# ============================================================
def _extract_text_from_one_page_ocr_pdf(
    *,
    fitz,
    ocr_pdf_bytes: bytes,
) -> str:
    # ------------------------------------------------------------
    # 1ページOCR済みPDF bytesからテキスト抽出
    # ------------------------------------------------------------
    text = extract_text_from_pdf_bytes(
        fitz=fitz,
        pdf_bytes=ocr_pdf_bytes,
        page_start_0=0,
        page_end_0_inclusive=0,
    )

    return str(text or "")

# ============================================================
# helper：単一ページPNG化
# ============================================================
def _render_one_page_png_bytes(
    *,
    fitz,
    pdf_bytes: bytes,
    page_no_1based: int,
    render_dpi: int,
) -> bytes:
    # ------------------------------------------------------------
    # 1ページをPNG bytesへ変換する
    # ------------------------------------------------------------
    page_idx = int(page_no_1based) - 1
    scale = float(render_dpi) / 72.0

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            alpha=False,
        )
        return pix.tobytes("png")
    finally:
        doc.close()


# ============================================================
# helper：GPT OCR
# ============================================================
def _run_gpt_ocr_one_page(
    *,
    image_bytes: bytes,
    model: str,
    max_output_tokens: int | None,
) -> tuple[str, Any]:
    # ------------------------------------------------------------
    # GPT Vision を使って1ページ画像から文字を抽出する
    # - text だけでなく res も返す
    # - res.usage / res.cost はページ側の busy 反映で使用する
    # ------------------------------------------------------------
    prompt = (
        "この画像に含まれる文字を、できるだけ忠実にすべて抽出してください。\n"
        "説明や要約は不要です。\n"
        "表・箇条書き・改行は、可能な範囲で元の構造を保ってください。\n"
        "判読できない文字は無理に補完せず、読める範囲だけ出力してください。"
    )

    res = call_vision_text(
        provider="openai",
        model=str(model),
        image_bytes=image_bytes,
        prompt=prompt,
        system=None,
        max_output_tokens=max_output_tokens,
        extra=None,
    )

    text = str(getattr(res, "text", "") or "").strip()
    return text, res


# ============================================================
# helper：ページテキスト連結
# ============================================================
def _join_pages_text(pages_text_list: list[str]) -> str:
    # ------------------------------------------------------------
    # ページ単位テキストを全文へ連結
    # ------------------------------------------------------------
    return "\n\n".join([str(x or "") for x in pages_text_list]).strip()


# ============================================================
# public：PDF情報取得
# ============================================================
def inspect_pdf_bytes(
    *,
    pdf_bytes: bytes,
    sample_pages: int = 3,
    min_text_chars: int = 40,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # PDF bytes の種別・ページ数を判定する
    # ------------------------------------------------------------
    fitz = _require_fitz()

    detected_kind, detected_pages = detect_pdf_kind_from_bytes(
        fitz=fitz,
        pdf_bytes=pdf_bytes,
        sample_pages=int(sample_pages),
        min_text_chars=int(min_text_chars),
    )

    pdf_kind = str(detected_kind or "")
    page_count = int(detected_pages)

    if pdf_kind not in ("text", "image"):
        raise RuntimeError(f"pdf_kind 判定結果が不正です。 pdf_kind={pdf_kind}")

    if page_count <= 0:
        page_count = _get_pdf_page_count(
            fitz=fitz,
            pdf_bytes=pdf_bytes,
        )

    if page_count <= 0:
        raise RuntimeError(f"page_count が不正です。 page_count={page_count}")

    return {
        "status": "ok",
        "pdf_kind": str(pdf_kind),
        "page_count": int(page_count),
    }


# ============================================================
# public：OCR実行
# ============================================================
def run_ocr_from_pdf_bytes(
    *,
    pdf_bytes: bytes,
    page_numbers: list[int] | None = None,
    ocr_lang: str = "jpn+eng",
    do_clean_text: bool = True,
    ocr_dpi: int = 300,
    method: str = "pymupdf_tesseract",
    gpt_model: str = "gpt-4.1-mini",
    gpt_max_output_tokens: int | None = 4000,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # 汎用OCR実行（正本API）
    #
    # method:
    # - pymupdf_tesseract : PyMuPDF OCR / Tesseract
    # - gpt_vision        : GPT Vision OCR
    #
    # 注意：
    # - 本APIは画像PDF専用
    # - text PDF は RuntimeError
    # - 保存はしない
    # ------------------------------------------------------------
    fitz = _require_fitz()

    info = inspect_pdf_bytes(
        pdf_bytes=pdf_bytes,
        sample_pages=3,
        min_text_chars=40,
    )

    pdf_kind = str(info["pdf_kind"])
    page_count = int(info["page_count"])

    if pdf_kind != "image":
        raise RuntimeError(
            f"OCR対象は画像PDFのみです。判定結果: pdf_kind={pdf_kind}"
        )

    target_pages = _normalize_page_numbers(
        page_numbers=page_numbers,
        page_count=page_count,
    )

    method_key = str(method or "pymupdf_tesseract").strip()

    if method_key not in ("pymupdf_tesseract", "gpt_vision"):
        raise RuntimeError(f"OCR方式が不正です。 method={method_key}")

    raw_pages: list[str] = []
    clean_pages: list[str] = []
    ai_results: list[Any] = []

    clean_options = _build_default_clean_options()

    for page_no in target_pages:
        # --------------------------------------------------------
        # PyMuPDF / Tesseract OCR
        # --------------------------------------------------------
        if method_key == "pymupdf_tesseract":
            ocr_pdf_bytes = _build_one_page_ocr_pdf_bytes(
                fitz=fitz,
                pdf_bytes=pdf_bytes,
                page_no_1based=int(page_no),
                ocr_lang=str(ocr_lang or "jpn+eng"),
                ocr_dpi=int(ocr_dpi),
            )

            raw_text = _extract_text_from_one_page_ocr_pdf(
                fitz=fitz,
                ocr_pdf_bytes=ocr_pdf_bytes,
            )

        # --------------------------------------------------------
        # GPT Vision OCR
        # --------------------------------------------------------
        elif method_key == "gpt_vision":
            image_bytes = _render_one_page_png_bytes(
                fitz=fitz,
                pdf_bytes=pdf_bytes,
                page_no_1based=int(page_no),
                render_dpi=int(ocr_dpi),
            )

            raw_text, ai_res = _run_gpt_ocr_one_page(
                image_bytes=image_bytes,
                model=str(gpt_model or "gpt-4.1-mini"),
                max_output_tokens=gpt_max_output_tokens,
            )

            ai_results.append(ai_res)


        else:
            raise RuntimeError(f"OCR方式が不正です。 method={method_key}")

        raw_pages.append(str(raw_text or ""))

        # --------------------------------------------------------
        # clean
        # --------------------------------------------------------
        if bool(do_clean_text):
            clean_text, _clean_report = clean_ocr_text(
                str(raw_text or ""),
                clean_options,
            )
            clean_pages.append(str(clean_text or ""))

    raw_text_all = _join_pages_text(raw_pages)

    clean_applied = bool(do_clean_text)
    clean_text_all = _join_pages_text(clean_pages) if clean_applied else ""

    return {
        "status": "ok",
        "pdf_kind": str(pdf_kind),
        "page_count": int(page_count),
        "used_ocr": True,
        "ocr_method": str(method_key),
        "ocr_lang": str(ocr_lang or "jpn+eng"),
        "ocr_dpi": int(ocr_dpi),
        "gpt_model": str(gpt_model or "") if method_key == "gpt_vision" else "",
        "page_numbers": list(target_pages),
        "raw_pages": raw_pages,
        "raw_text": raw_text_all,
        "clean_applied": bool(clean_applied),
        "clean_pages": clean_pages if clean_applied else [],
        "clean_text": clean_text_all if clean_applied else "",
        "ai_results": ai_results if method_key == "gpt_vision" else [],
    }