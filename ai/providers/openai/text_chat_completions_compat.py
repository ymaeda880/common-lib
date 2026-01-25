# -*- coding: utf-8 -*-
# common_lib/ai/providers/openai/text_chat_completions_compat.py

from __future__ import annotations

from typing import Any, Dict, Optional

from ...types import TextResult, UsageSummary
from ...errors import ProviderError, InvalidResponseError

from .client import get_client


def call_chat_completions_create(
    *,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> TextResult:
    client = get_client()

    messages = []
    if system and str(system).strip():
        messages.append({"role": "system", "content": str(system).strip()})
    messages.append({"role": "user", "content": str(prompt)})

    kwargs: Dict[str, Any] = {}
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    if max_output_tokens is not None:
        kwargs["max_tokens"] = int(max_output_tokens)
    if extra:
        kwargs.update(extra)

    try:
        res = client.chat.completions.create(model=model, messages=messages, **kwargs)
    except Exception as e:
        raise ProviderError(f"OpenAI chat.completions.create failed: {e}", provider="openai") from e

    try:
        text = res.choices[0].message.content or ""
    except Exception as e:
        raise InvalidResponseError("OpenAI chat.completions: choices[0].message.content が取得できません") from e

    usage_obj = getattr(res, "usage", None)
    usage = UsageSummary(
        input_tokens=int(getattr(usage_obj, "prompt_tokens", 0)) if usage_obj else None,
        output_tokens=int(getattr(usage_obj, "completion_tokens", 0)) if usage_obj else None,
        total_tokens=int(getattr(usage_obj, "total_tokens", 0)) if usage_obj else None,
        raw=None,
    )

    return TextResult(provider="openai", model=model, text=str(text), usage=usage, raw=None)
