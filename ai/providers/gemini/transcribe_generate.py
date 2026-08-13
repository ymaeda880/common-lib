# -*- coding: utf-8 -*-
# common_lib/ai/providers/gemini/transcribe_generate.py
# ============================================================
# Gemini 音声文字起こし
#
# 機能：
# - 通常文字起こし
# - response_format="srt" の場合のみSRT形式を要求
# - google-genai のレスポンスを TranscribeResult へ正規化
# - usage_metadata を UsageSummary へ変換
#
# 方針：
# - 通常文字起こしの既存プロンプトは変更しない
# - SRT指定時だけ追加指示を加える
# - DEBUGではGemini raw responseの状態を確認する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================

from typing import Any, Dict, Optional

from ...types import (
    TranscribeResult,
    UsageSummary,
)

from ...errors import ProviderError

from .client import configure_gemini


# ============================================================
# Gemini transcribe
# ============================================================

def transcribe_audio(
    *,
    model: str,
    audio_bytes: bytes,
    mime_type: str,
    filename: str,
    response_format: str = "text",
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    timeout_sec: int = 600,
    extra: Optional[Dict[str, Any]] = None,
) -> TranscribeResult:
    """
    Geminiによる音声文字起こし。

    通常文字起こし：
    - 従来の文字起こしプロンプトをそのまま使用する

    タイムスタンプ付き文字起こし：
    - response_format="srt" の場合のみSRT形式を要求する
    - 後段の共通SRT処理で解析できる形式へ統一する
    """

    # ============================================================
    # 通常文字起こし
    # - 現在動作しているプロンプトを変更しない
    # ============================================================

    instr_parts = [
        "この音声を日本語で正確に文字起こししてください。",
        "日本語は分かち書きにしないでください（単語の間に不要な半角スペースを入れない）。",
        "句読点（、。）を適切に補い、自然な文章として出力してください。",
    ]

    # ============================================================
    # タイムスタンプ付き文字起こし
    # - response_format="srt" の場合だけ追加
    # - 通常文字起こしには影響させない
    # ============================================================

    if str(response_format).lower() == "srt":
        instr_parts.extend(
            [
                "出力には音声内の発話時刻を付けてください。",
                "出力形式は必ず標準的なSRT形式にしてください。",
                "各字幕は、連番、開始時刻 --> 終了時刻、本文の順で出力してください。",
                "時刻形式は HH:MM:SS,mmm --> HH:MM:SS,mmm としてください。",
                "タイムスタンプは実際の音声上の時刻に合わせてください。",
                "音声の先頭を 00:00:00,000 としてください。",
                "発話内容を省略せず、音声に存在しない内容を追加しないでください。",
                "Markdownのコードブロックは使用しないでください。",
                "説明文や前置きは付けず、SRT本文だけを出力してください。",
            ]
        )

    # ============================================================
    # 言語指定
    # ============================================================

    if (
        language
        and str(language).strip()
    ):
        instr_parts.append(
            (
                f"言語コードは "
                f"{str(language).strip()} "
                f"を優先（不明なら自動判定）。"
            )
        )

    # ============================================================
    # 追加プロンプト
    # ============================================================

    if (
        prompt
        and str(prompt).strip()
    ):
        instr_parts.append(
            str(prompt).strip()
        )

    instruction = " ".join(
        instr_parts
    )

    # ============================================================
    # Gemini client
    # ============================================================

    client = configure_gemini()

    # ============================================================
    # generate_content
    # ============================================================

    try:
        from google.genai import types  # type: ignore

        resp = client.models.generate_content(
            model=model,
            contents=[
                instruction,
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type=mime_type,
                ),
            ],
        )

        # ========================================================
        # DEBUG START
        # Gemini raw response
        # ========================================================

        # print("=" * 80)
        # print("GEMINI_RAW_RESPONSE_DEBUG")

        # try:
        #     print(
        #         "response_text_len =",
        #         len(
        #             getattr(
        #                 resp,
        #                 "text",
        #                 "",
        #             )
        #             or ""
        #         ),
        #     )
        # except Exception as e:
        #     print(
        #         "response_text_len error =",
        #         repr(e),
        #     )

        # try:
        #     print(
        #         "candidate_count =",
        #         len(
        #             getattr(
        #                 resp,
        #                 "candidates",
        #                 None,
        #             )
        #             or []
        #         ),
        #     )
        # except Exception as e:
        #     print(
        #         "candidate_count error =",
        #         repr(e),
        #     )

        # try:
        #     print(
        #         "finish_reason =",
        #         repr(
        #             resp
        #             .candidates[0]
        #             .finish_reason
        #         ),
        #     )
        # except Exception as e:
        #     print(
        #         "finish_reason error =",
        #         repr(e),
        #     )

        # try:
        #     print(
        #         "candidate_content =",
        #         repr(
        #             resp
        #             .candidates[0]
        #             .content
        #         ),
        #     )
        # except Exception as e:
        #     print(
        #         "candidate_content error =",
        #         repr(e),
        #     )

        # try:
        #     print(
        #         "prompt_feedback =",
        #         repr(
        #             getattr(
        #                 resp,
        #                 "prompt_feedback",
        #                 None,
        #             )
        #         ),
        #     )
        # except Exception as e:
        #     print(
        #         "prompt_feedback error =",
        #         repr(e),
        #     )

        # print("=" * 80)

        # ========================================================
        # DEBUG END
        # ========================================================

        # ========================================================
        # Gemini usage metadata
        # ========================================================

        usage_metadata = getattr(
            resp,
            "usage_metadata",
            None,
        )

    except Exception as e:
        raise ProviderError(
            (
                "Gemini transcribe "
                f"generate_content failed: {e}"
            ),
            provider="gemini",
        ) from e

    # ============================================================
    # response text
    # ============================================================

    text = (
        getattr(
            resp,
            "text",
            "",
        )
        or ""
    )

    # ============================================================
    # SRT出力の軽微な正規化
    # - GeminiがMarkdownコードブロックを付けた場合だけ除去
    # - 通常文字起こしには一切適用しない
    # ============================================================

    if str(response_format).lower() == "srt":
        text = str(
            text
        ).strip()

        if text.startswith(
            "```srt"
        ):
            text = text[
                len("```srt"):
            ].lstrip()

        elif text.startswith(
            "```"
        ):
            text = text[
                len("```"):
            ].lstrip()

        if text.endswith(
            "```"
        ):
            text = text[
                :-3
            ].rstrip()

    # ============================================================
    # usage summary
    # - prompt_token_count      -> input_tokens
    # - candidates_token_count  -> output_tokens
    # - total_token_count       -> total_tokens
    # ============================================================

    usage = UsageSummary(
        input_tokens=getattr(
            usage_metadata,
            "prompt_token_count",
            None,
        ),
        output_tokens=getattr(
            usage_metadata,
            "candidates_token_count",
            None,
        ),
        total_tokens=getattr(
            usage_metadata,
            "total_token_count",
            None,
        ),
        raw=usage_metadata,
    )

    # ============================================================
    # result
    # ============================================================

    return TranscribeResult(
        provider="gemini",
        model=model,
        text=str(
            text
        ),
        request_id="gemini",
        meta={
            "mime_type": mime_type,
            "response_format": response_format,
        },
        usage=usage,
        raw=None,
    )