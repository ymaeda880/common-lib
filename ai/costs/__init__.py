# -*- coding: utf-8 -*-
# common_lib/ai/costs/__init__.py
# ============================================================
# costs package exports（正本）
# - estimate.py に存在しない名前（例: ChatUsage）を export しない
# ============================================================

from __future__ import annotations

from .estimate import CostResult

from .estimate import (
    estimate_chat_cost,
    estimate_embedding_cost,
    estimate_transcribe_cost,
)

from .pricing import (
    MILLION,
    get_chat_price,
    get_embedding_price,
    get_audio_price,
    price_per_1k_from_per_1m,
)

from .ui import (
    render_chat_cost_summary,
    render_embedding_price_hint,
    render_transcribe_cost_summary,
)

__all__ = [
    # types
    "CostResult",
    # estimate
    "estimate_chat_cost",
    "estimate_embedding_cost",
    "estimate_transcribe_cost",
    # pricing
    "MILLION",
    "get_chat_price",
    "get_embedding_price",
    "get_audio_price",
    "price_per_1k_from_per_1m",
    # ui
    "render_chat_cost_summary",
    "render_embedding_price_hint",
    "render_transcribe_cost_summary",
]
