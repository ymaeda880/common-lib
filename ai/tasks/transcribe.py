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

from ..types import TranscribeResult, UsageSummary
#from ..costs.estimate import estimate_transcribe_cost
from ..costs.estimate import estimate_transcribe_cost, estimate_chat_cost_from_usage


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

    # ============================================================
    # モデル別パラメータ制御
    # ============================================================

    # ------------------------------------------------------------
    # whisper-1
    # - language / prompt / response_format を使用可能
    # ------------------------------------------------------------
    if model == "whisper-1":
        if language:
            kwargs["language"] = language

        if prompt:
            kwargs["prompt"] = prompt

        kwargs["response_format"] = response_format

    # ------------------------------------------------------------
    # gpt-4o-transcribe-diarize
    # - タイムスタンプ・話者分離は diarized_json で取得する
    # - prompt は渡さない
    # ------------------------------------------------------------
    elif model == "gpt-4o-transcribe-diarize":
        kwargs["response_format"] = "diarized_json"

    res = transcribe_http(**kwargs)

    # ============================================================
    # usage / cost（正本）
    # ============================================================
    usage = res.usage
    cost = None

    # ------------------------------------------------------------
    # gpt-4o-transcribe-diarize
    # - APIレスポンスのusage tokenを使用する
    # - 音声時間からは推計しない
    # ------------------------------------------------------------
    if model == "gpt-4o-transcribe-diarize":
        raw_usage = None

        if isinstance(res.raw, dict):
            raw_usage = res.raw.get(
                "usage",
                None,
            )

        if isinstance(raw_usage, dict):
            input_tokens = raw_usage.get(
                "input_tokens",
                None,
            )

            output_tokens = raw_usage.get(
                "output_tokens",
                None,
            )

            total_tokens = raw_usage.get(
                "total_tokens",
                None,
            )

            usage = UsageSummary(
                input_tokens=(
                    int(input_tokens)
                    if isinstance(input_tokens, int)
                    else None
                ),
                output_tokens=(
                    int(output_tokens)
                    if isinstance(output_tokens, int)
                    else None
                ),
                total_tokens=(
                    int(total_tokens)
                    if isinstance(total_tokens, int)
                    else None
                ),
                raw=raw_usage,
            )

        cost = estimate_chat_cost_from_usage(
            model=model,
            usage=usage,
        )

    # ------------------------------------------------------------
    # whisper-1 / gpt-4o-mini-transcribe / gpt-4o-transcribe
    # - 従来どおり音声分単価を使用する
    # ------------------------------------------------------------
    elif audio_seconds is not None:
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
        usage=usage,
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
    response_format: str,
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
        response_format=response_format,
        language=language,
        prompt=prompt,
        timeout_sec=timeout_sec,
        extra=extra,
    )

    # ============================================================
    # TEMP DEBUG
    # Gemini usage dump
    # 概算(cost=None)の原因調査
    # ============================================================
    # print("============================================================")
    # print("GEMINI_TRANSCRIBE_USAGE_DEBUG")
    # print(repr(res.usage))
    # print("============================================================")

    # ============================================================
    # TEMP DEBUG END
    # Gemini usage dump
    # ============================================================

    # ============================================================
    # cost（正本）
    # - Gemini は音声分単価ではなく usage tokens ベースで概算する
    # - usage から input/output tokens が取れない場合は None
    # - 為替は estimate_chat_cost_from_usage 側（fx 正本）で解決する
    # ============================================================
    cost = estimate_chat_cost_from_usage(
        model=model,
        usage=res.usage,
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