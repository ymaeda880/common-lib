# -*- coding: utf-8 -*-
# common_lib/ai/__init__.py

from __future__ import annotations

from .types import (
    Provider,
    TaskType,
    UsageSummary,
    TextResult,
    ImageResult,
    TranscribeResult,
)
from .errors import (
    AIError,
    ProviderError,
    RetryableError,
    InvalidRequestError,
    InvalidResponseError,
    TimeoutError,
)
from .routing import (
    call_text,
    call_text_stream,
    generate_image,
    edit_image,
    transcribe_audio,
)

# ------------------------------------------------------------
# routing（高レベルAPI）：embedding
# ------------------------------------------------------------
from .routing import embed_text


# ------------------------------------------------------------
# usage（tokens抽出：正本）
# - Result から input/output tokens を安全に取得（推計しない）
# ------------------------------------------------------------
from .usage import get_usage_tokens_if_any


__all__ = [
    # types
    "Provider",
    "TaskType",
    "UsageSummary",
    "TextResult",
    "ImageResult",
    "TranscribeResult",
    # errors
    "AIError",
    "ProviderError",
    "RetryableError",
    "InvalidRequestError",
    "InvalidResponseError",
    "TimeoutError",
    # routing
    "call_text",
    "call_text_stream",
    "generate_image",
    "edit_image",
    "transcribe_audio",

    # routing（高レベルAPI）：embedding
    "embed_text",
]
