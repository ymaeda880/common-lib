# -*- coding: utf-8 -*-
# common_lib/io/text.py
# ------------------------------------------------------------
# 📄 テキストI/Oユーティリティ（text専用）
# - bytes / file-like object を安全に str に変換
# - UI 非依存（common_lib 正本）
# ------------------------------------------------------------

from __future__ import annotations
from typing import Union, IO


# ------------------------------------------------------------
# 改行正規化
# ------------------------------------------------------------
def normalize_newlines(text: str) -> str:
    """
    改行コードを LF に正規化する。
    """
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ------------------------------------------------------------
# .txt 読み込み（エンコード自動判定）
# ------------------------------------------------------------
def read_txt(
    file_or_bytes: Union[bytes, bytearray, IO[bytes]],
    *,
    errors_fallback: str = "ignore",
) -> str:
    """
    .txt を文字列として読み込む。

    - bytes / bytearray
    - .read() を持つ file-like object（Streamlit UploadedFile 等）

    Returns
    -------
    str
    """
    if isinstance(file_or_bytes, (bytes, bytearray)):
        data = bytes(file_or_bytes)
    else:
        data = file_or_bytes.read()

    for enc in ("utf-8", "utf-16", "shift_jis", "cp932"):
        try:
            return normalize_newlines(data.decode(enc))
        except Exception:
            continue

    # 最終フォールバック
    return normalize_newlines(data.decode("utf-8", errors=errors_fallback))
