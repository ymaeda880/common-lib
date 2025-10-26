# projects/openai/pricing/costs.py
# =============================================================================
# 料金見積りユーティリティ（共通ライブラリ）
# - 為替レートの取得（環境変数 / Streamlit secrets / デフォルト）
# - モデル（chat / embedding / 音声）単価テーブル
# - 見積り関数（USD/JPY換算）
# - meta.jsonl からの埋め込み費用サマリ
# - Streamlit 用の費用サマリ描画（チャットのみ／チャット+埋め込み）
# =============================================================================

"""
===============================================================================
openai.pricing.costs — モデル料金・為替換算ユーティリティ
===============================================================================

概要
----
OpenAI モデル（chat / embedding / audio）の **概算費用** を計算する共通ライブラリ。
Streamlit アプリ／バッチの両方で使用できます。USD→JPY 換算は自動。

機能
----
* 料金テーブル:
  - ``MODEL_PRICES_USD`` : Chatモデル単価（USD / 1M tokens）
  - ``EMBEDDING_PRICES_USD`` : 埋め込み単価（USD / 1M tokens）
  - ``AUDIO_PRICES_USD_PER_MIN`` : Whisper 単価（USD / 分）
* 為替レート:
  1) 環境変数 ``USDJPY`` → 2) ``st.secrets["USDJPY"]`` → 3) 150.0
* 見積りAPI:
  - ``estimate_chat_cost(model, usage)``
  - ``estimate_embedding_cost(model, tokens)``
  - ``estimate_transcribe_cost(model, seconds)``
  - ``usd_to_jpy(usd)``
* Streamlit表示:
  - ``render_chat_only_summary(...)`` : **Chatのみ** の費用サマリを3カラム表示
  - ``render_usage_summary(...)`` : Embedding+Chat の費用サマリを3カラム表示
* メタから自動集計:
  - ``summarize_embedding_cost_from_meta(meta_path)`` :
    meta.jsonl の ``chunk_len_tokens`` を合算して埋め込み費用を見積り

クイックスタート
----------------
1) Chat / Embedding の費用を計算:
    .. code-block:: python

        from openai.pricing.costs import ChatUsage, estimate_chat_cost, estimate_embedding_cost

        usage = ChatUsage(input_tokens=1200, output_tokens=800)
        estimate_chat_cost("gpt-5-mini", usage)  # => {"usd": ..., "jpy": ...}

        estimate_embedding_cost("text-embedding-3-large", 250_000)  # => {"usd": ..., "jpy": ...}

2) Streamlit で UI 表示:
    .. code-block:: python

        from openai.pricing.costs import render_chat_only_summary

        render_chat_only_summary(
            title="今回ランの概算",
            model="gpt-5-mini",
            in_tokens=2_000,
            out_tokens=1_000,
        )

3) meta.jsonl から埋め込み費用をサマリ:
    .. code-block:: python

        from pathlib import Path
        from openai.pricing.costs import summarize_embedding_cost_from_meta

        summary = summarize_embedding_cost_from_meta(Path("vs_root/meta.jsonl"))
        summary["jpy"]  # 合計見積り（JPY）

注意
----
* UI関数（``render_*``）は Streamlit 環境でのみ使用可（遅延 import）。
* 料金テーブルの値は全アプリに影響します。更新時はバージョン管理推奨。
* ``DEFAULT_USDJPY`` は自動判定されますが、テスト時は環境変数で上書きできます。

作成者: PREC 開発チーム（Y.M.） / 最終更新: 2025-10
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import math
import os

__all__ = [
    "DEFAULT_USDJPY",
    "MODEL_PRICES_USD",
    "EMBEDDING_PRICES_USD",
    "AUDIO_PRICES_USD_PER_MIN",
    "ChatUsage",
    "usd_to_jpy",
    "estimate_chat_cost",
    "estimate_embedding_cost",
    "estimate_transcribe_cost",
    "render_usage_summary",
    "render_chat_only_summary",
    "summarize_embedding_cost_from_meta",
]

# =============================================================================
# 為替の初期値（環境変数 → Streamlit secrets → デフォルト）
# =============================================================================


def _get_usdjpy_default() -> float:
    """
    優先度:
      1) 環境変数 USDJPY
      2) streamlit.secrets["USDJPY"]（可能なら）
      3) 150.0
    """
    v = os.environ.get("USDJPY")
    if v:
        try:
            return float(v)
        except ValueError:
            pass

    try:
        # Streamlit がない環境でも動くように遅延 import
        import streamlit as st  # type: ignore

        v2 = st.secrets.get("USDJPY", None)
        if v2 is not None:
            return float(v2)
    except Exception:
        pass

    return 150.0


DEFAULT_USDJPY: float = _get_usdjpy_default()

# =============================================================================
# モデル価格（USD / 100万トークン）
# =============================================================================

MODEL_PRICES_USD: Dict[str, Dict[str, float]] = {
    "gpt-5": {"in": 1.25, "out": 10.00},
    "gpt-5-mini": {"in": 0.25, "out": 2.00},
    "gpt-5-nano": {"in": 0.05, "out": 0.40},
    "gpt-4o": {"in": 2.50, "out": 10.00},
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "gpt-4.1": {"in": 2.00, "out": 8.00},  # 参考
    "gpt-4.1-mini": {"in": 0.40, "out": 1.60},  # 参考
    "gpt-3.5-turbo": {"in": 0.50, "out": 1.50},  # 参考
}

# =============================================================================
# Embedding 価格（USD / 100万トークン）
# =============================================================================

EMBEDDING_PRICES_USD: Dict[str, float] = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,  # レガシー
}

# =============================================================================
# 音声（Whisper）価格（USD / 分）
# =============================================================================

AUDIO_PRICES_USD_PER_MIN: Dict[str, float] = {
    "whisper-1": 0.006,  # $0.006 / 分
}

MILLION = 1_000_000


# =============================================================================
# データクラス
# =============================================================================
@dataclass
class ChatUsage:
    input_tokens: int
    output_tokens: int


# =============================================================================
# 通貨変換と見積り
# =============================================================================
def usd_to_jpy(usd: float, rate: float = DEFAULT_USDJPY) -> float:
    """USD → JPY。小数第2位で丸め。"""
    return round(float(usd) * float(rate), 2)


def estimate_chat_cost(model: str, usage: ChatUsage) -> Dict[str, float]:
    """
    Chat モデルの概算費用（USD/JPY）を計算。
    :param model: モデル名（MODEL_PRICES_USD のキー）
    :param usage: ChatUsage(input_tokens, output_tokens)
    """
    if model not in MODEL_PRICES_USD:
        raise ValueError(f"単価未設定のモデル: {model}")

    price = MODEL_PRICES_USD[model]
    in_cost = (max(0, int(usage.input_tokens)) / MILLION) * float(price["in"])
    out_cost = (max(0, int(usage.output_tokens)) / MILLION) * float(price["out"])
    usd = round(in_cost + out_cost, 6)
    jpy = usd_to_jpy(usd)
    return {"usd": usd, "jpy": jpy}


def estimate_embedding_cost(
    model: str, input_tokens: int, *, rate: float = DEFAULT_USDJPY
) -> Dict[str, float]:
    """
    Embedding の概算費用（USD/JPY）を計算。
    :param model: 埋め込みモデル名（EMBEDDING_PRICES_USD のキー）
    :param input_tokens: 入力トークン数
    :param rate: 為替レート
    """
    if model not in EMBEDDING_PRICES_USD:
        raise ValueError(f"単価未設定の埋め込みモデル: {model}")

    usd = round((max(0, int(input_tokens)) / MILLION) * float(EMBEDDING_PRICES_USD[model]), 6)
    jpy = usd_to_jpy(usd, rate=rate)
    return {"usd": usd, "jpy": jpy}


def estimate_transcribe_cost(model: str, seconds: float) -> Dict[str, float]:
    """
    音声文字起こし（Whisper）の概算費用（USD/JPY）を計算。
    :param model: "whisper-1" など
    :param seconds: 音声秒数
    """
    if model not in AUDIO_PRICES_USD_PER_MIN:
        raise ValueError(f"単価未設定の音声モデル: {model}")

    per_min = float(AUDIO_PRICES_USD_PER_MIN[model])
    minutes = max(0.0, float(seconds)) / 60.0
    usd = round(per_min * minutes, 6)
    jpy = usd_to_jpy(usd)
    return {"usd": usd, "jpy": jpy}


# =============================================================================
# UI（Streamlit）向け：使用量の概算描画
#   ※ Streamlit を使わない環境でも import できるよう遅延 import
# =============================================================================
def _model_prices_per_1k() -> Dict[str, Dict[str, float]]:
    """MODEL_PRICES_USD（USD/1M tok）から USD/1K tok を作る"""
    return {
        m: {
            "in": float(p.get("in", 0.0)) / 1000.0,
            "out": float(p.get("out", 0.0)) / 1000.0,
        }
        for m, p in MODEL_PRICES_USD.items()
    }


def render_usage_summary(
    *,
    embedding_model: str,
    embedding_tokens: int,
    chat_model: str,
    chat_prompt_tokens: int,
    chat_completion_tokens: int,
    use_backend_openai: bool,
    title: str = "📊 使用量の概算",
) -> Dict[str, float]:
    """
    使用量/費用の概算を3カラムで描画する（Streamlit）。
    - embedding_tokens が 0 の場合は Embedding を 0 として扱う
    - use_backend_openai が False の場合は Chat を 0 として扱う
    """
    try:
        import streamlit as st  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "render_usage_summary は Streamlit 環境でのみ利用できます。"
        ) from e

    emb_cost = {"usd": 0.0, "jpy": 0.0}
    if embedding_tokens and embedding_model:
        emb_cost = estimate_embedding_cost(embedding_model, embedding_tokens)

    chat_cost = {"usd": 0.0, "jpy": 0.0}
    if use_backend_openai and chat_model and (chat_prompt_tokens or chat_completion_tokens):
        chat_cost = estimate_chat_cost(
            chat_model,
            ChatUsage(
                input_tokens=chat_prompt_tokens or 0,
                output_tokens=chat_completion_tokens or 0,
            ),
        )

    total_usd = float(emb_cost["usd"]) + float(chat_cost["usd"])
    total_jpy = usd_to_jpy(total_usd, rate=DEFAULT_USDJPY)

    st.markdown(f"### {title}")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("合計 (JPY)", f"{total_jpy:,.2f} 円")
        st.caption(f"為替 {DEFAULT_USDJPY:.2f} JPY/USD")
    with c2:
        st.write("**内訳 (USD)**")
        st.write(f"- Embedding: `${emb_cost['usd']:.6f}`")
        if use_backend_openai:
            st.write(
                f"- Chat: `${chat_cost['usd']:.6f}` (in={chat_prompt_tokens:,}, out={chat_completion_tokens:,})"
            )
        st.write(f"- 合計: `${total_usd:.6f}`")
    with c3:
        per_1k = _model_prices_per_1k()
        emb_per_1k = float(EMBEDDING_PRICES_USD.get(embedding_model, 0.0)) / 1000.0
        chat_in = float(per_1k.get(chat_model, {}).get("in", 0.0))
        chat_out = float(per_1k.get(chat_model, {}).get("out", 0.0))
        st.write("**単価 (USD / 1K tok)**")
        st.write(f"- Embedding: `${emb_per_1k:.5f}`（{embedding_model}）")
        st.write(f"- Chat 入力: `${chat_in:.5f}`（{chat_model}）")
        st.write(f"- Chat 出力: `${chat_out:.5f}`（{chat_model}）")

    # 参照用に返す
    return {
        "embedding_usd": float(emb_cost["usd"]),
        "chat_usd": float(chat_cost["usd"]),
        "total_usd": float(total_usd),
        "total_jpy": float(total_jpy),
    }


def render_chat_only_summary(
    *,
    title: str,
    model: str,
    in_tokens: int,
    out_tokens: int,
) -> Dict[str, float]:
    """
    Embedding を表示せず、Chat のみの費用サマリを3カラムで描画する（Streamlit用）。
    戻り値: {"chat_usd": float, "total_usd": float, "total_jpy": float}
    """
    try:
        import streamlit as st  # type: ignore
    except Exception as e:
        raise RuntimeError("render_chat_only_summary は Streamlit 環境でのみ利用できます。") from e

    # 概算コスト（USD/JPY）
    cost = estimate_chat_cost(
        model,
        ChatUsage(input_tokens=int(in_tokens or 0), output_tokens=int(out_tokens or 0)),
    )
    total_usd = float(cost["usd"])
    total_jpy = usd_to_jpy(total_usd, rate=DEFAULT_USDJPY)

    # 単価（USD / 1K tokens）
    per_1k_in = float(MODEL_PRICES_USD.get(model, {}).get("in", 0.0)) / 1000.0
    per_1k_out = float(MODEL_PRICES_USD.get(model, {}).get("out", 0.0)) / 1000.0

    # 表示
    st.markdown(f"### {title}")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("合計 (JPY)", f"{total_jpy:,.2f} 円")
        st.caption(f"為替 {DEFAULT_USDJPY:.2f} JPY/USD")
    with c2:
        st.write("**内訳 (USD)**")
        st.write(f"- Chat: `${total_usd:.6f}` (in={in_tokens:,}, out={out_tokens:,})")
    with c3:
        st.write("**単価 (USD / 1K tok)**")
        st.write(f"- Chat 入力: `${per_1k_in:.5f}`（{model}）")
        st.write(f"- Chat 出力: `${per_1k_out:.5f}`（{model}）")

    return {"chat_usd": total_usd, "total_usd": total_usd, "total_jpy": float(total_jpy)}


# =============================================================================
# meta.jsonl から安全に概算するユーティリティ
# =============================================================================
def _percentile(values: List[int], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0:
        return float(min(values))
    if q >= 1:
        return float(max(values))
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(math.ceil(q * len(s)) - 1)))
    return float(s[idx])


def summarize_embedding_cost_from_meta(
    meta_path: Path,
    model: str = "text-embedding-3-large",
    *,
    rate: float = DEFAULT_USDJPY,
    outlier_tok_threshold: int = 8192,
    include_source_paths: Optional[List[str]] = None,  # 特定のPDFだけに絞る
    created_after_iso: Optional[str] = None,  # "2025-10-15T12:34:56Z" など
) -> Dict[str, Any]:
    """
    meta.jsonl を読み、chunk_len_tokens を合算して埋め込みコストを概算。
    同時にサニティ情報と警告を返す。

    Returns:
    {
      "model": str,
      "price_per_1M": float,
      "rate": float,
      "total_tokens": int,
      "n_chunks": int,
      "avg_tok": float, "p95_tok": float, "max_tok": int,
      "skipped_outliers": int,
      "had_chars_without_tokens": bool,
      "warnings": List[str],
      "usd": float, "jpy": float
    }
    """
    warnings: List[str] = []
    tokens_list: List[int] = []
    skipped_outliers = 0
    had_chars_without_tokens = False

    if not meta_path.exists():
        est0 = {"usd": 0.0, "jpy": 0.0}
        return {
            "model": model,
            "price_per_1M": float(EMBEDDING_PRICES_USD.get(model, 0.0)),
            "rate": float(rate),
            "total_tokens": 0,
            "n_chunks": 0,
            "avg_tok": 0.0,
            "p95_tok": 0.0,
            "max_tok": 0,
            "skipped_outliers": 0,
            "had_chars_without_tokens": False,
            "warnings": ["meta.jsonl が見つかりません"],
            "usd": float(est0["usd"]),
            "jpy": float(est0["jpy"]),
        }

    with meta_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue

            # ① ファイル名フィルタ（include_source_paths）
            if include_source_paths:
                src = obj.get("source_path") or obj.get("path") or obj.get("file")
                if not src or not any(src.endswith(p) or src == p for p in include_source_paths):
                    continue

            # ② 作成時刻フィルタ（created_after_iso）
            if created_after_iso and (ca := obj.get("created_at")):
                if str(ca) < str(created_after_iso):
                    continue

            # ③ トークン情報取得
            if "chunk_len_tokens" not in obj and "chunk_len_chars" in obj:
                had_chars_without_tokens = True

            tok = int(obj.get("chunk_len_tokens", 0) or 0)
            if tok < 0:
                continue
            if outlier_tok_threshold and tok > int(outlier_tok_threshold):
                skipped_outliers += 1
                continue

            tokens_list.append(tok)

    # 集計
    total_tokens = int(sum(tokens_list))
    n = len(tokens_list)
    avg_tok = (total_tokens / n) if n else 0.0
    p95_tok = _percentile(tokens_list, 0.95) if n else 0.0
    max_tok = max(tokens_list) if n else 0

    # チェックと警告
    price_per_1M = float(EMBEDDING_PRICES_USD.get(model, 0.0))
    if price_per_1M <= 0:
        warnings.append(f"埋め込みモデルの単価が見つかりません: {model}")
    if rate > 1000:
        warnings.append(f"為替レートが異常に大きい可能性があります: {rate:.2f} JPY/USD")
    if had_chars_without_tokens:
        warnings.append(
            "`chunk_len_tokens` が無く `chunk_len_chars` のみの行が見つかりました。"
            "文字数をトークン数として誤集計している可能性があります。"
        )
    if skipped_outliers > 0:
        warnings.append(f"外れ値チャンク（>{outlier_tok_threshold} tok）を {skipped_outliers} 件スキップしました。")

    # コスト計算
    est = estimate_embedding_cost(model, total_tokens, rate=rate)

    return {
        "model": model,
        "price_per_1M": price_per_1M,
        "rate": float(rate),
        "total_tokens": total_tokens,
        "n_chunks": n,
        "avg_tok": float(avg_tok),
        "p95_tok": float(p95_tok),
        "max_tok": int(max_tok),
        "skipped_outliers": skipped_outliers,
        "had_chars_without_tokens": had_chars_without_tokens,
        "warnings": warnings,
        "usd": float(est["usd"]),
        "jpy": float(est["jpy"]),
    }
