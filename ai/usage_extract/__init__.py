# -*- coding: utf-8 -*-
# common_lib/ai/usage_extract/__init__.py
# ============================================================
# usage_extract（正本）
# ------------------------------------------------------------
# 目的：
# - tokens 抽出系の正本 API を公開する
# - 呼び出し側は「extract_tokens.py を直import」してもよいが、
#   安定運用のため re-export も用意する
# ============================================================

from __future__ import annotations

# ============================================================
# re-export（正本API）
# ============================================================
from .extract_tokens import (
    TokenUsage,
    extract_text_token_usage,
    extract_embedding_token_usage,
    extract_text_in_out_tokens,
)
