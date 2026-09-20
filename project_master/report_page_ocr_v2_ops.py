# -*- coding: utf-8 -*-
# common_lib/project_master/report_page_ocr_v2_ops.py
# ============================================================
# 報告書 image頁 OCR v2
#
# 機能：
# - report_pages.json の page_kind="image" のみOCRする
# - 1ページOCR Dry Run
# - OCR結果の report_pages.json 反映
# - 指定した複数image頁の一括OCR
# - OCR後のクリーニング
# - image頁OCR完了状態の取得
#
# 方針：
# - 旧 report_ocr_ops.py は変更しない
# - report_raw.txt / report_clean.txt は作成しない
# - 正本は text/report_pages.json
# - OCR後の初期テキストは clean 後テキストとする
# - original_text / text の両方へ初期テキストを保存する
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================

import re
from pathlib import Path
from typing import Any

# ============================================================
# project_master
# ============================================================

from common_lib.project_master.processing_status_ops import (
    mark_cleaned,
    mark_ocr_done,
)

from common_lib.project_master.report_page_ocr_skip_ops import (
    is_report_manual_ocr_skip,
)

from common_lib.project_master.report_pdf_ops import (
    get_report_pdf_path,
)

from common_lib.project_master.report_pages_v2_ops import (
    read_report_pages,
    save_report_pages,
)
# ============================================================
# pdf tools
# ============================================================

from common_lib.pdf_tools.gpt_ocr import (
    render_pdf_page_png_bytes_for_gpt_ocr,
    run_gpt_ocr_one_page,
)

from common_lib.pdf_tools.text_clean import (
    CleanOptions,
    clean_ocr_text,
)

from common_lib.pdf_tools.text_extract.extract import (
    build_ocr_pdf_bytes,
    extract_text_from_pdf_bytes,
)

from common_lib.pdf_tools.text_extract.fitz_guard import (
    try_import_fitz,
)

from common_lib.pdf_tools.pdf_blank_page import (
    is_effectively_blank_pdf_page,
)

from common_lib.pdf_tools.ocr_hallucination import (
    append_hallucination_log,
    get_hallucination_result,
    get_ocr_text_density,
    get_page_content_dark_density,
)

# ============================================================
# helpers（clean）
# ============================================================

def _build_clean_options() -> CleanOptions:
    return CleanOptions(
        remove_jp_in_sentence_spaces=True,
        drop_toc_block=False,
        toc_min_run=6,
        drop_repeated_lines=True,
        repeated_min_count=3,
        repeated_max_len=40,
        join_wrapped_lines=False,
        drop_garbage_english_lines=False,
        drop_decoration_lines=True,
        drop_tiny_noise_lines=True,
    )


def _is_no_content_ocr_text(
    text: str,
) -> bool:
    # ------------------------------------------------------------
    # OCR結果が「内容なし」を示す定型応答なら，
    # RAG本文として採用せず，白紙相当として扱う．
    #
    # 判定：
    # 1. GPTの既知の長い定型応答 → 完全一致
    # 2. 20文字以下 → 無内容表現を含むか確認
    #
    # 通常本文の誤判定を避けるため，
    # 長文に対する部分一致は行わない．
    # ------------------------------------------------------------
    value = str(text or "").strip()

    if not value:
        return True

    # 空白・改行を除去
    normalized = re.sub(
        r"\s+",
        "",
        value,
    )

    # 文末の句読点は無視
    normalized = normalized.rstrip(
        "。．."
    )

    # ------------------------------------------------------------
    # ① GPTが返す既知の「内容なし」定型文
    #    長い文章なので完全一致だけ許可する
    # ------------------------------------------------------------
    exact_no_content_texts = (
        "申し訳ありませんが、この画像から文字を抽出することができません",
        "申し訳ありませんが、この画像には文字が含まれていません",
        "この画像から文字を抽出することができません",
        "この画像には文字が含まれていません",
    )

    if normalized in exact_no_content_texts:
        return True

    # ------------------------------------------------------------
    # ② 20文字を超える文章は，これ以上判定しない
    # ------------------------------------------------------------
    if len(normalized) > 20:
        return False

    # ------------------------------------------------------------
    # ③ 20文字以下の短い「内容なし」応答
    # ------------------------------------------------------------
    no_content_phrases = (
        "文字が含まれていません",
        "文字はありません",
        "文字がありません",
        "テキストはありません",
        "テキストがありません",
        "記載内容なし",
        "記載なし",
        "文字なし",
        "テキストなし",
    )

    return any(
        phrase in normalized
        for phrase in no_content_phrases
    )

