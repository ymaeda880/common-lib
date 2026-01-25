# -*- coding: utf-8 -*-
# common_lib/busy/apply_text_result.py
# ============================================================
# busy 反映ユーティリティ（正本）
#
# 目的：
# - TextResult（res）から tokens / cost を「返ってきた範囲だけ」抽出し、
#   busy_run（br）へ反映する
# - 推計しない：取れないものは None のまま・busyへ書かない
# - pages 側の後処理ロジックを薄くする（共通化）
# ============================================================

from __future__ import annotations

# ============================================================
# 標準ライブラリ
# ============================================================
from dataclasses import dataclass
from typing import Any, Optional, Tuple


# ============================================================
# 戻り値（pages表示用にまとめる）
# ============================================================
@dataclass(frozen=True)
class AppliedTextPostprocess:
    # ------------------------------------------------------------
    # tokens / cost は「取れた範囲だけ」
    # ------------------------------------------------------------
    in_tokens: Optional[int]
    out_tokens: Optional[int]
    cost_obj: Any
    note: str = ""


# ============================================================
# 内部：数値判定
# ============================================================
def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float))


# ============================================================
# 正本：TextResult → busy_run(br) 反映
# ============================================================
def apply_text_result_to_busy(
    *,
    br: Any,
    res: Any,
    extract_text_in_out_tokens: Any,
    note_ok: str = "ok",
    note_no_usage: str = "no_usage",
    note_no_cost: str = "no_cost",
) -> AppliedTextPostprocess:
    """
    返ってきた範囲だけ busy に反映し、表示用の値を返す。

    引数：
      br: busy_run のコンテキスト（with busy_run(...) as br: の br）
      res: TextResult（stream/通常どちらでも最終結果）
      extract_text_in_out_tokens: tokens抽出正本関数（dependency注入）
        - 例：common_lib.ai.usage_extract.extract_text_in_out_tokens

    方針：
      - tokens は input/output が両方 int のときだけ br.set_usage
      - cost は usd/jpy が両方数値のときだけ br.set_cost
      - 推計はしない
    """
    # ------------------------------------------------------------
    # tokens（正本）
    # ------------------------------------------------------------
    in_tok, out_tok = extract_text_in_out_tokens(res=res)

    # ------------------------------------------------------------
    # busy: usage（両方取れたときだけ）
    # ------------------------------------------------------------
    wrote_usage = False
    if isinstance(in_tok, int) and isinstance(out_tok, int):
        try:
            br.set_usage(int(in_tok), int(out_tok))
            wrote_usage = True
        except Exception:
            wrote_usage = False

    # ------------------------------------------------------------
    # cost（res.cost があれば）
    # ------------------------------------------------------------
    cost_obj = getattr(res, "cost", None)

    wrote_cost = False
    if cost_obj is not None:
        usd = getattr(cost_obj, "usd", None)
        jpy = getattr(cost_obj, "jpy", None)
        if _is_num(usd) and _is_num(jpy):
            try:
                br.set_cost(float(usd), float(jpy))
                wrote_cost = True
            except Exception:
                wrote_cost = False

    # ------------------------------------------------------------
    # note（最小）
    # ------------------------------------------------------------
    note = note_ok
    if not wrote_usage:
        note = note_no_usage
    if not wrote_cost:
        # usage は取れていて cost だけ無いケースもあるので分ける
        note = (note if note != note_ok else note_no_cost)

    try:
        br.add_finish_meta(note=str(note))
    except Exception:
        pass

    return AppliedTextPostprocess(
        in_tokens=in_tok if isinstance(in_tok, int) else None,
        out_tokens=out_tok if isinstance(out_tok, int) else None,
        cost_obj=cost_obj,
        note=str(note),
    )
