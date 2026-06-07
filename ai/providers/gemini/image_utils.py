# -*- coding: utf-8 -*-
# common_lib/ai/providers/gemini/image_utils.py
# ============================================================
# Gemini 画像レスポンス共通ユーティリティ
#
# 機能：
# - google-genai の generate_content response から画像 bytes を抽出する
# - resp.parts / resp.candidates[].content.parts の両方に対応する
# - PNG bytes に統一して返す
# ============================================================

from __future__ import annotations

from io import BytesIO
from typing import Any


# ============================================================
# response から画像 bytes を抽出
# ============================================================
def extract_image_bytes_from_response(resp: Any) -> bytes:
    # ------------------------------------------------------------
    # parts 候補を収集
    # ------------------------------------------------------------
    parts_list = []

    direct_parts = getattr(resp, "parts", None)
    if direct_parts:
        parts_list.extend(list(direct_parts))

    candidates = getattr(resp, "candidates", None) or []

    for cand in candidates:
        content = getattr(cand, "content", None)
        cand_parts = getattr(content, "parts", None) if content is not None else None

        if cand_parts:
            parts_list.extend(list(cand_parts))

    # ------------------------------------------------------------
    # 画像 bytes を抽出
    # ------------------------------------------------------------
    for part in parts_list:
        try:
            image = part.as_image()
            if image is not None:
                buf = BytesIO()
                image.save(buf, format="PNG")
                return buf.getvalue()
        except Exception:
            pass

        inline_data = getattr(part, "inline_data", None)
        data = getattr(inline_data, "data", None) if inline_data is not None else None

        if data:
            return bytes(data)

    raise RuntimeError("Gemini response に画像データが含まれていません。")