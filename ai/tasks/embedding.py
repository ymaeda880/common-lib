# -*- coding: utf-8 -*-
# common_lib/ai/tasks/embedding.py
# ============================================================
# Embedding タスク（正本）
# - provider 実装（OpenAI 等）をここに閉じ込める
# - routing.py はこの関数を呼ぶだけ
# - usage/cost は「取れた範囲のみ」詰める（ページ側では推計しない）
# ============================================================

from __future__ import annotations

# ============================================================
# typing / dataclasses（正本）
# ============================================================
from typing import Any, Dict, Optional, List

# ============================================================
# types（正本）
# ============================================================
from ..types import EmbedResult, UsageSummary

# ============================================================
# errors（正本）
# ============================================================
from ..errors import InvalidResponseError

# ============================================================
# costs（正本：estimate）
# ============================================================
from ..costs.estimate import estimate_embedding_cost_from_usage

# ============================================================
# usage → tokens（正本）
# ============================================================
from common_lib.ai.usage_extract.extract_tokens import _extract_embedding_tokens_from_usage


# ============================================================
# OpenAI client（正本）
# ============================================================
from ..providers.openai.client import get_client


# ============================================================
# OpenAI
# ============================================================
def openai_embed_text(
    *,
    model: str,
    inputs: List[str],
    extra: Optional[Dict[str, Any]] = None,
) -> EmbedResult:
    """
    OpenAI embedding
    - inputs: 複数テキスト対応
    - vectors: List[List[float]]
    - usage/cost: 取れた範囲のみ
    """
    # ------------------------------------------------------------
    # OpenAI client（正本）
    # ------------------------------------------------------------
    client = get_client()

    # ------------------------------------------------------------
    # リクエスト（provider 固有）
    # ------------------------------------------------------------
    resp = client.embeddings.create(
        model=model,
        input=inputs,
        **(extra or {}),
    )

    # ------------------------------------------------------------
    # vectors パース（必須）
    # ------------------------------------------------------------
    data = getattr(resp, "data", None)
    if not data:
        raise InvalidResponseError("embedding response has no data")

    vectors: List[List[float]] = []
    for item in data:
        vec = getattr(item, "embedding", None)
        if not isinstance(vec, list) or not vec:
            raise InvalidResponseError("embedding item has no vector")
        vectors.append([float(x) for x in vec])

    dim = len(vectors[0]) if vectors else 0

    # ------------------------------------------------------------
    # usage（取れた範囲のみ）
    # - tokens 抽出は ai/usage 正本に一本化
    # ------------------------------------------------------------
    u = getattr(resp, "usage", None)
    tu = _extract_embedding_tokens_from_usage(u)

    usage = UsageSummary(
        input_tokens=tu.input_tokens,
        output_tokens=None,
        total_tokens=tu.total_tokens,
        raw=u if isinstance(u, dict) else None,
    )

    # ------------------------------------------------------------
    # cost（取れた範囲のみ）
    # - usage が取れた範囲だけで cost を作る（推計しない）
    # ------------------------------------------------------------
    cost = estimate_embedding_cost_from_usage(
        model=str(model),
        usage=usage,
    )

    # ------------------------------------------------------------
    # Result（正本型）
    # ------------------------------------------------------------
    return EmbedResult(
        provider="openai",
        model=str(model),
        vectors=vectors,
        dim=int(dim),
        usage=usage,
        cost=cost,
        raw=None,
    )
