# -*- coding: utf-8 -*-
# common_lib/io/normalize.py
# ============================================================
# 前提文書の正規化（UI非依存）
# - 改行正規化
# - 最大文字数カット
# ============================================================

from __future__ import annotations

from typing import Tuple

from common_lib.io.text import normalize_newlines


# ============================================================
# 正規化（共通）
# ============================================================
def normalize_context_text(
    text: str,
    *,
    max_chars: int,
) -> Tuple[str, bool]:
    """
    前提文書としての共通正規化。

    - 改行を LF に統一
    - 最大文字数で先頭からカット

    Returns
    -------
    (normalized_text, truncated)
    """
    # ------------------------------------------------------------
    # normalize newlines
    # ------------------------------------------------------------
    t = normalize_newlines(text or "")

    # ------------------------------------------------------------
    # truncate
    # ------------------------------------------------------------
    if max_chars and max_chars > 0 and len(t) > max_chars:
        return t[:max_chars], True

    return t, False
