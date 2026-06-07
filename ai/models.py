# -*- coding: utf-8 -*-
# common_lib/ai/models.py
# ============================================================
# AIモデル定義（正本）
# - UIはここを参照するだけ
# - provider:model 形式を正本とする
# ============================================================

# ============================================================
# Text / Chat 系モデル（表示順もここで管理）
# ============================================================
# TEXT_MODEL_CATALOG = [
#     ("OpenAI / gpt-5-mini", "openai:gpt-5-mini"),
#     ("OpenAI / gpt-5-nano", "openai:gpt-5-nano"),
#     ("Gemini / gemini-2.0-flash", "gemini:gemini-2.0-flash"),
# ]

TEXT_MODEL_CATALOG = [
    ("OpenAI / gpt-5", "openai:gpt-5"),
    ("OpenAI / gpt-5-mini", "openai:gpt-5-mini"),
    ("OpenAI / gpt-5-nano", "openai:gpt-5-nano"),
    ("Azure OpenAI / gpt-5-mini", "azure:gpt-5-mini"),
    ("Gemini / gemini-3.5-flash", "gemini:gemini-3.5-flash"),
]

DEFAULT_TEXT_MODEL_KEY = "openai:gpt-5-mini"

DEFAULT_TEXT_MODEL_KEY = "openai:gpt-5-mini"

# ============================================================
# Image 系モデル
# ============================================================
IMAGE_MODEL_CATALOG = [
    ("OpenAI / gpt-image-1", "openai:gpt-image-1"),
    ("Gemini / gemini-2.5-flash-image", "gemini:gemini-2.5-flash-image"),
]

DEFAULT_IMAGE_MODEL_KEY = "openai:gpt-image-1"

# ============================================================
# Transcribe 系モデル
# ============================================================
TRANSCRIBE_MODELS = [
    "whisper-1",
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
    "gemini-3.5-flash",
]


# ============================================================
# Embedding（ベクトル埋込）系モデル
# ============================================================
# - provider:model 形式を正本とする
# - UI（model picker）はここを参照するだけ
# ============================================================
EMBED_MODEL_CATALOG = [
    ("OpenAI / text-embedding-3-small", "openai:text-embedding-3-small"),
    ("OpenAI / text-embedding-3-large", "openai:text-embedding-3-large"),
]

DEFAULT_EMBED_MODEL_KEY = "openai:text-embedding-3-large"