# ============================================================
# helpers（page取得）
# ============================================================

def _find_page_row(
    payload: dict[str, Any],
    *,
    page_no: int,
) -> dict[str, Any]:
    for row in payload.get("pages", []):
        if int(
            row.get(
                "page_no",
                0,
            )
            or 0
        ) == int(page_no):
            return row

    raise RuntimeError(
        f"report_pages.json に "
        f"PDF Page {page_no} がありません．"
    )

# ============================================================
# helpers（ハルシネーションログ）
# ============================================================

def _get_report_hallucination_log_path(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
) -> Path:
    pdf_path = get_report_pdf_path(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        role="main",
    )

    if pdf_path is None:
        raise RuntimeError(
            "ハルシネーションログ保存先を解決できません．"
        )

    return (
        pdf_path.parent.parent
        / "text"
        / "ocr_hallucination_log.json"
    )

# ============================================================
# public：OCR状態
# ============================================================
def get_image_ocr_status(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
) -> dict[str, Any]:
    payload = read_report_pages(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
    )

    image_pages = [
        row
        for row in payload.get("pages", [])
        if str(row.get("page_kind", "") or "").strip().lower() == "image"
    ]

    completed_pages = [
        int(row.get("page_no", 0))
        for row in image_pages
        if bool(row.get("ocr_done", False))
    ]

    blank_pages = [
        int(row.get("page_no", 0))
        for row in image_pages
        if (
            bool(row.get("blank_page", False))
            or str(row.get("ocr_method", "") or "").strip().lower() == "blank_skip"
        )
    ]

    skip_pages = [
        int(row.get("page_no", 0))
        for row in image_pages
        if is_report_manual_ocr_skip(
            row
        )
    ]

    blank_page_set = set(
        blank_pages
    )
    skip_page_set = set(
        skip_pages
    )

    ocr_pages = [
        int(row.get("page_no", 0))
        for row in image_pages
        if (
            bool(row.get("ocr_done", False))
            and int(
                row.get(
                    "page_no",
                    0,
                )
            )
            not in blank_page_set
            and int(
                row.get(
                    "page_no",
                    0,
                )
            )
            not in skip_page_set
        )
    ]

    remaining_pages = [
        int(row.get("page_no", 0))
        for row in image_pages
        if not bool(row.get("ocr_done", False))
    ]

    return {
        "image_page_count": len(image_pages),
        "completed_pages": completed_pages,
        "completed_page_count": len(completed_pages),
        "ocr_pages": ocr_pages,
        "ocr_page_count": len(ocr_pages),
        "blank_pages": blank_pages,
        "blank_page_count": len(blank_pages),
        "skip_pages": skip_pages,
        "skip_page_count": len(skip_pages),
        "remaining_pages": remaining_pages,
        "next_page": remaining_pages[0] if remaining_pages else None,
        "ocr_done": bool(image_pages) and not remaining_pages,
    }

# ============================================================
# public：1ページ OCR Dry Run
# ============================================================

