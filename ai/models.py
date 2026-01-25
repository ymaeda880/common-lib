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
TEXT_MODEL_CATALOG = [
    ("OpenAI / gpt-5-mini", "openai:gpt-5-mini"),
    ("OpenAI / gpt-5-nano", "openai:gpt-5-nano"),
    ("Gemini / gemini-2.0-flash", "gemini:gemini-2.0-flash"),
]

DEFAULT_TEXT_MODEL_KEY = "openai:gpt-5-mini"


# ============================================================
# Transcribe 系モデル
# ============================================================
TRANSCRIBE_MODELS = [
    "whisper-1",
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
    "gemini-2.0-flash",
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
