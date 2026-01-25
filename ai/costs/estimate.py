# -*- coding: utf-8 -*-
# common_lib/ai/costs/estimate.py
# ============================================================
# Cost estimation（正本）
#
# 目的：
# - 単価は pricing 正本
# - 為替は fx 正本（get_default_usd_jpy）
# - 呼び出し側は USD/JPY を一切渡さない
# - usage の形揺れ吸収は ai/usage 正本に一本化（extract_tokens）
# ============================================================

from __future__ import annotations

# ============================================================
# 標準ライブラリ
# ============================================================
from typing import Any, Optional

# ============================================================
# 内部：pricing / fx（正本）
# ============================================================
from .pricing import get_audio_price, get_chat_price, get_embedding_price
from .fx import get_default_usd_jpy, usd_to_jpy

# ============================================================
# usage → tokens（正本：ai/usage）
# ============================================================
from common_lib.ai.usage_extract.extract_tokens import (
    _extract_text_tokens_from_usage,
    _extract_embedding_tokens_from_usage,
)


# ============================================================
# CostResult（正本：types）
# ============================================================
from common_lib.ai.types import CostResult


# ============================================================
# Transcribe cost
# ============================================================
def estimate_transcribe_cost(
    *,
    model: str,
    audio_seconds: float,
) -> Optional[CostResult]:
    """
    音声文字起こしの概算コスト
    - 単価は pricing 正本
    - 為替は fx 正本
    - 単価未設定モデルは None
    """
    price = get_audio_price(model)
    if price is None:
        return None

    usd = (audio_seconds / 60.0) * float(price.usd_per_min)

    fx = get_default_usd_jpy()
    jpy = usd_to_jpy(usd, usd_jpy=fx.usd_jpy)

    return CostResult(
        usd=float(usd),
        jpy=float(jpy),
        usd_jpy=float(fx.usd_jpy),
        fx_source=fx.source,
    )


# ============================================================
# Chat cost（参考：既存整理）
# ============================================================
def estimate_chat_cost(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> Optional[CostResult]:
    """
    Chat の概算コスト
    - 単価は pricing 正本（USD / 1M tok）
    - 為替は fx 正本
    - 単価未設定モデルは None
    """
    price = get_chat_price(model)
    if price is None:
        return None

    usd = (
        (float(input_tokens) / 1_000_000.0) * float(price.in_usd)
        + (float(output_tokens) / 1_000_000.0) * float(price.out_usd)
    )

    fx = get_default_usd_jpy()
    jpy = usd_to_jpy(usd, usd_jpy=fx.usd_jpy)

    return CostResult(
        usd=float(usd),
        jpy=float(jpy),
        usd_jpy=float(fx.usd_jpy),
        fx_source=fx.source,
    )


# ============================================================
# Chat cost（usage 互換ヘルパー：製本）
# - usage の形揺れ吸収は ai/usage 正本に一本化
# - 推計はしない（usage から tokens が取れた時だけ cost を作る）
# ============================================================
def estimate_chat_cost_from_usage(
    *,
    model: str,
    usage: Any,
) -> Optional[CostResult]:
    """
    usage（dict / object）から tokens を抽出して Chat cost を作る。
    - tokens が取れない場合は None
    - 推計はしない（usage が無い/不足なら諦める）
    """
    # ------------------------------------------------------------
    # None ガード
    # ------------------------------------------------------------
    if usage is None:
        return None

    # ------------------------------------------------------------
    # tokens 抽出（正本）
    # ------------------------------------------------------------
    tu = _extract_text_tokens_from_usage(usage)

    # ------------------------------------------------------------
    # Chat は input/output の両方が必要（単価が分かれるため）
    # ※ 片方欠けは推計になるので None
    # ------------------------------------------------------------
    if tu.input_tokens is None or tu.output_tokens is None:
        return None

    return estimate_chat_cost(
        model=model,
        input_tokens=int(tu.input_tokens),
        output_tokens=int(tu.output_tokens),
    )


# ============================================================
# Embedding cost
# ============================================================
def estimate_embedding_cost(
    *,
    model: str,
    input_tokens: int,
) -> Optional[CostResult]:
    """
    Embedding の概算コスト
    - 単価は pricing 正本（USD / 1M tok）
    - 為替は fx 正本
    - 単価未設定モデルは None
    """
    price_per_1m = get_embedding_price(model)
    if price_per_1m is None:
        return None

    usd = (float(input_tokens) / 1_000_000.0) * float(price_per_1m)

    fx = get_default_usd_jpy()
    jpy = usd_to_jpy(usd, usd_jpy=fx.usd_jpy)

    return CostResult(
        usd=float(usd),
        jpy=float(jpy),
        usd_jpy=float(fx.usd_jpy),
        fx_source=fx.source,
    )


# ============================================================
# Embedding cost（usage 互換ヘルパー：製本）
# - usage の形揺れ吸収は ai/usage 正本に一本化
# - 推計はしない（usage から tokens が取れた時だけ cost を作る）
# ============================================================
def estimate_embedding_cost_from_usage(
    *,
    model: str,
    usage: Any,
) -> Optional[CostResult]:
    """
    usage（dict / object）から input tokens を抽出して Embedding cost を作る。
    - tokens が取れない場合は None
    - 推計はしない（usage が無い/不足なら諦める）
    """
    # ------------------------------------------------------------
    # None ガード
    # ------------------------------------------------------------
    if usage is None:
        return None

    # ------------------------------------------------------------
    # tokens 抽出（正本）
    # ------------------------------------------------------------
    tu = _extract_embedding_tokens_from_usage(usage)

    # ------------------------------------------------------------
    # Embedding は input が無ければ計算不能（推計しない）
    # ------------------------------------------------------------
    if tu.input_tokens is None:
        return None

    return estimate_embedding_cost(
        model=model,
        input_tokens=int(tu.input_tokens),
    )
