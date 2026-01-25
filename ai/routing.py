# -*- coding: utf-8 -*-
# common_lib/ai/routing.py

from __future__ import annotations

from typing import Any, Dict, Optional

# ============================================================
# types（正本）
# ============================================================
from .types import Provider, TextResult, ImageResult, TranscribeResult, EmbedResult

from .errors import InvalidRequestError


# ============================================================
# TEXT
# ============================================================
def call_text(
    *,
    provider: Provider,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> TextResult:
    if not prompt or not str(prompt).strip():
        raise InvalidRequestError("prompt is empty")

    if provider == "openai":
        from .tasks.text import openai_call_text
        return openai_call_text(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            extra=extra,
        )

    if provider == "gemini":
        from .tasks.text import gemini_call_text
        return gemini_call_text(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            extra=extra,
        )

    raise InvalidRequestError(f"unknown provider: {provider}")


def call_text_stream(
    *,
    provider: Provider,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    """
    ストリームは「ジェネレータ」を返す想定。
    いまは OpenAI のみを想定（必要になったら拡張）。
    """
    if not prompt or not str(prompt).strip():
        raise InvalidRequestError("prompt is empty")

    if provider == "openai":
        from .tasks.text import openai_call_text_stream
        return openai_call_text_stream(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            extra=extra,
        )

    raise InvalidRequestError(f"stream not supported provider: {provider}")


# ============================================================
# IMAGE
# ============================================================
def generate_image(
    *,
    provider: Provider,
    model: str,
    prompt: str,
    size: str = "1024x1024",
    n: int = 1,
    extra: Optional[Dict[str, Any]] = None,
) -> ImageResult:
    if not prompt or not str(prompt).strip():
        raise InvalidRequestError("prompt is empty")

    if provider == "openai":
        from .tasks.image import openai_generate_image
        return openai_generate_image(model=model, prompt=prompt, size=size, n=n, extra=extra)

    raise InvalidRequestError(f"image not supported provider: {provider}")


def edit_image(
    *,
    provider: Provider,
    model: str,
    prompt: str,
    image_bytes: bytes,
    size: str = "1024x1024",
    extra: Optional[Dict[str, Any]] = None,
) -> ImageResult:
    if not prompt or not str(prompt).strip():
        raise InvalidRequestError("prompt is empty")
    if not image_bytes:
        raise InvalidRequestError("image_bytes is empty")

    if provider == "openai":
        from .tasks.image import openai_edit_image
        return openai_edit_image(model=model, prompt=prompt, image_bytes=image_bytes, size=size, extra=extra)

    raise InvalidRequestError(f"image edit not supported provider: {provider}")


# ============================================================
# TRANSCRIBE
# ============================================================
def transcribe_audio(
    *,
    provider: Provider,
    model: str,
    audio_bytes: bytes,
    mime_type: str,
    filename: str,          # ★ 追加
    audio_seconds: Optional[float] = None,  # ★ 追加（秒課金の正本入力）
    response_format: str = "json",  # json/text/srt/vtt
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    timeout_sec: int = 600,
    extra: Optional[Dict[str, Any]] = None,
) -> TranscribeResult:
    if not audio_bytes:
        raise InvalidRequestError("audio_bytes is empty")
    if not mime_type:
        raise InvalidRequestError("mime_type is empty")

    if provider == "openai":
        from .tasks.transcribe import openai_transcribe_audio
        return openai_transcribe_audio(
            model=model,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            filename=filename,      # ★ 追加
            audio_seconds=audio_seconds,  # ★ 追加
            response_format=response_format,
            language=language,
            prompt=prompt,
            timeout_sec=timeout_sec,
            extra=extra,
        )

    if provider == "gemini":
        from .tasks.transcribe import gemini_transcribe_audio
        return gemini_transcribe_audio(
            model=model,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            filename=filename,      # ★ 追加２
            audio_seconds=audio_seconds,  # ★追加
            language=language,
            prompt=prompt,
            timeout_sec=timeout_sec,
            extra=extra,
        )

    raise InvalidRequestError(f"unknown provider: {provider}")

# ============================================================
# EMBEDDING
# ============================================================
def embed_text(
    *,
    provider: Provider,
    model: str,
    inputs: list[str],
    extra: Optional[Dict[str, Any]] = None,
) -> EmbedResult:
    """
    ベクトル埋込（embedding）
    - inputs は複数文字列を許容（行ごと埋込等を想定）
    """
    if not inputs or not any(str(x).strip() for x in inputs):
        raise InvalidRequestError("inputs is empty")

    if provider == "openai":
        # ------------------------------------------------------------
        # tasks（OpenAI）
        # ------------------------------------------------------------
        from .tasks.embedding import openai_embed_text
        return openai_embed_text(
            model=model,
            inputs=inputs,
            extra=extra,
        )

    raise InvalidRequestError(f"embedding not supported provider: {provider}")
