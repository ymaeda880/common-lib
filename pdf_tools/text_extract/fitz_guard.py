# common_lib/pdf_tools/text_extract/fitz_guard.py
# ============================================================
# PDF text extract（共通ライブラリ）
#
# 機能：
# - PyMuPDF（fitz）の import を安全に行う
# - 利用不能時はエラー情報を返す（ページ側でガード表示する想定）
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from dataclasses import dataclass
from typing import Any, Optional


# ============================================================
# public result
# ============================================================
@dataclass(frozen=True)
class FitzImportResult:
    ok: bool
    fitz: Optional[Any]
    error: Optional[BaseException]


# ============================================================
# public api
# ============================================================
def try_import_fitz() -> FitzImportResult:
    """
    PyMuPDF（fitz）を import して返す。
    - ok=True なら fitz が利用可能
    - ok=False なら error に例外が入る
    """
    try:
        import fitz  # type: ignore
    except Exception as e:  # noqa: BLE001
        return FitzImportResult(ok=False, fitz=None, error=e)
    return FitzImportResult(ok=True, fitz=fitz, error=None)