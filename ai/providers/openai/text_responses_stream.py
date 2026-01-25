# -*- coding: utf-8 -*-
# common_lib/ai/providers/openai/text_responses_stream.py
# ============================================================
# OpenAI Responses API stream（正本）
# - delta を yield
# - 最後に final response（usage付き）を generator return で返す
#   ※呼び手は StopIteration.value で受け取れる
# ============================================================

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from ...errors import ProviderError
from .client import get_client


def stream_responses(
    *,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Iterator[str]:
    """
    ストリーム実装：
      - 文字列 delta を順に yield
      - 最後に final response（usage付き）を generator return で返す

    使う側（例）：
      gen = stream_responses(...)
      try:
          for piece in gen:
              ...
      except StopIteration as si:
          final_res = si.value
    """
    client = get_client()

    # ------------------------------------------------------------
    # input messages
    # ------------------------------------------------------------
    input_messages = []
    if system and str(system).strip():
        input_messages.append({"role": "system", "content": str(system).strip()})
    input_messages.append({"role": "user", "content": str(prompt)})

    # ------------------------------------------------------------
    # kwargs
    # ------------------------------------------------------------
    kwargs: Dict[str, Any] = {}
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = int(max_output_tokens)
    if extra:
        kwargs.update(extra)

    # ------------------------------------------------------------
    # stream
    # ------------------------------------------------------------
    try:
        with client.responses.stream(model=model, input=input_messages, **kwargs) as stream:
            for event in stream:
                # event.delta っぽいものがある場合
                delta = getattr(event, "delta", None)
                if isinstance(delta, str) and delta:
                    yield delta
                    continue

                # それ以外（SDK差）: output_text を拾う
                ot = getattr(event, "output_text", None)
                if isinstance(ot, str) and ot:
                    yield ot

            # ----------------------------------------------------
            # ここが重要：final response（usage付き）
            # ----------------------------------------------------
            final_res = None
            try:
                final_res = getattr(stream, "get_final_response", None)
                if callable(final_res):
                    final_res = stream.get_final_response()
            except Exception:
                final_res = None

            return final_res  # StopIteration.value

    except Exception as e:
        raise ProviderError(f"OpenAI responses.stream failed: {e}", provider="openai") from e
