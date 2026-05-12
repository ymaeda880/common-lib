# -*- coding: utf-8 -*-
# common_lib/ai/providers/openai/vision_responses_create.py
# ============================================================
# OpenAI Vision Text（Responses API）
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import base64
from typing import Any, Dict, Optional

# ============================================================
# types
# ============================================================
from ...types import TextResult

# ============================================================
# OpenAI client 正本
# ============================================================
from .client import get_client


# ============================================================
# helper：画像bytes → data URL
# ============================================================
def _to_png_data_url(image_bytes: bytes) -> str:
    # ------------------------------------------------------------
    # OpenAI Responses API の input_image 用 data URL
    # ------------------------------------------------------------
    if not image_bytes:
        raise RuntimeError("image_bytes is empty")

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/png;base64,{b64}"


# ============================================================
# helper：output_text 抽出
# ============================================================
def _extract_output_text(resp: Any) -> str:
    # ------------------------------------------------------------
    # SDKの output_text があればそれを使う
    # ------------------------------------------------------------
    text = getattr(resp, "output_text", None)
    if text:
        return str(text).strip()

    # ------------------------------------------------------------
    # 念のため output 配列から拾う
    # ------------------------------------------------------------
    parts: list[str] = []

    for item in getattr(resp, "output", []) or []:
        for c in getattr(item, "content", []) or []:
            t = getattr(c, "text", None)
            if t:
                parts.append(str(t))

    return "\n".join(parts).strip()


# ============================================================
# public：Vision Text
# ============================================================
def call_vision_responses_create(
    *,
    model: str,
    image_bytes: bytes,
    prompt: str,
    system: Optional[str],
    max_output_tokens: Optional[int],
    extra: Optional[Dict[str, Any]],
) -> TextResult:
    # ------------------------------------------------------------
    # OpenAI Responses API に画像＋promptを渡してテキストを得る
    # ------------------------------------------------------------
    client = get_client()

    data_url = _to_png_data_url(image_bytes)

    input_messages: list[dict[str, Any]] = []

    if system:
        input_messages.append(
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": str(system),
                    }
                ],
            }
        )

    input_messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": str(prompt),
                },
                {
                    "type": "input_image",
                    "image_url": data_url,
                    "detail": "high",
                },
            ],
        }
    )

    kwargs: dict[str, Any] = {
        "model": str(model),
        "input": input_messages,
    }

    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = int(max_output_tokens)

    if extra:
        kwargs.update(dict(extra))

    resp = client.responses.create(**kwargs)

    return TextResult(
        provider="openai",
        model=str(model),
        text=_extract_output_text(resp),
        usage=getattr(resp, "usage", None),
        cost=None,
    )