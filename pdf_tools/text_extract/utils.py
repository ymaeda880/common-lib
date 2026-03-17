# common_lib/pdf_tools/text_extract/utils.py
# ============================================================
# PDF text extract（共通ライブラリ）
#
# 機能：
# - sha256（アップロード差し替え検知）
# - txt ダウンロードファイル名生成
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import datetime as dt
import hashlib
from pathlib import Path


# ============================================================
# public api（hash）
# ============================================================
def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


# ============================================================
# public api（download filename）
# ============================================================
def build_txt_filename(original_name: str) -> str:
    stem = Path(str(original_name or "extracted")).stem
    today = dt.date.today().strftime("%Y%m%d")
    return f"{stem}_extracted_{today}.txt"