# -*- coding: utf-8 -*-
# common_lib/io/decode.py
# ============================================================
# decode 正本（UI非依存）
# - bytes -> str の統一戦略（UTF-8 BOM / replace）
# - 「静かに欠落（ignore）」を避ける
# ============================================================

from __future__ import annotations

from typing import Tuple


# ============================================================
# bytes -> str（正本）
# ============================================================
def decode_bytes_to_text(data: bytes) -> Tuple[str, str]:
    """
    bytes を str にデコードする（正本戦略）。

    方針：
    - UTF-8（BOM対応）を優先
    - 失敗時は replace を使い、欠落（ignore）を避ける

    Returns
    -------
    (text, strategy)
      - strategy: "utf-8-sig" / "utf-8-replace"
    """
    # ------------------------------------------------------------
    # UTF-8 with BOM
    # ------------------------------------------------------------
    try:
        return data.decode("utf-8-sig"), "utf-8-sig"
    except Exception:
        pass

    # ------------------------------------------------------------
    # UTF-8 replace（最終フォールバック）
    # ------------------------------------------------------------
    return data.decode("utf-8", errors="replace"), "utf-8-replace"
