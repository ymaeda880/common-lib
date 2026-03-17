# common_lib/pdf_tools/text_extract/__init__.py
# ============================================================
# PDF text extract（共通ライブラリ）
#
# 役割：
# - ページ側からの import を簡潔にする re-export
# ============================================================

from __future__ import annotations

# ============================================================
# re-export: fitz guard
# ============================================================
from .fitz_guard import FitzImportResult, try_import_fitz

# ============================================================
# re-export: utils
# ============================================================
from .utils import sha256_bytes, build_txt_filename

# ============================================================
# re-export: detect / extract
# ============================================================
from .detect import detect_pdf_kind_from_bytes
from .extract import (
    extract_text_direct,
    extract_text_with_ocr,
    build_ocr_pdf_bytes,
    extract_text_from_pdf_bytes,
)

# ============================================================
# re-export: models
# ============================================================
from .models import ExtractMeta