# -*- coding: utf-8 -*-
# common_lib/pdf_tools/gpt_ocr.py
# ============================================================
# GPT OCR（OpenAI Vision）共通ロジック
#
# 役割：
# - PDFページを画像化する
# - OpenAI Vision によるページ単位OCRを実行する
# - OCRプロンプトを一元管理する
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from typing import Any

# ============================================================
# imports（common_lib/ai）
# ============================================================
from common_lib.ai.routing import call_vision_text


# ============================================================
# prompt（正本）
# ============================================================
GPT_OCR_PROMPT = (
    "この画像に含まれる文字を、できるだけ忠実にすべて抽出してください。\n"
    "説明や要約は不要です。\n"
    "表・箇条書き・改行は、可能な範囲で元の構造を保ってください。\n"
    "判読できない文字は無理に補完せず、読める範囲だけ出力してください。"
)


# ============================================================
# PDF page render
# ============================================================
def render_pdf_page_png_bytes_for_gpt_ocr(
    *,
    fitz,
    pdf_bytes: bytes,
    page_no_1based: int,
    render_dpi: int = 300,
) -> bytes:
    # ------------------------------------------------------------
    # PDFの1ページをPNG bytesに変換する
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
# GPT OCR one page
# ============================================================
def run_gpt_ocr_one_page(
    *,
    image_bytes: bytes,
    model: str,
    max_output_tokens: int | None,
    prompt: str = GPT_OCR_PROMPT,
) -> tuple[str, Any]:
    # ------------------------------------------------------------
    # OpenAI Visionで1ページ画像から文字を抽出する
    # ------------------------------------------------------------
    res = call_vision_text(
        provider="openai",
        model=str(model),
        image_bytes=image_bytes,
        prompt=str(prompt),
        system=None,
        max_output_tokens=max_output_tokens,
        extra=None,
    )

    text = str(getattr(res, "text", "") or "").strip()
    return text, res


# ============================================================
# GPT OCR by page
# ============================================================
def run_gpt_ocr_by_page(
    *,
    fitz,
    pdf_bytes: bytes,
    page_count_total: int,
    gpt_model: str,
    gpt_max_output_tokens: int | None,
    render_dpi: int = 300,
    progress_callback=None,
) -> tuple[list[str], list[Any]]:
    # ------------------------------------------------------------
    # GPT OCRをページごとに実行する
    # ------------------------------------------------------------
    raw_page_texts: list[str] = []
    ai_results: list[Any] = []

    for page_no in range(1, int(page_count_total) + 1):
        image_bytes = render_pdf_page_png_bytes_for_gpt_ocr(
            fitz=fitz,
            pdf_bytes=pdf_bytes,
            page_no_1based=int(page_no),
            render_dpi=int(render_dpi),
        )

        raw_text, ai_res = run_gpt_ocr_one_page(
            image_bytes=image_bytes,
            model=str(gpt_model or "gpt-4.1-mini"),
            max_output_tokens=gpt_max_output_tokens,
        )

        raw_page_texts.append(str(raw_text or ""))
        ai_results.append(ai_res)

        if progress_callback is not None:
            progress_callback(int(page_no), int(page_count_total))

    return raw_page_texts, ai_results