# -*- coding: utf-8 -*-
# common_lib/pdf_tools/gpt_ocr.py
# ============================================================
# GPT OCR（OpenAI Vision）共通ロジック
#
# 役割：
# - PDFページを画像化する
# - 必要に応じてOCR用画像を回転する
# - OpenAI Vision によるページ単位OCRを実行する
# - OCRプロンプトを一元管理する
#
# 方針：
# - PDF本体は変更しない
# - OCR用PNG生成時だけ回転する
# - rotation_deg=0 の場合は従来どおりの動作とする
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================

from typing import Any
import struct


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
# constants
# ============================================================

VALID_ROTATION_DEGREES = (
    0,
    90,
    180,
    270,
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
    max_long_side_px: int = 4000,
    rotation_deg: int = 0,
) -> bytes:
    # ------------------------------------------------------------
    # PDFの1ページをPNG bytesに変換する
    #
    # 通常は指定DPIで描画する．
    # ただし巨大PDFページでは画像サイズが過大になるため，
    # 長辺が max_long_side_px を超えないよう自動縮小する．
    #
    # rotation_deg：
    # - 0   ：回転なし
    # - 90  ：右90°回転
    # - 180 ：180°回転
    # - 270 ：左90°回転
    #
    # PDF本体は変更せず，OCR用PNGだけを回転する．
    # ------------------------------------------------------------

    page_idx = (
        int(page_no_1based)
        - 1
    )

    normalized_rotation_deg = int(
        rotation_deg
        or 0
    )

    if (
        normalized_rotation_deg
        not in VALID_ROTATION_DEGREES
    ):
        raise ValueError(
            "rotation_deg は "
            "0 / 90 / 180 / 270 "
            "のいずれかを指定してください．"
            f" rotation_deg={normalized_rotation_deg}"
        )

    doc = fitz.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    try:
        page = doc.load_page(
            page_idx
        )

        base_scale = (
            float(render_dpi)
            / 72.0
        )

        target_width = (
            float(page.rect.width)
            * base_scale
        )

        target_height = (
            float(page.rect.height)
            * base_scale
        )

        long_side = max(
            target_width,
            target_height,
        )

        scale = base_scale

        if (
            int(max_long_side_px) > 0
            and long_side
            > float(max_long_side_px)
        ):
            scale *= (
                float(max_long_side_px)
                / float(long_side)
            )

        # --------------------------------------------------------
        # OCR用画像の回転
        #
        # 130_pdfOCRskip.py で保存した
        # ocr_rotation_deg をここへ渡す．
        #
        # 0度では従来と同じ描画となる．
        # --------------------------------------------------------

        matrix = fitz.Matrix(
            scale,
            scale,
        )

        if (
            normalized_rotation_deg
            != 0
        ):
            matrix = matrix.prerotate(
                normalized_rotation_deg
            )

        pix = page.get_pixmap(
            matrix=matrix,
            alpha=False,
        )

        return pix.tobytes(
            "png"
        )

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

    # # ===== DEBUG START =====
    # print("")
    # print("========================================")
    # print("[GPT OCR IMAGE DEBUG]")
    # print(f"bytes: {len(image_bytes):,}")
    # print(f"header: {image_bytes[:16]!r}")

    # png_signature_ok = image_bytes.startswith(
    #     b"\x89PNG\r\n\x1a\n"
    # )

    # print(f"png_signature_ok: {png_signature_ok}")

    # if png_signature_ok and len(image_bytes) >= 24:
    #     width, height = struct.unpack(
    #         ">II",
    #         image_bytes[16:24],
    #     )

    #     print(f"width: {width:,}")
    #     print(f"height: {height:,}")
    #     print(f"pixels: {width * height:,}")

    # print("========================================")
    # # ===== DEBUG END =====

    res = call_vision_text(
        provider="openai",
        model=str(
            model
        ),
        image_bytes=image_bytes,
        prompt=str(
            prompt
        ),
        system=None,
        max_output_tokens=max_output_tokens,
        extra=None,
    )

    text = str(
        getattr(
            res,
            "text",
            "",
        )
        or ""
    ).strip()

    return (
        text,
        res,
    )


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
    #
    # この共通処理では rotation_deg を指定しないため，
    # 従来どおり rotation_deg=0 で動作する．
    #
    # report_pages.json / contract_pages.json の
    # ocr_rotation_deg は，各OCR処理側から
    # render_pdf_page_png_bytes_for_gpt_ocr() に直接渡す．
    # ------------------------------------------------------------

    raw_page_texts: list[str] = []
    ai_results: list[Any] = []

    for page_no in range(
        1,
        int(page_count_total) + 1,
    ):
        image_bytes = (
            render_pdf_page_png_bytes_for_gpt_ocr(
                fitz=fitz,
                pdf_bytes=pdf_bytes,
                page_no_1based=int(
                    page_no
                ),
                render_dpi=int(
                    render_dpi
                ),
            )
        )

        raw_text, ai_res = (
            run_gpt_ocr_one_page(
                image_bytes=image_bytes,
                model=str(
                    gpt_model
                    or "gpt-4.1-mini"
                ),
                max_output_tokens=(
                    gpt_max_output_tokens
                ),
            )
        )

        raw_page_texts.append(
            str(
                raw_text
                or ""
            )
        )

        ai_results.append(
            ai_res
        )

        if (
            progress_callback
            is not None
        ):
            progress_callback(
                int(
                    page_no
                ),
                int(
                    page_count_total
                ),
            )

    return (
        raw_page_texts,
        ai_results,
    )