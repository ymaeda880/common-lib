"""終了情報を返す追加の呼出し口。既存routing.call_textは切り替えない。"""
from __future__ import annotations

from typing import Any
from .errors import InvalidRequestError
from .types import Provider, TextResult


def call_text_with_status(
    *, provider: Provider, model: str, prompt: str, system: str | None = None,
    temperature: float | None = None, max_output_tokens: int | None = None,
    extra: dict[str, Any] | None = None,
) -> TextResult:
    if not prompt or not str(prompt).strip():
        raise InvalidRequestError("prompt is empty")
    kwargs = dict(model=model, prompt=prompt, system=system, temperature=temperature,
                  max_output_tokens=max_output_tokens, extra=extra)
    if provider == "azure":
        # 既存のAzure実装はrawとAzure単価でのcostを返すので、そのまま利用。
        from .routing import call_text
        return call_text(provider=provider, **kwargs)
    if provider == "openai":
        from .providers.openai.text_responses_create_with_status import call_responses_create
        result = call_responses_create(**kwargs)
    elif provider == "gemini":
        from .providers.gemini.text_generate_with_status import generate_text
        result = generate_text(**kwargs)
    else:
        raise InvalidRequestError(f"unknown provider: {provider}")
    from .tasks.text import _fill_text_cost_if_missing
    return _fill_text_cost_if_missing(res=result, model=str(model))
