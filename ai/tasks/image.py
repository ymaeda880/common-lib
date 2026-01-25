# -*- coding: utf-8 -*-
# common_lib/ai/tasks/image.py

from __future__ import annotations

from typing import Any, Dict, Optional

from ..types import ImageResult


def openai_generate_image(
    *,
    model: str,
    prompt: str,
    size: str,
    n: int,
    extra: Optional[Dict[str, Any]],
) -> ImageResult:
    from ..providers.openai.image_generate import generate_image
    return generate_image(model=model, prompt=prompt, size=size, n=n, extra=extra)


def openai_edit_image(
    *,
    model: str,
    prompt: str,
    image_bytes: bytes,
    size: str,
    extra: Optional[Dict[str, Any]],
) -> ImageResult:
    from ..providers.openai.image_edit import edit_image
    return edit_image(model=model, prompt=prompt, image_bytes=image_bytes, size=size, extra=extra)
