# -*- coding: utf-8 -*-
# common_lib/pdf_ops/analyze_ops.py
# ============================================================
# PDF解析（710から切り出し）
# ============================================================

from __future__ import annotations

from pathlib import Path

# ============================================================
# pdf_tools（既存正本）
# ============================================================
from common_lib.pdf_tools.text_extract.fitz_guard import (
    try_import_fitz,
)
from common_lib.pdf_tools.text_extract.detect import (
    detect_pdf_kind_from_bytes,
)
from common_lib.pdf_tools.text_extract.extract import (
    extract_text_direct,
)
from common_lib.pdf_tools.pages_json import (
    create_raw_pages_json,
)


# ============================================================
# helpers（PDF判定 / text抽出）
# ============================================================
def classify_pdf_and_extract_page_texts(pdf_path: Path):
    # ------------------------------------------------------------
    # PDF種別判定 + ページ数 + ページ別テキスト抽出
    # 710からそのまま移植
    # ------------------------------------------------------------
    fitz_res = try_import_fitz()
    if (not fitz_res.ok) or (fitz_res.fitz is None):
        raise RuntimeError(
            f"PyMuPDF（fitz）が利用できません。 import error: {fitz_res.error}"
        )

    fitz = fitz_res.fitz
    pdf_bytes = pdf_path.read_bytes()

    pdf_kind, page_count = detect_pdf_kind_from_bytes(
        fitz=fitz,
        pdf_bytes=pdf_bytes,
        sample_pages=3,
        min_text_chars=40,
    )

    page_texts: list[str] = []

    for page_idx in range(int(page_count)):
        one_page_text = extract_text_direct(
            fitz=fitz,
            pdf_bytes=pdf_bytes,
            page_start_0=int(page_idx),
            page_end_0_inclusive=int(page_idx),
        )
        page_texts.append(str(one_page_text or ""))

    return fitz, pdf_bytes, str(pdf_kind or ""), int(page_count), page_texts


# ============================================================
# helpers（raw出力）
# ============================================================
def write_raw_text_outputs(
    *,
    raw_path: Path,
    raw_pages_path: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    pdf_filename: str,
    source_pdf_sha256: str,
    raw_text: str,
    page_texts: list[str],
) -> None:
    # ------------------------------------------------------------
    # raw text / raw pages json を保存
    # 710からそのまま移植（pathは外から渡す）
    # ------------------------------------------------------------
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(str(raw_text or ""), encoding="utf-8")

    create_raw_pages_json(
        raw_pages_path,
        collection_id=str(collection_id),
        shard_id=str(shard_id),
        doc_id=str(doc_id),
        pdf_filename=str(pdf_filename),
        source_pdf_sha256=str(source_pdf_sha256),
        pages_text_list=page_texts,
    )