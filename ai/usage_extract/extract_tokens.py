# -*- coding: utf-8 -*-
# common_lib/ai/usage/extract_tokens.py
# ============================================================
# Token usage extraction（正本）
#
# 目的：
# - OpenAI / Gemini のレスポンス（raw / common_lib結果）からトークン数を抽出する
# - Text / Embedding の両方に対応
# - 推計しない：返ってきた値だけ返す（取れなければ None）
#
# 対応する入力（代表例）：
# - common_lib.ai.types.TextResult / EmbeddingResult（usage属性を持つ想定）
# - OpenAI Responses API の res（res.usage.input_tokens/output_tokens/total_tokens）
# - OpenAI Embeddings API の res（res.usage.* の形揺れを吸収）
# - google-genai (Gemini) の resp（resp.usage_metadata.prompt_token_count 等）
# ============================================================

from __future__ import annotations

# ============================================================
# 標準ライブラリ
# ============================================================
from dataclasses import dataclass
from typing import Any, Optional, Tuple


# ============================================================
# 型：TokenUsage
# ============================================================
@dataclass(frozen=True)
class TokenUsage:
    # ------------------------------------------------------------
    # Text は input/output/total を持つ
    # Embedding は output_tokens が無いことが多い（None）
    # ------------------------------------------------------------
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]


# ============================================================
# 内部：dict / object から int を拾う（defensive）
# ============================================================
def _pick_int(obj: Any, key: str) -> Optional[int]:
    # ------------------------------------------------------------
    # None ガード
    # ------------------------------------------------------------
    if obj is None:
        return None

    # ------------------------------------------------------------
    # dict / object 両対応
    # ------------------------------------------------------------
    if isinstance(obj, dict):
        v = obj.get(key)
    else:
        v = getattr(obj, key, None)

    # ------------------------------------------------------------
    # int 化
    # ------------------------------------------------------------
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


# ============================================================
# 内部：usage から Text tokens を抜く（OpenAI互換）
# - input/output 優先、prompt/completion 互換も見る
# ============================================================
def _extract_text_tokens_from_usage(usage: Any) -> TokenUsage:
    # ------------------------------------------------------------
    # 入力/出力/合計（OpenAI Responses / common_lib UsageSummary 想定）
    # ------------------------------------------------------------
    in_tok = _pick_int(usage, "input_tokens")
    out_tok = _pick_int(usage, "output_tokens")
    total_tok = _pick_int(usage, "total_tokens")

    # ------------------------------------------------------------
    # 互換（ChatCompletions 等）
    # ------------------------------------------------------------
    if in_tok is None:
        in_tok = _pick_int(usage, "prompt_tokens")
    if out_tok is None:
        out_tok = _pick_int(usage, "completion_tokens")

    # ------------------------------------------------------------
    # total 互換（無い場合は None のまま：推計しない）
    # ------------------------------------------------------------
    return TokenUsage(input_tokens=in_tok, output_tokens=out_tok, total_tokens=total_tok)


# ============================================================
# 内部：Gemini usage_metadata から Text tokens を抜く
# ============================================================
def _extract_text_tokens_from_gemini_usage_metadata(um: Any) -> TokenUsage:
    # ------------------------------------------------------------
    # Gemini raw（google-genai）:
    # - prompt_token_count
    # - candidates_token_count
    # - total_token_count
    # ------------------------------------------------------------
    in_tok = (
        _pick_int(um, "input_tokens")
        or _pick_int(um, "prompt_tokens")
        or _pick_int(um, "prompt_token_count")
    )
    out_tok = (
        _pick_int(um, "output_tokens")
        or _pick_int(um, "completion_tokens")
        or _pick_int(um, "candidates_token_count")
    )
    total_tok = _pick_int(um, "total_tokens") or _pick_int(um, "total_token_count")

    return TokenUsage(input_tokens=in_tok, output_tokens=out_tok, total_tokens=total_tok)


