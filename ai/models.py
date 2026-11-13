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
    ("Gemini / gemini-3.6-flash", "gemini:gemini-3.6-flash"),
]

DEFAULT_TEXT_MODEL_KEY = "openai:gpt-5-mini"

# ============================================================
# Image 系モデル
# ============================================================
IMAGE_MODEL_CATALOG = [
    ("OpenAI / gpt-image-1", "openai:gpt-image-1"),
    ("OpenAI / gpt-image-2", "openai:gpt-image-2"),
    ("OpenAI / gpt-image-2.5-flare", "openai:gpt-image-2.5-flare"),
    ("OpenAI / gpt-image-2.5-sunburst", "openai:gpt-image-2.5-sunburst"),
    ("Gemini / gemini-2.5-flash-image", "gemini:gemini-2.5-flash-image"),
]

DEFAULT_IMAGE_MODEL_KEY = "openai:gpt-image-2"

# ============================================================
# Transcribe 系モデル
# ============================================================
TRANSCRIBE_MODELS = [
    "gpt-transcribe",
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe-diarize",
    "whisper-1",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.5-transcribe",
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


# ============================================================
# タイムスタンプ付き文字起こし：モデル別の応答形式
# - 対応モデルと応答形式は、この共通定義で管理する
# - 各ページは、自分が処理できる応答形式を指定して一覧を取得する
# ============================================================
TIMESTAMP_TRANSCRIBE_FORMATS = {
    "whisper-1": "srt",
    "gpt-4o-transcribe-diarize": "diarized_json",
    "gemini-3.5-flash": "srt",
    "gemini-3.6-flash": "srt",
    "gemini-3.5-transcribe": "json",
}


def get_timestamp_transcribe_models(
    *, response_formats: tuple[str, ...]
) -> list[str]:
    return [
        model
        for model in TRANSCRIBE_MODELS
        if TIMESTAMP_TRANSCRIBE_FORMATS.get(model) in response_formats
    ]