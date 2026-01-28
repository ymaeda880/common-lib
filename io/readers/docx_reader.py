# -*- coding: utf-8 -*-
# common_lib/io/readers/docx_reader.py
# ============================================================
# .docx reader（UI非依存）
# - python-docx が必要
# - 当面は paragraphs のみ抽出（表は将来拡張）
# ============================================================

from __future__ import annotations

from typing import Tuple


# ============================================================
# reader
# ============================================================
def read_docx_bytes_paragraphs(data: bytes) -> Tuple[str, str]:
    """
    .docx bytes を段落テキストとして抽出する。

    Returns
    -------
    (text, docx_mode)
      - docx_mode: "paragraphs"
    """
    # ------------------------------------------------------------
    # dependency
    # ------------------------------------------------------------
    try:
        import docx  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "`.docx` を読むには python-docx が必要です。"
            "（common_lib/io/readers/docx_reader.py）"
        ) from e

    # ------------------------------------------------------------
    # load document
    # ------------------------------------------------------------
    from io import BytesIO

    doc = docx.Document(BytesIO(data))

    # ------------------------------------------------------------
    # extract paragraphs（空段落除外）
    # ------------------------------------------------------------
    parts = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            parts.append(t)

    return "\n".join(parts), "paragraphs"
