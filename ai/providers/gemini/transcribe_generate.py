# -*- coding: utf-8 -*-
# common_lib/ai/providers/gemini/transcribe_generate.py

from __future__ import annotations

from typing import Any, Dict, Optional

from ...types import TranscribeResult, UsageSummary
from ...errors import ProviderError

from .client import configure_gemini


def transcribe_audio(
    *,
    model: str,
    audio_bytes: bytes,
    mime_type: str,
    filename: str,
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    timeout_sec: int = 600,
    extra: Optional[Dict[str, Any]] = None,
) -> TranscribeResult:
    """
    Gemini: instruction + audio bytes を generate_content に投げて文字起こし（最小版）
    """
    configure_gemini()

    #import google.generativeai as genai  # type: ignore

    instr_parts = [
        "この音声を日本語で正確に文字起こししてください。",
        "日本語は分かち書きにしないでください（単語の間に不要な半角スペースを入れない）。",
        "句読点（、。）を適切に補い、自然な文章として出力してください。",
    ]
    if language and str(language).strip():
        instr_parts.append(f"言語コードは {str(language).strip()} を優先（不明なら自動判定）。")
    if prompt and str(prompt).strip():
        instr_parts.append(str(prompt).strip())

    instruction = " ".join(instr_parts)


    # ============================================================
    # Gemini transcribe（google-genai）
    # - configure_gemini() は google-genai Client を返す前提
    # ============================================================
    client = configure_gemini()

    try:
        from google.genai import types  # type: ignore

        resp = client.models.generate_content(
            model=model,
            contents=[
                instruction,
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
        )
    except Exception as e:
        raise ProviderError(f"Gemini transcribe generate_content failed: {e}", provider="gemini") from e



    text = getattr(resp, "text", "") or ""
    usage = UsageSummary()

    return TranscribeResult(
        provider="gemini",
        model=model,
        text=str(text),
        request_id="gemini",
        meta={"mime_type": mime_type},
        usage=usage,
        raw=None,
    )
