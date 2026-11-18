# -*- coding: utf-8 -*-
# common_lib/ai/providers/openai/text_responses_create_with_status.py
# 既存ファイルのコピー。終了理由・使用量を返し、業務側で記録後に完了確認する。

from __future__ import annotations

from typing import Any, Dict, Optional

from ...types import TextResult, UsageSummary
from ...errors import ProviderError

from .client import get_client


def _extract_text(res: Any) -> str:
    # openai SDK によって取り出し方が変わるため、いくつか試す
    t = getattr(res, "output_text", None)
    if isinstance(t, str) and t:
        return t

    # fallback: output array を舐める（最低限）
    out = getattr(res, "output", None)
    if isinstance(out, list):
        parts: list[str] = []
        for item in out:
            # item.content があるケースなど
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for c in content:
                    text = getattr(c, "text", None)
                    if isinstance(text, str):
                        parts.append(text)
        if parts:
            return "".join(parts)

    # 本文がなくても使用量と終了理由を上位へ返す。
    return ""


def _completion_metadata(res: Any) -> Dict[str, Any]:
    def pick(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

    details = pick(res, "incomplete_details")
    refusal = ""
    for item in pick(res, "output", []) or []:
        for content in pick(item, "content", []) or []:
            if pick(content, "type") == "refusal":
                refusal = str(pick(content, "refusal", "") or "refusal")
    return {
        "status": pick(res, "status"),
        "incomplete_details": {"reason": pick(details, "reason")},
        "refusal": refusal,
    }



def _extract_usage(res: Any) -> UsageSummary:
    usage = getattr(res, "usage", None)
    if not usage:
        return UsageSummary()

    # SDKによって field 名が変わりうるので雑に拾う
    in_tok = getattr(usage, "input_tokens", None)
    out_tok = getattr(usage, "output_tokens", None)
    tot = getattr(usage, "total_tokens", None)

    def _to_int(x):
        try:
            return int(x) if x is not None else None
        except Exception:
            return None

    return UsageSummary(
        input_tokens=_to_int(in_tok),
        output_tokens=_to_int(out_tok),
        total_tokens=_to_int(tot),
        raw=None,
    )


def call_responses_create(
    *,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> TextResult:
    client = get_client()

    # Responses API は input に message list を渡せる想定
    input_messages = []
    if system and str(system).strip():
        input_messages.append({"role": "system", "content": str(system).strip()})
    input_messages.append({"role": "user", "content": str(prompt)})

    kwargs: Dict[str, Any] = {}
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = int(max_output_tokens)
    if extra:
        kwargs.update(extra)

    try:
        res = client.responses.create(
            model=model,
            input=input_messages,
            **kwargs,
        )
    except Exception as e:
        raise ProviderError(f"OpenAI responses.create failed: {e}", provider="openai") from e

    text = _extract_text(res)
    usage = _extract_usage(res)

    return TextResult(
        provider="openai",
        model=model,
        text=text,
        usage=usage,
        raw=_completion_metadata(res),
    )
