# -*- coding: utf-8 -*-
# common_lib/io/doc_context.py
# ============================================================
# 文書コンテキスト（前提文書）正本API（UI非依存）
# - pages 側の拡張子分岐・デコード・抽出を common_lib に集約
# - 戻り値は DocContext（kind/text/meta）
# ============================================================

from __future__ import annotations

from dataclasses import replace
from typing import Optional, Tuple

from common_lib.io.doc_context_types import DocContext, DocContextMeta
from common_lib.io.normalize import normalize_context_text

from common_lib.io.readers.txt_md_reader import read_txt_or_md_bytes
from common_lib.io.readers.json_reader import read_json_bytes_pretty
from common_lib.io.readers.docx_reader import read_docx_bytes_paragraphs
from common_lib.io.readers.pdf_reader import read_pdf_bytes_text_only
from common_lib.io.readers.pdf_policy import PdfPolicy


# ============================================================
# helpers（拡張子）
# ============================================================
def _split_ext(file_name: str) -> str:
    if not file_name:
        return ""
    s = file_name.strip().lower()
    if "." not in s:
        return ""
    return s.rsplit(".", 1)[-1].strip()


# ============================================================
# helpers（kind）
# ============================================================
def _kind_from_ext(ext: str) -> str:
    if ext == "docx":
        return "Word(.docx)"
    if ext in ("txt", "md"):
        return f"テキストファイル（.{ext}）"
    if ext == "json":
        return "JSONファイル（.json）"
    if ext == "pdf":
        return "PDFファイル（.pdf）"
    return f"不明形式（.{ext or 'unknown'}）"


# ============================================================
# 高レベルAPI：bytes入力（正本）
# ============================================================
def read_doc_context_from_bytes(
    *,
    file_name: str,
    data: bytes,
    max_chars: int = 15000,
    pdf_policy: Optional[PdfPolicy] = None,
) -> DocContext:
    """
    ファイル（bytes）から前提文書を作る（正本）。

    方針：
    - 形式別 reader で text を抽出
    - 共通正規化（改行/最大文字数カット）
    - meta を確定して DocContext を返す
    """
    # ------------------------------------------------------------
    # init meta
    # ------------------------------------------------------------
    ext = _split_ext(file_name)
    kind = _kind_from_ext(ext)

    meta = DocContextMeta(
        source_name=file_name or "",
        source_ext=ext,
        extracted_chars=0,
        truncated=False,
        max_chars=int(max_chars),
        warnings=[],
        deps_missing=[],
        decode_strategy="",
        json_pretty=None,
        json_parse_error=None,
        docx_mode=None,
        pdf_mode=None,
        pdf_text_extracted_chars=None,
        pdf_seems_image_based=None,
        pdf_text_threshold=None,
        ocr_supported=None,
    )

    # ------------------------------------------------------------
    # route by ext
    # ------------------------------------------------------------
    raw_text = ""
    if ext in ("txt", "md"):
        raw_text, strategy = read_txt_or_md_bytes(data)
        meta = replace(meta, decode_strategy=strategy)

    elif ext == "json":
        try:
            raw_text, strategy = read_json_bytes_pretty(data)
            meta = replace(meta, decode_strategy=strategy, json_pretty=True, json_parse_error=False)
        except Exception as e:
            # 正本：厳格（パースできないJSONはエラー）
            meta = replace(meta, json_pretty=False, json_parse_error=True)
            raise RuntimeError(f"JSON の読み込みに失敗しました: {e}") from e

    elif ext == "docx":
        try:
            raw_text, mode = read_docx_bytes_paragraphs(data)
            meta = replace(meta, docx_mode=mode)
            if mode == "paragraphs":
                meta = replace(meta, warnings=[*meta.warnings, "docx_tables_not_included"])
        except Exception as e:
            # 依存不足など
            msg = str(e)
            if "python-docx" in msg or "docx" in msg.lower():
                meta = replace(meta, deps_missing=[*meta.deps_missing, "python-docx"])
            raise

    elif ext == "pdf":
        pol = pdf_policy or PdfPolicy(text_threshold=50, ocr_supported=False)
        meta = replace(
            meta,
            pdf_mode="text_only",
            pdf_text_threshold=int(pol.text_threshold),
            ocr_supported=bool(pol.ocr_supported),
        )
        try:
            raw_text, extracted_chars, _ = read_pdf_bytes_text_only(data, policy=pol)
            meta = replace(meta, pdf_text_extracted_chars=int(extracted_chars), pdf_seems_image_based=False)
        except Exception as e:
            # B案：画像PDF扱いで明示エラー（metaにも残す）
            meta = replace(meta, pdf_text_extracted_chars=0, pdf_seems_image_based=True)
            raise RuntimeError(str(e)) from e

    else:
        raise RuntimeError(f"未対応のファイル形式です: .{ext or 'unknown'}")

    # ------------------------------------------------------------
    # normalize（改行/最大文字数）
    # ------------------------------------------------------------
    normalized, truncated = normalize_context_text(raw_text, max_chars=int(max_chars))
    meta = replace(meta, extracted_chars=len(normalized), truncated=bool(truncated))

    # ------------------------------------------------------------
    # empty guard（静かに空にしない）
    # ------------------------------------------------------------
    if not (normalized or "").strip():
        raise RuntimeError("前提文書として扱えるテキストが空でした。別のファイルを選択してください。")

    return DocContext(kind=kind, text=normalized, meta=meta)


# ============================================================
# 高レベルAPI：貼り付け入力（正本）
# ============================================================
def read_doc_context_from_text(
    *,
    raw_text: str,
    max_chars: int = 15000,
    kind: str = "貼り付けテキスト",
) -> DocContext:
    """
    貼り付けテキストから前提文書を作る（正本）。
    """
    meta = DocContextMeta(
        source_name="pasted",
        source_ext="",
        extracted_chars=0,
        truncated=False,
        max_chars=int(max_chars),
        warnings=[],
    )

    normalized, truncated = normalize_context_text(raw_text or "", max_chars=int(max_chars))
    meta = replace(meta, extracted_chars=len(normalized), truncated=bool(truncated))

    if not (normalized or "").strip():
        raise RuntimeError("貼り付けテキストが空です。")

    return DocContext(kind=kind, text=normalized, meta=meta)