def run_image_page_ocr_preview_v2(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    page_no: int,
    method: str,
    gpt_model: str = "gpt-4.1-mini",
    gpt_max_output_tokens: int = 4000,
    ocr_lang: str = "jpn+eng",
    s3_ratio_threshold: float = 0.05,
    gpt_prompt: str | None = None,
) -> dict[str, Any]:
    payload = read_report_pages(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
    )

    page_row = _find_page_row(
        payload,
        page_no=int(page_no),
    )

    if str(
        page_row.get(
            "page_kind",
            "",
        )
        or ""
    ).strip().lower() != "image":
        raise RuntimeError(
            f"PDF Page {page_no} は"
            "image頁ではありません．"
        )

    if is_report_manual_ocr_skip(
        page_row
    ):
        raise RuntimeError(
            f"PDF Page {page_no} は"
            "テキスト化不要として登録されています．"
            "130_pdfOCRskip.pyで解除してからOCRしてください．"
        )

    pdf_path = get_report_pdf_path(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        role="main",
    )

    if (
        pdf_path is None
        or not pdf_path.exists()
    ):
        raise RuntimeError(
            "報告書PDFが存在しません．"
        )

    pdf_bytes = pdf_path.read_bytes()

    fitz_res = try_import_fitz()

    if (
        not fitz_res.ok
        or fitz_res.fitz is None
    ):
        raise RuntimeError(
            "PyMuPDFを利用できません．"
            f" {fitz_res.error}"
        )

    fitz = fitz_res.fitz
    method_key = str(method or "").strip()

    # ------------------------------------------------------------
    # OCR用画像の回転角
    #
    # 130_pdfOCRskip.py の ocr_rotation_deg は，
    # 「現在の文字方向」を表す．
    #
    # OCRでは文字を正立させる必要があるため，
    # 保存された文字方向とは逆方向に画像を回転する．
    #
    # 文字方向：
    #   0   → 補正 0
    #   90  → 補正 270
    #   180 → 補正 180
    #   270 → 補正 90
    # ------------------------------------------------------------
    text_direction_deg = int(
        page_row.get(
            "ocr_rotation_deg",
            0,
        )
        or 0
    )

    if text_direction_deg not in (
        0,
        90,
        180,
        270,
    ):
        raise RuntimeError(
            f"PDF Page {page_no} の"
            "ocr_rotation_deg が不正です．"
            f" text_direction_deg={text_direction_deg}"
        )

    rotation_deg = (
        -text_direction_deg
    ) % 360

    ai_results: list[Any] = []

    # ------------------------------------------------------------
    # 白紙判定
    #
    # OCR処理より先に判定する．
    # 実質完全白紙ならGPT / Tesseractへ送らない．
    # ------------------------------------------------------------
    is_blank_page = (
        is_effectively_blank_pdf_page(
            fitz=fitz,
            pdf_bytes=pdf_bytes,
            page_no=int(page_no),
        )
    )


    # ------------------------------------------------------------
    # GPT OCR
    # ------------------------------------------------------------
    if method_key == "gpt_vision":
        image_bytes = (
            render_pdf_page_png_bytes_for_gpt_ocr(
                fitz=fitz,
                pdf_bytes=pdf_bytes,
                page_no_1based=int(page_no),
                render_dpi=300,
                rotation_deg=int(
                    rotation_deg
                ),
            )
        )

        # --------------------------------------------------------
        # 実質白紙
        # --------------------------------------------------------
        if is_blank_page:
            return {
                "page_no": int(page_no),
                "raw_text": "",
                "clean_text": "",
                "ai_results": [],
                "method": method_key,
                "is_blank": True,
                "hallucination_suspected": False,
                "hallucination_reason": "",
            }

        # --------------------------------------------------------
        # 非白紙だけGPT OCR
        # --------------------------------------------------------
        if gpt_prompt is None:
            raw_text, ai_result = (
                run_gpt_ocr_one_page(
                    image_bytes=image_bytes,
                    model=str(
                        gpt_model
                        or "gpt-4.1-mini"
                    ),
                    max_output_tokens=int(
                        gpt_max_output_tokens
                    ),
                )
            )
        else:
            raw_text, ai_result = (
                run_gpt_ocr_one_page(
                    image_bytes=image_bytes,
                    model=str(
                        gpt_model
                        or "gpt-4.1-mini"
                    ),
                    max_output_tokens=int(
                        gpt_max_output_tokens
                    ),
                    prompt=str(gpt_prompt),
                )
            )

        raw_text = str(
            raw_text
            or ""
        )

        ai_results = (
            [ai_result]
            if ai_result is not None
            else []
        )   

    # ------------------------------------------------------------
    # Tesseract
    # ------------------------------------------------------------
    elif method_key == "pymupdf_tesseract":
        debug_image_bytes = None

        if is_blank_page:
            return {
                "page_no": int(page_no),
                "raw_text": "",
                "clean_text": "",
                "ai_results": [],
                "method": method_key,
                "is_blank": True,
                "hallucination_suspected": False,
                "hallucination_reason": "",                
                #"debug_image_bytes": None,
            }

        ocr_pdf_bytes = build_ocr_pdf_bytes(
            fitz=fitz,
            pdf_bytes=pdf_bytes,
            page_start_0=int(page_no) - 1,
            page_end_0_inclusive=int(page_no) - 1,
            ocr_lang=str(
                ocr_lang
                or "jpn+eng"
            ),
            ocr_dpi=300,
        )

        raw_text = str(
            extract_text_from_pdf_bytes(
                fitz=fitz,
                pdf_bytes=ocr_pdf_bytes,
                page_start_0=0,
                page_end_0_inclusive=0,
            )
            or ""
        )

    else:
        raise RuntimeError(
            "OCR方式が不正です．"
            f" method={method_key}"
        )

    # ------------------------------------------------------------
    # OCR結果が空の場合
    #
    # GPTが文字のないページに対して空文字を返すことがあるため，
    # OCRエラーにはせず，白紙ページとして扱う．
    # ------------------------------------------------------------
    if not raw_text.strip():
        return {
            "page_no": int(page_no),
            "raw_text": "",
            "clean_text": "",
            "ai_results": list(ai_results or []),
            "method": method_key,
            "is_blank": True,
            "hallucination_suspected": False,
            "hallucination_reason": "",
        }

    clean_text, _clean_report = clean_ocr_text(
        raw_text,
        _build_clean_options(),
    )

    # ===== DEBUG START =====
    # print("")
    # print("========================================")
    # print("[OCR RAW TEXT]")
    # print(repr(raw_text))
    # print("----------------------------------------")
    # print("[OCR CLEAN TEXT]")
    # print(repr(clean_text))
    # print("========================================")
    # ===== DEBUG END =====

    # ------------------------------------------------------------
    # ハルシネーション判定用データ
    # ------------------------------------------------------------

    content_density = get_page_content_dark_density(
        fitz=fitz,
        pdf_bytes=pdf_bytes,
        page_no=int(page_no),
    )

    content_pixel_count = int(
        content_density["content_pixel_count"]
    )

    ocr_density = get_ocr_text_density(
        text=clean_text,
        pixel_count=content_pixel_count,
    ) 

    if _is_no_content_ocr_text(clean_text):
        return {
            "page_no": int(page_no),
            "raw_text": str(raw_text or ""),
            "clean_text": "",
            "ai_results": list(ai_results or []),
            "method": method_key,
            "is_blank": True,
            "hallucination_suspected": False,
            "hallucination_reason": "",
        }

    content_dark_pixels = int(
        content_density["content_dark_pixels"]
    )
    ocr_char_count = int(
        ocr_density["char_count"]
    )

    hallucination_suspected, hallucination_reason = get_hallucination_result(
        method=method_key,
        content_dark_pixels=content_dark_pixels,
        ocr_char_count=ocr_char_count,
        s3_ratio_threshold=float(s3_ratio_threshold),
    )

    return {
        "page_no": int(page_no),
        "raw_text": str(raw_text or ""),
        "clean_text": str(clean_text or ""),
        "ai_results": list(ai_results or []),
        "method": method_key,
        "is_blank": False,
        "hallucination_suspected": hallucination_suspected,
        "hallucination_reason": hallucination_reason,
        "content_dark_pixels": content_dark_pixels,
        "ocr_char_count": ocr_char_count,
    }

