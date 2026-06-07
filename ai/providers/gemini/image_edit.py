# -*- coding: utf-8 -*-
# common_lib/ai/providers/gemini/image_edit.py
# ============================================================
# Gemini 画像編集 provider
#
# 機能：
# - 入力画像 bytes + prompt を Gemini に渡して画像編集する
# - ImageResult.image_bytes に PNG bytes を返す
# ============================================================

from __future__ import annotations

from typing import Any, Dict, Optional

from ...types import ImageResult
from ...errors import ProviderError

from .client import configure_gemini
from .image_utils import extract_image_bytes_from_response


# ============================================================
# Gemini 画像編集
# ============================================================
def edit_image(
    *,
    model: str,
    prompt: str,
    image_bytes: bytes,
    size: str,
    extra: Optional[Dict[str, Any]],
) -> ImageResult:
    client = configure_gemini()

    try:
        from google.genai import types  # type: ignore

        _ = size
        _ = extra

        cfg = types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        )

        resp = client.models.generate_content(
            model=model,
            contents=[
                str(prompt),
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/png",
                ),
            ],
            config=cfg,
        )

        out_bytes = extract_image_bytes_from_response(resp)

    except Exception as e:
        raise ProviderError(f"Gemini image edit failed: {e}", provider="gemini") from e

    return ImageResult(
        provider="gemini",
        model=model,
        image_bytes=out_bytes,
        image_url=None,
        cost=None,
        raw=None,
    )