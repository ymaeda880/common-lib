# common_lib/ai/costs/pricing.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


MILLION = 1_000_000


@dataclass(frozen=True)
class ChatPricePer1M:
    """Chat の単価（USD / 1M tokens）"""
    in_usd: float
    out_usd: float


@dataclass(frozen=True)
class AudioPricePerMin:
    """音声の単価（USD / 分）"""
    usd_per_min: float


# ============================================================
# 価格テーブル（ここが正本）
# - いまは旧 common_lib/openai/costs.py の値を移植
# - 将来 update するのはここだけ
# ============================================================

CHAT_PRICES_USD_PER_1M: Dict[str, ChatPricePer1M] = {
    "gpt-5": ChatPricePer1M(in_usd=1.25, out_usd=10.00),
    "gpt-5-mini": ChatPricePer1M(in_usd=0.25, out_usd=2.00),
    "gpt-5-nano": ChatPricePer1M(in_usd=0.05, out_usd=0.40),
    "gpt-4o": ChatPricePer1M(in_usd=2.50, out_usd=10.00),
    "gpt-4o-mini": ChatPricePer1M(in_usd=0.15, out_usd=0.60),
    # 参考（必要なら）
    "gpt-4.1": ChatPricePer1M(in_usd=2.00, out_usd=8.00),
    "gpt-4.1-mini": ChatPricePer1M(in_usd=0.40, out_usd=1.60),
    "gpt-3.5-turbo": ChatPricePer1M(in_usd=0.50, out_usd=1.50),
    # gemini
    "gemini-2.0-flash": ChatPricePer1M(in_usd=0.10, out_usd=0.40),

}

EMBEDDING_PRICES_USD_PER_1M: Dict[str, float] = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,
}

AUDIO_PRICES_USD_PER_MIN: Dict[str, AudioPricePerMin] = {
    "whisper-1": AudioPricePerMin(usd_per_min=0.006),

    # OpenAI Transcribe models（Whisper互換・分単価）
    "gpt-4o-mini-transcribe": AudioPricePerMin(usd_per_min=0.006),
    "gpt-4o-transcribe": AudioPricePerMin(usd_per_min=0.006),
}


# ============================================================
# 取得ユーティリティ
# ============================================================

def get_chat_price(model: str) -> Optional[ChatPricePer1M]:
    return CHAT_PRICES_USD_PER_1M.get(model)


def get_embedding_price(model: str) -> Optional[float]:
    return EMBEDDING_PRICES_USD_PER_1M.get(model)


def get_audio_price(model: str) -> Optional[AudioPricePerMin]:
    return AUDIO_PRICES_USD_PER_MIN.get(model)


def price_per_1k_from_per_1m(price_per_1m: float) -> float:
    """USD/1M → USD/1K"""
    return float(price_per_1m) / 1000.0
