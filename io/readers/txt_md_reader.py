# -*- coding: utf-8 -*-
# common_lib/io/readers/txt_md_reader.py
# ============================================================
# .txt / .md reader（UI非依存）
# - bytes -> str（decode正本） -> text
# ============================================================

from __future__ import annotations

from typing import Tuple

from common_lib.io.decode import decode_bytes_to_text


# ============================================================
# reader
# ============================================================
def read_txt_or_md_bytes(data: bytes) -> Tuple[str, str]:
    """
    .txt / .md の bytes をテキスト化する。

    Returns
    -------
    (text, decode_strategy)
    """
    text, strategy = decode_bytes_to_text(data)
    return text, strategy