# ============================================================
# 正本：Text tokens を抽出（OpenAI / Gemini）
# ============================================================
def extract_text_token_usage(*, res: Any, provider: Optional[str] = None) -> TokenUsage:
    """
    Text 実行結果から tokens を抽出する（推計しない）。
    優先順位：
      1) res.usage（common_libのTextResult/UsageSummary、OpenAI Responsesなど）
      2) Gemini の場合は res.usage_metadata も見る（raw response）
      3) dict/object の形揺れは _pick_int で吸収
    """
    # ------------------------------------------------------------
    # まず usage を見る（共通：TextResult / OpenAI Responses 等）
    # ------------------------------------------------------------
    usage = getattr(res, "usage", None)
    if usage is not None:
        return _extract_text_tokens_from_usage(usage)

    # ------------------------------------------------------------
    # 次に Gemini raw（usage_metadata）を見る
    # ------------------------------------------------------------
    if provider == "gemini":
        um = getattr(res, "usage_metadata", None)
        if um is not None:
            return _extract_text_tokens_from_gemini_usage_metadata(um)

    # ------------------------------------------------------------
    # fallback（何も取れない）
    # ------------------------------------------------------------
    return TokenUsage(input_tokens=None, output_tokens=None, total_tokens=None)


# ============================================================
# 内部：Embedding usage から tokens を抜く（defensive）
# - Embedding は「入力のみ」が基本：output は None
# ============================================================
def _extract_embedding_tokens_from_usage(usage: Any) -> TokenUsage:
    # ------------------------------------------------------------
    # OpenAI embeddings の usage は環境により表記が揺れる可能性があるので広めに見る
    # - prompt_tokens（よくある）
    # - input_tokens（将来的互換）
    # - total_tokens
    # ------------------------------------------------------------
    in_tok = _pick_int(usage, "input_tokens")
    if in_tok is None:
        in_tok = _pick_int(usage, "prompt_tokens")

    total_tok = _pick_int(usage, "total_tokens")

    return TokenUsage(input_tokens=in_tok, output_tokens=None, total_tokens=total_tok)


# ============================================================
# 正本：Embedding tokens を抽出（OpenAI / Gemini）
# ============================================================
def extract_embedding_token_usage(*, res: Any, provider: Optional[str] = None) -> TokenUsage:
    """
    Embedding 実行結果から tokens を抽出する（推計しない）。
    優先順位：
      1) res.usage（OpenAI embeddingsなど）
      2) Gemini の場合は res.usage_metadata（存在する実装の場合）
    """
    # ------------------------------------------------------------
    # usage（OpenAI embedding response 等）
    # ------------------------------------------------------------
    usage = getattr(res, "usage", None)
    if usage is not None:
        return _extract_embedding_tokens_from_usage(usage)

    # ------------------------------------------------------------
    # Gemini raw（usage_metadata）を念のため見る（Embedding系で返る場合）
    # ------------------------------------------------------------
    if provider == "gemini":
        um = getattr(res, "usage_metadata", None)
        if um is not None:
            # Embeddingで output 概念が無い前提：prompt_token_count を input に寄せる
            in_tok = (
                _pick_int(um, "input_tokens")
                or _pick_int(um, "prompt_tokens")
                or _pick_int(um, "prompt_token_count")
            )
            total_tok = _pick_int(um, "total_tokens") or _pick_int(um, "total_token_count")
            return TokenUsage(input_tokens=in_tok, output_tokens=None, total_tokens=total_tok)

    return TokenUsage(input_tokens=None, output_tokens=None, total_tokens=None)


# ============================================================
# 便利関数：Text（in,out）だけ欲しい場合
# ============================================================
def extract_text_in_out_tokens(*, res: Any, provider: Optional[str] = None) -> Tuple[Optional[int], Optional[int]]:
    u = extract_text_token_usage(res=res, provider=provider)
    return (u.input_tokens, u.output_tokens)
