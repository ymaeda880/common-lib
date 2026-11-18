"""テキスト送信の容量確認用。既存のモデル選択一覧は変更しない。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextModelLimits:
    context_tokens: int | None
    input_tokens: int | None
    output_tokens: int


# 2026-11-17確認。未登録のモデル・デプロイ名には推測値を適用しない。
# https://developers.openai.com/api/docs/models/gpt-5
# https://developers.openai.com/api/docs/models/gpt-5-mini
# https://developers.openai.com/api/docs/models/gpt-5-nano
# https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models
# https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash
# https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash
TEXT_MODEL_LIMITS = {
    ("openai", "gpt-5"): TextModelLimits(400_000, None, 128_000),
    ("openai", "gpt-5-mini"): TextModelLimits(400_000, None, 128_000),
    ("openai", "gpt-5-nano"): TextModelLimits(400_000, None, 128_000),
    ("azure", "gpt-5-mini"): TextModelLimits(400_000, 272_000, 128_000),
    # Geminiの公表値は入力上限・出力上限。合計上限として扱わない。
    ("gemini", "gemini-3.5-flash"): TextModelLimits(None, 1_048_576, 65_536),
    ("gemini", "gemini-3.6-flash"): TextModelLimits(None, 1_048_576, 65_536),
}
for _name in ("gpt-5", "gpt-5-mini", "gpt-5-nano"):
    TEXT_MODEL_LIMITS[("openai", f"{_name}-2025-08-07")] = TEXT_MODEL_LIMITS[("openai", _name)]


def get_text_model_limits(provider: str, model: str) -> TextModelLimits | None:
    return TEXT_MODEL_LIMITS.get((str(provider).strip().lower(), str(model).strip()))
