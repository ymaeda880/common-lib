# -*- coding: utf-8 -*-
# common_lib/busy/apply_transcribe_result.py
# ============================================================
# busy 反映ユーティリティ（Transcribe 正本）
#
# 目的：
# - TranscribeResult（res）から cost を「返ってきた範囲だけ」取り出し、
#   busy_run（br）へ反映する
# - 推計しない：取れないものは None のまま・busyへ書かない
# - pages 側の後処理ロジックを薄くする（共通化）
# ============================================================

from __future__ import annotations

# ============================================================
# 標準ライブラリ
# ============================================================
from dataclasses import dataclass
from typing import Any, Optional


# ============================================================
# 戻り値（pages表示用にまとめる）
# ============================================================
@dataclass(frozen=True)
class AppliedTranscribePostprocess:
    cost_obj: Any
    note: str = ""


# ============================================================
# 内部：数値判定
# ============================================================
def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float))


# ============================================================
# 正本：TranscribeResult → busy_run(br) 反映
# ============================================================
def apply_transcribe_result_to_busy(
    *,
    br: Any,
    res: Any,
    note_ok_cost: str = "ok_cost",
    note_no_cost: str = "no_cost",
) -> AppliedTranscribePostprocess:
    """
    返ってきた範囲だけ busy に反映し、表示用の値を返す。

    方針：
      - cost は res.cost がある場合のみ見る
      - usd/jpy が両方数値のときだけ br.set_cost
      - 推計しない
    """
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

    note = note_ok_cost if wrote_cost else note_no_cost
    try:
        br.add_finish_meta(note=str(note))
    except Exception:
        pass

    return AppliedTranscribePostprocess(
        cost_obj=cost_obj,
        note=str(note),
    )
