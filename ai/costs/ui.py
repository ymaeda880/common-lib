# -*- coding: utf-8 -*-
# common_lib/ai/costs/ui.py
# =============================================================================
# cost UI（Streamlit専用）
# - 計算しない（CostResult を受け取って表示するだけ）
# =============================================================================

from __future__ import annotations

from typing import Optional

from .estimate import CostResult

from .pricing import (
    get_chat_price,
    get_embedding_price,
    get_audio_price,
    price_per_1k_from_per_1m,
)


def render_chat_cost_summary(
    *,
    title: str,
    model: str,
    in_tokens: Optional[int],
    out_tokens: Optional[int],
    cost: Optional[CostResult],
) -> None:
    """
    Chat の概算表示（Streamlit）
    - cost が None の場合は「未計算」表示
    """
    try:
        import streamlit as st  # type: ignore
    except Exception as e:
        raise RuntimeError("render_chat_cost_summary は Streamlit 環境でのみ利用できます") from e

    st.markdown(f"### {title}")

    c1, c2, c3 = st.columns(3)

    with c1:
        if cost is None:
            st.metric("概算（JPY）", "—")
        else:
            st.metric("概算（JPY）", f"{cost.jpy:,.2f} 円")
            st.caption(f"為替: {cost.usd_jpy:.2f} JPY/USD（{cost.fx_source}）")

    with c2:
        st.write("**内訳**")
        st.write(f"- input_tokens: {in_tokens if in_tokens is not None else '—'}")
        st.write(f"- output_tokens: {out_tokens if out_tokens is not None else '—'}")
        st.write(f"- usd: ${cost.usd:.6f}" if cost is not None else "- usd: —")

    with c3:
        st.write("**単価（USD / 1K tok）**")
        p = get_chat_price(model)
        if not p:
            st.write("- 未設定")
        else:
            st.write(f"- 入力: ${price_per_1k_from_per_1m(p.in_usd):.5f}")
            st.write(f"- 出力: ${price_per_1k_from_per_1m(p.out_usd):.5f}")
            st.caption(f"model: {model}")


def render_embedding_price_hint(*, model: str) -> None:
    """
    embedding の単価ヒント（Streamlit）
    """
    try:
        import streamlit as st  # type: ignore
    except Exception as e:
        raise RuntimeError("render_embedding_price_hint は Streamlit 環境でのみ利用できます") from e

    p = get_embedding_price(model)
    if p is None:
        st.write(f"- Embedding: 未設定（{model}）")
    else:
        st.write(f"- Embedding: ${price_per_1k_from_per_1m(float(p)):.5f} / 1K tok（{model}）")

def render_transcribe_cost_summary(
    *,
    title: str,
    model: str,
    audio_sec: Optional[float],
    cost: Optional[CostResult],
    notes: Optional[str] = None,
) -> None:
    """
    Transcribe の概算表示（Streamlit）
    - Chat と同じ「概算 / 内訳 / 単価」3カラム構成に揃える
    - 計算しない（CostResult を受け取って表示するだけ）
    """
    try:
        import streamlit as st  # type: ignore
    except Exception as e:
        raise RuntimeError("render_transcribe_cost_summary は Streamlit 環境でのみ利用できます") from e

    st.markdown(f"### {title}")

    c1, c2, c3 = st.columns(3)

    # ------------------------------------------------------------
    # c1: 概算（JPY）
    # ------------------------------------------------------------
    with c1:
        if cost is None:
            st.metric("概算（JPY）", "—")
        else:
            st.metric("概算（JPY）", f"{cost.jpy:,.2f} 円")
            st.caption(f"為替: {cost.usd_jpy:.2f} JPY/USD（{cost.fx_source}）")

    # ------------------------------------------------------------
    # c2: 内訳（Chat と同じ “- key: value” 形式）
    # ------------------------------------------------------------
    with c2:
        st.write("**内訳**")

        if audio_sec is None:
            st.write("- audio_seconds: —")
        else:
            try:
                sec = float(audio_sec)
                audio_min = sec / 60.0
                st.write(f"- audio_seconds: {sec:.1f} 秒 / {audio_min:.2f} 分")
            except Exception:
                st.write(f"- audio_seconds: {audio_sec}")

        st.write(f"- usd: ${cost.usd:.6f}" if cost is not None else "- usd: —")

        if notes:
            st.caption(str(notes))

    # ------------------------------------------------------------
    # c3: 単価（USD / min）※ pricing 正本から表示
    # ------------------------------------------------------------
    with c3:
        st.write("**単価（USD / min）**")
        p = get_audio_price(model)
        if p is None:
            st.write("- 未設定")
        else:
            st.write(f"- ${float(p.usd_per_min):.6f} / min")
        st.caption(f"model: {model}")
