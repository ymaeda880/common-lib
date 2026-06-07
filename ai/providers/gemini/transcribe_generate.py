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

        # ============================================================
        # DEBUG : gemini raw response
        # ============================================================
        # print("=" * 60)
        # print("GEMINI_RAW_RESPONSE_DEBUG")

        # try:
        #     print("response_text_len =", len(getattr(resp, "text", "") or ""))
        # except Exception as e:
        #     print("response_text_len error =", e)

        # try:
        #     print("candidate_count =", len(resp.candidates))
        # except Exception as e:
        #     print("candidate_count error =", e)

        # try:
        #     print("finish_reason =", resp.candidates[0].finish_reason)
        # except Exception as e:
        #     print("finish_reason error =", e)

        # try:
        #     print("candidate_text_preview =")
        #     print(repr(str(resp.candidates[0].content.parts[0].text)[:300]))
        # except Exception as e:
        #     print("candidate_text_preview error =", e)

        # print("=" * 60)
        # ============================================================
        # DEBUG END
        # ============================================================

        # ============================================================
        # Gemini usage metadata
        # - google-genai の usage_metadata から token 数を取得する
        # - 取得できない場合は None のままにする
        # ============================================================
        usage_metadata = getattr(resp, "usage_metadata", None)

    except Exception as e:
        raise ProviderError(f"Gemini transcribe generate_content failed: {e}", provider="gemini") from e


    # ============================================================
    # response text
    # ============================================================
    text = getattr(resp, "text", "") or ""

    # ============================================================
    # TEMP DEBUG
    # Gemini response dump
    # ============================================================
    # print("============================================================")
    # print("GEMINI_RESPONSE_TYPE:", type(resp))
    # print("GEMINI_RESPONSE_REPR:")
    # print(repr(resp))
    # print("============================================================")
    # ============================================================
    # TEMP DEBUG END
    # ============================================================

    # ============================================================
    # usage summary
    # - Gemini は usage_metadata を UsageSummary に正規化する
    # - prompt_token_count を input_tokens として扱う
    # - candidates_token_count を output_tokens として扱う
    # - total_token_count を total_tokens として扱う
    # ============================================================
    usage = UsageSummary(
        input_tokens=getattr(usage_metadata, "prompt_token_count", None),
        output_tokens=getattr(usage_metadata, "candidates_token_count", None),
        total_tokens=getattr(usage_metadata, "total_token_count", None),
        raw=usage_metadata,
    )

    return TranscribeResult(
        provider="gemini",
        model=model,
        text=str(text),
        request_id="gemini",
        meta={"mime_type": mime_type},
        usage=usage,
        raw=None,
    )
