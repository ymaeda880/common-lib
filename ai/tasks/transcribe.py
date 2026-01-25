# -*- coding: utf-8 -*-
# common_lib/ai/tasks/transcribe.py
# =============================================================================
# Transcribe tasks（正本）
# - pages は audio_seconds を計測して渡す
# - tasks は estimate_transcribe_cost を使って cost を埋める（可能な場合のみ）
# - 返り値は TranscribeResult（types.py 正本）
#
# 通貨換算（正本方針）：
# - USD/JPY は pages/tasks で入力・受け渡ししない
# - 為替は costs/estimate.py（fx.get_default_usd_jpy() / 既定150）で解決する
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional

from ..types import TranscribeResult
from ..costs.estimate import estimate_transcribe_cost


def openai_transcribe_audio(
    *,
    model: str,
    audio_bytes: bytes,
    mime_type: str,
    filename: str,
    response_format: str,
    language: Optional[str],
    prompt: Optional[str],
    timeout_sec: int,
    audio_seconds: Optional[float],
    extra: Optional[Dict[str, Any]] = None,
) -> TranscribeResult:
    from ..providers.openai.transcribe_http import transcribe_http

    # ============================================================
    # OpenAI Transcribe（モデル差分 + strict param 制御）
    # ============================================================
    kwargs: Dict[str, Any] = dict(
        model=model,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        filename=filename,
        timeout_sec=timeout_sec,
        extra=extra,
    )

    # language は whisper-1 のみ
    if model == "whisper-1" and language:
        kwargs["language"] = language

    # whisper-1 のみ許可される引数
    if model == "whisper-1":
        if prompt:
            kwargs["prompt"] = prompt
        kwargs["response_format"] = response_format

    res = transcribe_http(**kwargs)

    # ============================================================
    # cost（正本）
    # - audio_seconds がある時だけ
    # - 為替は estimate_transcribe_cost 側（fx 正本）で解決する
    # - 単価未設定などで計算不能なら None のまま
    # ============================================================
    cost = None
    if audio_seconds is not None:
        cost = estimate_transcribe_cost(
            model=model,
            audio_seconds=float(audio_seconds),
        )

    return TranscribeResult(
        provider=res.provider,
        model=res.model,
        text=res.text,
        audio_seconds=audio_seconds,
        request_id=res.request_id,
        meta=res.meta,
        usage=res.usage,
        cost=cost,
        raw=res.raw,
    )


# =============================================================================
# GEMINI TRANSCRIBE
# =============================================================================
def gemini_transcribe_audio(
    *,
    model: str,
    audio_bytes: bytes,
    mime_type: str,
    filename: str,
    language: Optional[str],
    prompt: Optional[str],
    timeout_sec: int,
    audio_seconds: Optional[float],
    extra: Optional[Dict[str, Any]] = None,
) -> TranscribeResult:
    from ..providers.gemini.transcribe_generate import transcribe_audio

    res = transcribe_audio(
        model=model,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        filename=filename,
        language=language,
        prompt=prompt,
        timeout_sec=timeout_sec,
        extra=extra,
    )

    # ============================================================
    # cost（正本）
    # - audio_seconds がある時だけ
    # - 為替は estimate_transcribe_cost 側（fx 正本）で解決する
    # - pricing 未設定などで計算不能なら None のまま
    # ============================================================
    cost = None
    if audio_seconds is not None:
        cost = estimate_transcribe_cost(
            model=model,
            audio_seconds=float(audio_seconds),
        )

    return TranscribeResult(
        provider=res.provider,
        model=res.model,
        text=res.text,
        audio_seconds=audio_seconds,
        request_id=res.request_id,
        meta=res.meta,
        usage=res.usage,
        cost=cost,
        raw=res.raw,
    )