# ============================================================
# public：白紙image頁を処理済みにする
# ============================================================

def mark_image_page_blank_v2(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    page_no: int,
    done_by: str,
) -> dict[str, Any]:
    payload = read_report_pages(
        projects_root,
        project_year=int(
            project_year
        ),
        project_no=str(
            project_no
        ),
    )

    page_row = _find_page_row(
        payload,
        page_no=int(
            page_no
        ),
    )

    if str(
        page_row.get(
            "page_kind",
            "",
        )
        or ""
    ).strip().lower() != "image":
        raise RuntimeError(
            f"PDF Page {page_no} は"
            "image頁ではありません．"
        )

    # ------------------------------------------------------------
    # 白紙ページ
    #
    # OCRは実行しないが，image頁としての処理は完了とする．
    # テキストは空のまま保持する．
    # ------------------------------------------------------------
    page_row["original_text"] = ""
    page_row["text"] = ""

    page_row["ocr_done"] = True
    page_row["ocr_method"] = (
        "blank_skip"
    )
    page_row["ocr_by"] = str(
        done_by
        or ""
    )

    page_row["blank_page"] = True
    page_row.pop(
        "ocr_skip",
        None,
    )
    page_row.pop(
        "ocr_skip_reason",
        None,
    )

    save_report_pages(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        payload=payload,
    )

    status = get_image_ocr_status(
        projects_root,
        project_year=int(
            project_year
        ),
        project_no=str(
            project_no
        ),
    )

    if bool(
        status.get(
            "ocr_done",
            False,
        )
    ):
        mark_ocr_done(
            projects_root,
            project_year=int(
                project_year
            ),
            project_no=str(
                project_no
            ),
            done_by=str(
                done_by
            ),
        )

        mark_cleaned(
            projects_root,
            project_year=int(
                project_year
            ),
            project_no=str(
                project_no
            ),
            done_by=str(
                done_by
            ),
        )

    return status

