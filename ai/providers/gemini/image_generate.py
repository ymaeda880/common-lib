# -*- coding: utf-8 -*-
# common_lib/ai/providers/gemini/image_generate.py
# ============================================================
# Gemini 画像生成 provider
#
# 機能：
# - google-genai Client を使って画像生成する
# - auth_portal_app/.streamlit/secrets.toml の GEMINI_API_KEY を使用
# - ImageResult.image_bytes に PNG bytes を返す
# ============================================================

from __future__ import annotations

from typing import Any, Dict, Optional

from ...types import ImageResult
from ...errors import ProviderError

from .client import configure_gemini
from .image_utils import extract_image_bytes_from_response


# ============================================================
# Gemini 画像生成
# ============================================================
def generate_image(
    *,
    model: str,
    prompt: str,
    size: str,
    n: int,
    extra: Optional[Dict[str, Any]],
) -> ImageResult:
    client = configure_gemini()

    try:
        from google.genai import types  # type: ignore

        _ = size
        _ = n
        _ = extra

        cfg = types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        )

        resp = client.models.generate_content(
            model=model,
            contents=[str(prompt)],
            config=cfg,
        )

        image_bytes = extract_image_bytes_from_response(resp)

    except Exception as e:
        raise ProviderError(f"Gemini image generate failed: {e}", provider="gemini") from e

    return ImageResult(
        provider="gemini",
        model=model,
        image_bytes=image_bytes,
        image_url=None,
        cost=None,
        raw=None,
    )