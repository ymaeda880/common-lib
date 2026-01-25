# common_lib/busy/apply_usage_cost.py
# =============================================================================
# busy_run 補助：AI result から usage / cost を反映する
#
# 役割：
# - common_lib.ai.routing から返る result を調べる
# - usage / cost が「実測値として含まれていれば」 busy_run に反映
#
# 設計方針：
# - 推計は一切しない
# - result に含まれる値のみを使用
# - 無ければ何もしない（静かにスキップ）
# - ページ側で例外を出さない
#
# 想定利用箇所：
# - with busy_run(...) as br:
#       result = call_text / generate_image / transcribe_audio(...)
#       apply_usage_cost_if_any(br, result)
# =============================================================================

from __future__ import annotations
from typing import Any


# =============================================================================
# public API
# =============================================================================
def apply_usage_cost_if_any(br: Any, result: Any) -> None:
    """
    AI の result に usage / cost が含まれていれば、
    busy_run に反映する。

    Parameters
    ----------
    br : busy_run context
        with busy_run(...) as br: で得られるオブジェクト
    result : Any
        common_lib.ai.routing が返す Result オブジェクト
        （TextResult / ImageResult / TranscribeResult 等）
    """

    # -------------------------------------------------------------------------
    # usage（token 数）
    # -------------------------------------------------------------------------
    try:
        usage = getattr(result, "usage", None)
        in_tok = usage.input_tokens
        out_tok = usage.output_tokens

        if isinstance(in_tok, int) and isinstance(out_tok, int):
            br.set_usage(in_tok, out_tok)

    except (AttributeError, TypeError):
        # usage が無い / 型が違う場合は何もしない
        pass

    # -------------------------------------------------------------------------
    # cost（USD / JPY）
    # -------------------------------------------------------------------------
    try:
        cost = getattr(result, "cost", None)
        usd = cost.usd
        jpy = cost.jpy

        if isinstance(usd, (int, float)) and isinstance(jpy, (int, float)):
            br.set_cost(float(usd), float(jpy))

    except (AttributeError, TypeError):
        # cost が無い / 型が違う場合は何もしない
        pass
