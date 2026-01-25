# -*- coding: utf-8 -*-
# common_lib/ai/types.py
# =============================================================================
# AI Result / Usage / Cost の正本型（common_lib.ai の固定I/F）
# - CostResult はここ（types.py）を正本にする（重複定義しない）
# - estimate.py / tasks.py / ui.py はこの型に合わせる
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
# ============================================================
# typing（正本）
# ============================================================
from typing import Any, Dict, Literal, Optional, List


Provider = Literal["openai", "gemini"]
TaskType = Literal["text", "image", "transcribe", "embedding"]



# =============================================================================
# Usage（取れた時だけ入る）
# =============================================================================
@dataclass(frozen=True)
class UsageSummary:
    """
    取得できる場合のみ埋める（取得不能は None）
    - text: input_tokens / output_tokens
    - transcribe: tokensが取れないケースが多い
    - image: tokens概念が無い/取れないケースが多い
    """
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    raw: Optional[Dict[str, Any]] = None


# =============================================================================
# Cost（共通・正本）
# =============================================================================
@dataclass(frozen=True)
class CostResult:
    """
    cost の共通表現（正本）
    - fx_source: 'manual' / 'api' 等、為替の出所
    """
    usd: float
    jpy: float
    usd_jpy: float
    fx_source: str = "manual"


# =============================================================================
# Text
# =============================================================================
@dataclass(frozen=True)
class TextResult:
    provider: Provider
    model: str
    text: str
    usage: UsageSummary = UsageSummary()
    cost: Optional[CostResult] = None
    raw: Optional[Dict[str, Any]] = None


# =============================================================================
# Image
# =============================================================================
@dataclass(frozen=True)
class ImageResult:
    provider: Provider
    model: str
    # 返り値は bytes 優先。URLしかない場合は url のみ。
    image_bytes: Optional[bytes] = None
    image_url: Optional[str] = None
    cost: Optional[CostResult] = None
    raw: Optional[Dict[str, Any]] = None


# =============================================================================
# Transcribe（音声文字起こし）
# =============================================================================
@dataclass(frozen=True)
class TranscribeResult:
    provider: Provider
    model: str
    text: str

    # pages 側で計測して渡す（取れたら必ず入れる）
    audio_seconds: Optional[float] = None

    # OpenAI の x-request-id 等（取れたら入れる）
    request_id: Optional[str] = None

    # srt/vtt 等の形式や補助情報（プロバイダ固有の情報もここ）
    meta: Optional[Dict[str, Any]] = None

    # tokens は取れないケースが多い（取れたら入れる）
    usage: UsageSummary = UsageSummary()

    # cost は取れた場合のみ（取れない場合は None）
    cost: Optional[CostResult] = None

    raw: Optional[Dict[str, Any]] = None


# =============================================================================
# Embedding（ベクトル埋込）
# =============================================================================
@dataclass(frozen=True)
class EmbedResult:
    provider: Provider
    model: str
    vectors: List[List[float]]
    dim: int

    # tokens は取れない/取れないことが多い（取れたら入れる）
    usage: UsageSummary = UsageSummary()

    # cost は取れた場合のみ（取れない場合は None）
    cost: Optional[CostResult] = None

    raw: Optional[Dict[str, Any]] = None