# ============================================================
# public：ハルシネーション疑いページを白紙として確定
# ============================================================

def confirm_report_hallucination_page_blank(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    page_no: int,
    done_by: str,
    method: str,
    model: str,
    reason: str,
    content_dark_pixels: int,
    ocr_char_count: int,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # Dry Runでハルシネーション疑いとなったimage頁を，
    # 人手確認後に白紙として確定する．
    #
    # report_pages.jsonを白紙として更新したうえで，
    # text/ocr_hallucination_log.jsonへ
    # confirmed_blankとして確認履歴を保存する．
    # ------------------------------------------------------------
    status = mark_image_page_blank_v2(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        page_no=int(page_no),
        done_by=str(done_by),
    )

    append_hallucination_log(
        log_path=_get_report_hallucination_log_path(
            projects_root,
            project_year=int(project_year),
            project_no=str(project_no),
        ),
        document_type="report",
        project_year=int(project_year),
        project_no=str(project_no),
        page_no=int(page_no),
        method=str(method),
        model=str(model),
        reason=str(reason or ""),
        content_dark_pixels=int(content_dark_pixels),
        ocr_char_count=int(ocr_char_count),
        detected_by=str(done_by),
        action="confirmed_blank",
        review_status="confirmed_blank",
    )

    return status

# ============================================================
# public：1ページ OCR結果反映
# ============================================================

def apply_image_page_ocr_result_v2(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    page_no: int,
    text: str,
    done_by: str,
    method: str,
) -> dict[str, Any]:
    payload = read_report_pages(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
    )

    page_row = _find_page_row(
        payload,
        page_no=int(page_no),
    )

    if str(
        page_row.get(
            "page_kind",
            "",
        )
        or ""
    ).strip().lower() != "image":
        raise RuntimeError(
            f"PDF Page {page_no} は"
            "image頁ではありません．"
        )

    if is_report_manual_ocr_skip(
        page_row
    ):
        raise RuntimeError(
            f"PDF Page {page_no} は"
            "テキスト化不要として登録されています．"
            "130_pdfOCRskip.pyで解除してからOCRしてください．"
        )

    final_text = str(
        text
        or ""
    )

    if not final_text.strip():
        raise RuntimeError(
            "保存するOCRテキストが空です．"
        )

    # ------------------------------------------------------------
    # image頁に対する最初の有効テキスト
    # ------------------------------------------------------------
    page_row["original_text"] = final_text
    page_row["text"] = final_text

    page_row["ocr_done"] = True
    page_row["ocr_method"] = str(
        method
        or ""
    )
    page_row["ocr_by"] = str(
        done_by
        or ""
    )

    page_row["blank_page"] = False
    page_row.pop(
        "ocr_skip",
        None,
    )
    page_row.pop(
        "ocr_skip_reason",
        None,
    )

    save_report_pages(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        payload=payload,
    )

    status = get_image_ocr_status(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
    )

    if bool(
        status.get(
            "ocr_done",
            False,
        )
    ):
        mark_ocr_done(
            projects_root,
            project_year=int(project_year),
            project_no=str(project_no),
            done_by=str(done_by),
        )

        mark_cleaned(
            projects_root,
            project_year=int(project_year),
            project_no=str(project_no),
            done_by=str(done_by),
        )

    return status

# ============================================================
# public：ハルシネーション疑いOCR結果を確認後に採用
# ============================================================

def confirm_report_hallucination_ocr_result(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    page_no: int,
    text: str,
    done_by: str,
    method: str,
    model: str,
    reason: str,
    content_dark_pixels: int,
    ocr_char_count: int,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # Dry Runでハルシネーション疑いとなったOCR結果を，
    # 人が元PDFと比較して正常と確認した後に採用する．
    #
    # report_pages.jsonへOCR本文を反映し，
    # text/ocr_hallucination_log.jsonへ
    # confirmed_okとして確認履歴を保存する．
    # ------------------------------------------------------------
    status = apply_image_page_ocr_result_v2(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        page_no=int(page_no),
        text=str(text),
        done_by=str(done_by),
        method=str(method),
    )

    append_hallucination_log(
        log_path=_get_report_hallucination_log_path(
            projects_root,
            project_year=int(project_year),
            project_no=str(project_no),
        ),
        document_type="report",
        project_year=int(project_year),
        project_no=str(project_no),
        page_no=int(page_no),
        method=str(method),
        model=str(model),
        reason=str(reason or ""),
        content_dark_pixels=int(content_dark_pixels),
        ocr_char_count=int(ocr_char_count),
        detected_by=str(done_by),
        action="confirmed_ok",
        review_status="confirmed_ok",
    )

    return status

# ============================================================
# public：複数image頁 OCR
# ============================================================

def run_image_pages_ocr_v2(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    done_by: str,
    method: str,
    gpt_model: str = "gpt-4.1-mini",
    gpt_max_output_tokens: int = 4000,
    ocr_lang: str = "jpn+eng",
    max_pages_per_run: int = 100,
    allow_rerun_ocr: bool = False,
    target_page_numbers: list[int] | None = None,
    progress_callback=None,
    s3_ratio_threshold: float = 0.05,
    gpt_prompt: str | None = None,
) -> dict[str, Any]:
    payload = read_report_pages(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
    )

    image_rows = [
        row
        for row in payload.get("pages", [])
        if str(
            row.get(
                "page_kind",
                "",
            )
            or ""
        ).strip().lower()
        == "image"
    ]

    if not image_rows:
        return {
            "status": "skip",
            "processed_pages": [],
            "ocr_pages": [],
            "blank_pages": [],
            "hallucination_pages": [],
            "hallucination_results": [],
            "ai_results": [],
            "message": (
                "image頁がないため"
                "OCR対象外です．"
            ),
        }

    # ------------------------------------------------------------
    # 手動OCR不要頁を除外
    #
    # allow_rerun_ocr=True であっても，
    # 130_pdfOCRskip.pyで人がOCR不要と確定したページは
    # OCR対象へ戻さない．
    # ------------------------------------------------------------
    ocr_candidate_rows = [
        row
        for row in image_rows
        if not is_report_manual_ocr_skip(
            row
        )
    ]

    # ------------------------------------------------------------
    # OCR済み除外
    # ------------------------------------------------------------
    if bool(allow_rerun_ocr):
        target_rows = list(
            ocr_candidate_rows
        )
    else:
        target_rows = [
            row
            for row in ocr_candidate_rows
            if not bool(
                row.get(
                    "ocr_done",
                    False,
                )
            )
        ]

    # ------------------------------------------------------------
    # 明示的なページ指定
    # ------------------------------------------------------------
    if target_page_numbers is not None:
        target_set = {
            int(page_no)
            for page_no
            in target_page_numbers
        }

        target_rows = [
            row
            for row in target_rows
            if int(
                row.get(
                    "page_no",
                    0,
                )
                or 0
            )
            in target_set
        ]

    # ------------------------------------------------------------
    # ページ指定なし
    # ------------------------------------------------------------
    else:
        target_rows = target_rows[
            :max(
                1,
                int(max_pages_per_run),
            )
        ]

    if not target_rows:
        return {
            "status": "skip",
            "processed_pages": [],
            "ocr_pages": [],
            "blank_pages": [],
            "hallucination_pages": [],
            "hallucination_results": [],
            "ai_results": [],
            "message": (
                "指定されたimage頁に"
                "OCR対象ページがありません．"
            ),
        }

    processed_pages: list[int] = []

    # ------------------------------------------------------------
    # 処理結果内訳
    # ------------------------------------------------------------
    ocr_pages: list[int] = []
    blank_pages: list[int] = []
    hallucination_pages: list[int] = []
    hallucination_results: list[dict[str, Any]] = []

    all_ai_results: list[Any] = []

    total_target = len(
        target_rows
    )

    for index, row in enumerate(
        target_rows,
        start=1,
    ):
        page_no = int(
            row.get(
                "page_no",
                0,
            )
            or 0
        )

        preview_result = (
            run_image_page_ocr_preview_v2(
                projects_root,
                project_year=int(
                    project_year
                ),
                project_no=str(
                    project_no
                ),
                page_no=page_no,
                method=str(method),
                gpt_model=str(
                    gpt_model
                ),
                gpt_max_output_tokens=int(
                    gpt_max_output_tokens
                ),
                ocr_lang=str(
                    ocr_lang
                ),
                s3_ratio_threshold=float(
                    s3_ratio_threshold
                ),
                gpt_prompt=gpt_prompt,
            )
        )



        # --------------------------------------------------------
        # 白紙ページ
        # --------------------------------------------------------
        if bool(preview_result.get("is_blank", False)):
            mark_image_page_blank_v2(
                projects_root,
                project_year=int(project_year),
                project_no=str(project_no),
                page_no=page_no,
                done_by=str(done_by),
            )

            blank_pages.append(page_no)

        # --------------------------------------------------------
        # ハルシネーション疑い
        #
        # OCR結果はreport_pages.jsonへ保存しない．
        # ocr_doneにもせず，人手確認対象として残す．
        # 判定理由も一括OCR結果へ保持する．
        # --------------------------------------------------------
        elif bool(
            preview_result.get(
                "hallucination_suspected",
                False,
            )
        ):
            reason = str(
                preview_result.get("hallucination_reason", "") or ""
            )
            content_dark_pixels = int(
                preview_result.get("content_dark_pixels", 0) or 0
            )
            ocr_char_count = int(
                preview_result.get("ocr_char_count", 0) or 0
            )

            hallucination_pages.append(page_no)
            hallucination_results.append(
                {
                    "page_no": page_no,
                    "reason": reason,
                    "content_dark_pixels": content_dark_pixels,
                    "ocr_char_count": ocr_char_count,
                }
            )

            append_hallucination_log(
                log_path=_get_report_hallucination_log_path(
                    projects_root,
                    project_year=int(project_year),
                    project_no=str(project_no),
                ),
                document_type="report",
                project_year=int(project_year),
                project_no=str(project_no),
                page_no=page_no,
                method=str(method),
                model=str(gpt_model),
                reason=reason,
                content_dark_pixels=content_dark_pixels,
                ocr_char_count=ocr_char_count,
                detected_by=str(done_by),
            )       


        # --------------------------------------------------------
        # 通常ページ
        # --------------------------------------------------------
        else:
            apply_image_page_ocr_result_v2(
                projects_root,
                project_year=int(project_year),
                project_no=str(project_no),
                page_no=page_no,
                text=str(
                    preview_result.get("clean_text", "")
                    or ""
                ),
                done_by=str(done_by),
                method=str(method),
            )

            ocr_pages.append(page_no)     

        if not bool(
            preview_result.get(
                "hallucination_suspected",
                False,
            )
        ):
            processed_pages.append(page_no)

        all_ai_results.extend(
            list(
                preview_result.get(
                    "ai_results",
                    [],
                )
                or []
            )
        )

        if progress_callback is not None:
            progress_callback(
                page_no,
                index,
                total_target,
            )

    status = get_image_ocr_status(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
    )

    return {
        "status": "ok",

        "processed_pages": (
            processed_pages
        ),

        "ocr_pages": (
            ocr_pages
        ),

        "blank_pages": (
            blank_pages
        ),

        "hallucination_pages": (
            hallucination_pages
        ),

        "hallucination_results": (
            hallucination_results
        ),

        "ai_results": (
            all_ai_results
        ),

        "ocr_done": bool(
            status.get(
                "ocr_done",
                False,
            )
        ),

        "next_page": status.get(
            "next_page"
        ),

        "message": (
            f"処理：{len(processed_pages):,}ページ ／ "
            f"OCR：{len(ocr_pages):,}ページ ／ "
            f"白紙スキップ：{len(blank_pages):,}ページ ／ "
            f"ハルシネーション疑い："
            f"{len(hallucination_pages):,}ページ"
        ),
    }