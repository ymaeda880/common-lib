# -*- coding: utf-8 -*-
# common_lib/ai/tasks/image.py
# ============================================================
# 画像生成 task wrapper
#
# 機能：
# - routing.py から呼ばれる provider 別 wrapper
# - provider 実装への薄い委譲のみを行う
# ============================================================

from __future__ import annotations

from typing import Any, Dict, Optional

from ..types import ImageResult


# ============================================================
# OpenAI 画像生成
# ============================================================
def openai_generate_image(
    *,
    model: str,
    prompt: str,
    size: str,
    n: int,
    extra: Optional[Dict[str, Any]],
) -> ImageResult:
    from ..providers.openai.image_generate import generate_image

    return generate_image(
        model=model,
        prompt=prompt,
        size=size,
        n=n,
        extra=extra,
    )


# ============================================================
# OpenAI 画像編集
# ============================================================
def openai_edit_image(
    *,
    model: str,
    prompt: str,
    image_bytes: bytes,
    size: str,
    extra: Optional[Dict[str, Any]],
) -> ImageResult:
    from ..providers.openai.image_edit import edit_image

    return edit_image(
        model=model,
        prompt=prompt,
        image_bytes=image_bytes,
        size=size,
        extra=extra,
    )


# ============================================================
# Gemini 画像生成
# ============================================================
def gemini_generate_image(
    *,
    model: str,
    prompt: str,
    size: str,
    n: int,
    extra: Optional[Dict[str, Any]],
) -> ImageResult:
    from ..providers.gemini.image_generate import generate_image

    return generate_image(
        model=model,
        prompt=prompt,
        size=size,
        n=n,
        extra=extra,
    )


# ============================================================
# Gemini 画像編集
# ============================================================
def gemini_edit_image(
    *,
    model: str,
    prompt: str,
    image_bytes: bytes,
    size: str,
    extra: Optional[Dict[str, Any]],
) -> ImageResult:
    from ..providers.gemini.image_edit import edit_image

    return edit_image(
        model=model,
        prompt=prompt,
        image_bytes=image_bytes,
        size=size,
        extra=extra,
    )