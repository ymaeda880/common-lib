# -*- coding: utf-8 -*-
# common_lib/ai/providers/openai/image_edit.py

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, Dict, Optional

from ...types import ImageResult
from ...errors import ProviderError, InvalidResponseError

from .client import get_client


def edit_image(
    *,
    model: str,
    prompt: str,
    image_bytes: bytes,
    size: str,
    extra: Optional[Dict[str, Any]] = None,
) -> ImageResult:
    """
    OpenAI images.edit（gpt-image-1 等）
    入力画像は bytes。SDK には file-like を渡す。
    """
    client = get_client()

    bio = BytesIO(image_bytes)
    bio.name = "image.png"  # type: ignore[attr-defined]  # 一部実装で name を参照するため

    try:
        res = client.images.edit(
            model=model,
            image=("image.png", bio),
            prompt=prompt,
            size=size,
            **(extra or {}),
        )
    except Exception as e:
        raise ProviderError(
            f"OpenAI images.edit failed: {e}",
            provider="openai",
        ) from e

    try:
        d0 = res.data[0]
    except Exception as e:
        raise InvalidResponseError("OpenAI images.edit: data[0] が取得できません") from e

    b64_json = getattr(d0, "b64_json", None)
    url = getattr(d0, "url", None)

    if b64_json:
        try:
            out_bytes = base64.b64decode(b64_json)
        except Exception as e:
            raise InvalidResponseError("OpenAI images.edit: b64_json decode failed") from e
        return ImageResult(provider="openai", model=model, image_bytes=out_bytes, raw={"size": size})

    if url:
        return ImageResult(provider="openai", model=model, image_url=str(url), raw={"size": size})

    raise InvalidResponseError("OpenAI images.edit: b64_json/url のいずれも見つかりません")
