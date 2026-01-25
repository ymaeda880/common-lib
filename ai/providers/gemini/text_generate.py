# -*- coding: utf-8 -*-
# common_lib/ai/providers/gemini/text_generate.py

# ============================================================
# Gemini usage / cost の取り扱いについて（重要・設計メモ）
# ------------------------------------------------------------
# ■ 背景
# google-genai (Gemini) の generate_content() は、
# OpenAI Responses API のような res.usage を返さず、
# トークン情報は resp.usage_metadata に格納される。
#
# 例（raw）:
#   usage_metadata:
#     prompt_token_count     = 入力トークン数
#     candidates_token_count = 出力トークン数
#     total_token_count      = 合計トークン数
#
# ■ この実装の方針
# - 推計は一切しない。
#   → API が返したトークン情報のみを使用する。
# - provider 層（このファイル）で、
#   Gemini 固有の usage_metadata を共通形式に正規化する。
#
# ■ 正規化の内容
# usage_metadata から以下を defensive に抽出し、
# common_lib 共通の UsageSummary に詰め替える：
#
#   UsageSummary.input_tokens  ←
#       input_tokens
#       or prompt_tokens
#       or prompt_token_count      (Gemini 実体)
#
#   UsageSummary.output_tokens ←
#       output_tokens
#       or completion_tokens
#       or candidates_token_count  (Gemini 実体)
#
#   UsageSummary.total_tokens  ←
#       total_tokens
#       or total_token_count
#
# ※ これにより、上位レイヤ（tasks / busy / costs / UI）は
#    provider 差を意識せず input/output/total を扱える。
#
# ■ cost（概算）について
# - Gemini は実測 cost を返さない前提。
# - そのため、ここで
#     tokens × 単価（pricing 正本）
#   による概算 cost を計算する。
# - fx_source には "estimate:<source>" を明示し、
#   実測ではないことを区別する。
#
# ■ 重要な注意
# - Gemini のトークンは、この provider 実装で初めて拾われる。
# - common_lib/ai/costs/estimate.py は
#   「正規化済み usage（input/output tokens）」を前提としている。
# - raw な resp.usage_metadata を直接参照するのは
#   調査用ページ（例: 202_OpenAI_API_res確認.py）のみ。
#
# この分離により：
# - provider 層：API差分吸収・正規化
# - cost 層     ：単価 × tokens の計算に専念
# という責務分離を保っている。
# ============================================================


from __future__ import annotations

from typing import Any, Dict, Optional

from ...types import TextResult, UsageSummary
from ...errors import ProviderError

from .client import configure_gemini


def generate_text(
    *,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> TextResult:
    # ============================================================
    # Gemini generate（google-genai）
    # - configure_gemini() は google-genai の Client を返す前提
    # - google.generativeai は使わない
    # ============================================================
    client = configure_gemini()

    try:
        from google.genai import types  # type: ignore

        parts = []
        if system and str(system).strip():
            parts.append(str(system).strip())
        parts.append(str(prompt))

        cfg = types.GenerateContentConfig()
        if temperature is not None:
            cfg.temperature = float(temperature)
        if max_output_tokens is not None:
            cfg.max_output_tokens = int(max_output_tokens)

        # extra は今は未使用（必要になったら対応）
        _ = extra

        resp = client.models.generate_content(
            model=model,
            contents=parts,
            config=cfg,
        )

    except Exception as e:
        raise ProviderError(f"Gemini generate_content failed: {e}", provider="gemini") from e

    # ============================================================
    # usage（tokens）を google-genai の response から抽出
    # - 推計しない：返ってきた値だけを UsageSummary に入れる
    # - 形が変わっても落ちないように defensive に拾う
    # ============================================================
    text = getattr(resp, "text", "") or ""

    um = getattr(resp, "usage_metadata", None)

    def _pick_int(u: Any, key: str) -> Optional[int]:
        if u is None:
            return None
        v = u.get(key) if isinstance(u, dict) else getattr(u, key, None)
        if v is None:
            return None
        try:
            return int(v)
        except Exception:
            return None

    in_tok = (
        _pick_int(um, "input_tokens")
        or _pick_int(um, "prompt_tokens")
        or _pick_int(um, "prompt_token_count")
    )
    out_tok = (
        _pick_int(um, "output_tokens")
        or _pick_int(um, "completion_tokens")
        or _pick_int(um, "candidates_token_count")
    )
    total_tok = _pick_int(um, "total_tokens") or _pick_int(um, "total_token_count")

    usage = UsageSummary(
        input_tokens=in_tok,
        output_tokens=out_tok,
        total_tokens=total_tok,
        raw=None,
    )

    # ============================================================
    # cost（概算）
    # - Gemini は実測costを返さない想定のため、tokens×単価で概算する
    # - 概算であることは fx_source に明示する
    # ============================================================
    cost = None
    try:
        from ...costs.pricing import get_chat_price, price_per_1k_from_per_1m
        from ...costs.fx import get_default_usd_jpy
        from ...types import CostResult

        p = get_chat_price(model)
        fx = get_default_usd_jpy(default=150.0)

        if p and (usage.input_tokens is not None) and (usage.output_tokens is not None):
            in_usd_per_1k = float(price_per_1k_from_per_1m(p.in_usd))
            out_usd_per_1k = float(price_per_1k_from_per_1m(p.out_usd))

            usd = (float(usage.input_tokens) / 1000.0) * in_usd_per_1k + (float(usage.output_tokens) / 1000.0) * out_usd_per_1k
            jpy = float(usd) * float(fx.usd_jpy)

            cost = CostResult(
                usd=float(usd),
                jpy=float(jpy),
                usd_jpy=float(fx.usd_jpy),
                fx_source=f"estimate:{fx.source}",
            )
    except Exception:
        cost = None

    return TextResult(provider="gemini", model=model, text=str(text), usage=usage, cost=cost, raw=None)



