# -*- coding: utf-8 -*-
# common_lib/ai/tasks/text.py
# ============================================================
# Text タスク（正本）
#
# 目的：
# - provider 実装（OpenAI / Gemini）をここに閉じ込める
# - routing.py はこの関数を呼ぶだけ
# - usage/cost は「取れた範囲のみ」詰める（ページ側では推計しない）
#
# 方針（重要）：
# - cost は res.cost が無い場合のみ、usage から計算して埋める
# - tokens 抽出の形揺れ吸収は ai/usage 正本（extract_tokens）に一本化
#   ※ estimate_chat_cost_from_usage 側が正本を利用する前提
# ============================================================

from __future__ import annotations

# ============================================================
# typing / dataclasses（正本）
# ============================================================
from typing import Any, Dict, Optional
import dataclasses

# ============================================================
# types / errors（正本）
# ============================================================
from ..types import TextResult
from ..errors import InvalidRequestError

# ============================================================
# costs（正本：estimate）
# ============================================================
from ..costs.estimate import estimate_chat_cost_from_usage


# ============================================================
# 内部：cost を埋める（共通）
# ============================================================
def _fill_text_cost_if_missing(*, res: Any, model: str) -> Any:
    """
    res.cost が無い場合のみ、usage から cost を作って埋める。
    - 推計しない：usage から tokens が取れた場合のみ cost を作る
    - pricing 未設定などは例外で表に出す（正本を直す）
    """
    # ------------------------------------------------------------
    # すでに cost があれば何もしない
    # ------------------------------------------------------------
    if getattr(res, "cost", None) is not None:
        return res

    # ------------------------------------------------------------
    # usage が無ければ何もしない（推計しない）
    # ------------------------------------------------------------
    usage = getattr(res, "usage", None)
    if usage is None:
        return res

    # ------------------------------------------------------------
    # cost 計算（usage→tokens→pricing→fx）
    # ------------------------------------------------------------
    c = estimate_chat_cost_from_usage(model=model, usage=usage)
    if c is None:
        return res

    # ------------------------------------------------------------
    # 反映（dataclass / pydantic 両対応）
    # ------------------------------------------------------------
    if dataclasses.is_dataclass(res):
        return dataclasses.replace(res, cost=c)
    if hasattr(res, "model_copy"):
        return res.model_copy(update={"cost": c})
    return res


# ============================================================
# OpenAI（Text）
# ============================================================
def openai_call_text(
    *,
    model: str,
    prompt: str,
    system: Optional[str],
    temperature: Optional[float],
    max_output_tokens: Optional[int],
    extra: Optional[Dict[str, Any]],
) -> TextResult:
    from ..providers.openai.text_responses_create import call_responses_create

    res = call_responses_create(
        model=model,
        prompt=prompt,
        system=system,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        extra=extra,
    )

    # ------------------------------------------------------------
    # cost（正本）：usage が取れていて cost が無い場合のみ埋める
    # ------------------------------------------------------------
    res = _fill_text_cost_if_missing(res=res, model=str(model))

    return res

# ============================================================
# OpenAI（Text / stream）
# - delta はそのまま yield
# - 最後に TextResult（usage/cost付き）を generator return で返す
# ============================================================
def openai_call_text_stream(
    *,
    model: str,
    prompt: str,
    system: Optional[str],
    temperature: Optional[float],
    max_output_tokens: Optional[int],
    extra: Optional[Dict[str, Any]],
):
    from ..providers.openai.text_responses_stream import stream_responses

    # provider の stream generator
    gen = stream_responses(
        model=model,
        prompt=prompt,
        system=system,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        extra=extra,
    )

    chunks: list[str] = []
    final_raw = None

    # ------------------------------------------------------------
    # delta をそのまま流す
    # ------------------------------------------------------------
    try:
        while True:
            piece = next(gen)
            if piece:
                s = str(piece)
                chunks.append(s)
                yield s
    except StopIteration as si:
        # provider が return した最終レスポンス（usage 付きの可能性）
        final_raw = si.value

    # ------------------------------------------------------------
    # TextResult に製本（推計しない）
    # ------------------------------------------------------------
    text = "".join(chunks).strip()
    usage = getattr(final_raw, "usage", None) if final_raw is not None else None

    res = TextResult(
        provider="openai",
        model=str(model),
        text=text,
        usage=usage,
        cost=None,
    )

    # ------------------------------------------------------------
    # cost（正本）：usage が取れていて cost が無い場合のみ埋める
    # ------------------------------------------------------------
    res = _fill_text_cost_if_missing(res=res, model=str(model))

    # ------------------------------------------------------------
    # generator return（StopIteration.value）
    # ------------------------------------------------------------
    return res


# ============================================================
# Gemini（Text）
# ============================================================
def gemini_call_text(
    *,
    model: str,
    prompt: str,
    system: Optional[str],
    temperature: Optional[float],
    max_output_tokens: Optional[int],
    extra: Optional[Dict[str, Any]],
) -> TextResult:
    from ..providers.gemini.text_generate import generate_text

    res = generate_text(
        model=model,
        prompt=prompt,
        system=system,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        extra=extra,
    )

    # ------------------------------------------------------------
    # cost（正本）：usage が取れていて cost が無い場合のみ埋める
    # ------------------------------------------------------------
    res = _fill_text_cost_if_missing(res=res, model=str(model))

    return res
