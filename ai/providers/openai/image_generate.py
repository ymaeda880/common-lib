# -*- coding: utf-8 -*-
# common_lib/ai/providers/openai/image_generate.py

from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from ...types import ImageResult
from ...errors import ProviderError, InvalidResponseError

from .client import get_client


def generate_image(
    *,
    model: str,
    prompt: str,
    size: str,
    n: int = 1,
    extra: Optional[Dict[str, Any]] = None,
) -> ImageResult:
    """
    OpenAI images.generate（gpt-image-1 等）
    戻り値は image_bytes 優先。url のみの場合は image_url を返す。
    """
    client = get_client()

    try:
        res = client.images.generate(
            model=model,
            prompt=prompt,
            n=int(n),
            size=size,
            **(extra or {}),
        )
    except Exception as e:
        raise ProviderError(
            f"OpenAI images.generate failed: {e}",
            provider="openai",
        ) from e

    try:
        d0 = res.data[0]
    except Exception as e:
        raise InvalidResponseError("OpenAI images.generate: data[0] が取得できません") from e

    b64_json = getattr(d0, "b64_json", None)
    url = getattr(d0, "url", None)

    if b64_json:
        try:
            img_bytes = base64.b64decode(b64_json)
        except Exception as e:
            raise InvalidResponseError("OpenAI images.generate: b64_json decode failed") from e
        return ImageResult(provider="openai", model=model, image_bytes=img_bytes, raw={"size": size, "n": n})

    if url:
        return ImageResult(provider="openai", model=model, image_url=str(url), raw={"size": size, "n": n})

    raise InvalidResponseError("OpenAI images.generate: b64_json/url のいずれも見つかりません")
