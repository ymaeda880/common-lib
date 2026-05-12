# -*- coding: utf-8 -*-
# common_lib/busy/apply_ocr_result.py
# ============================================================
# OCR busy 反映ユーティリティ（正本）
#
# 目的：
# - GPT Vision OCR の複数ページ実行結果から tokens / cost を集計する
# - busy_run へ usage / cost を反映する
# - 推計しない：返ってきた値だけ使う
# ============================================================

from __future__ import annotations

# ============================================================
# 標準ライブラリ
# ============================================================
from dataclasses import dataclass
from typing import Any, Optional


# ============================================================
# 戻り値
# ============================================================
@dataclass(frozen=True)
class AppliedOcrPostprocess:
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
# 内部：cost集計用オブジェクト
# ============================================================
@dataclass(frozen=True)
class OcrCostSummary:
    usd: float
    jpy: float


# ============================================================
# 正本：OCR Vision results → busy_run(br) 反映
# ============================================================
def apply_ocr_results_to_busy(
    *,
    br: Any,
    results: list[Any],
    extract_text_in_out_tokens: Any,
    note_ok: str = "ok_ocr",
    note_no_usage: str = "ocr_no_usage",
    note_no_cost: str = "ocr_no_cost",
) -> AppliedOcrPostprocess:
    # ------------------------------------------------------------
    # tokens / cost を返ってきた範囲だけ集計する
    # ------------------------------------------------------------
    total_in = 0
    total_out = 0
    has_usage = False

    total_usd = 0.0
    total_jpy = 0.0
    has_cost = False

    for res in list(results or []):
        in_tok, out_tok = extract_text_in_out_tokens(res=res)

        if isinstance(in_tok, int) and isinstance(out_tok, int):
            total_in += int(in_tok)
            total_out += int(out_tok)
            has_usage = True

        cost_obj = getattr(res, "cost", None)
        if cost_obj is not None:
            usd = getattr(cost_obj, "usd", None)
            jpy = getattr(cost_obj, "jpy", None)

            if _is_num(usd) and _is_num(jpy):
                total_usd += float(usd)
                total_jpy += float(jpy)
                has_cost = True

    # ------------------------------------------------------------
    # busy: usage
    # ------------------------------------------------------------
    wrote_usage = False
    if has_usage:
        try:
            br.set_usage(int(total_in), int(total_out))
            wrote_usage = True
        except Exception:
            wrote_usage = False

    # ------------------------------------------------------------
    # busy: cost
    # ------------------------------------------------------------
    cost_summary = None
    wrote_cost = False

    if has_cost:
        cost_summary = OcrCostSummary(
            usd=float(total_usd),
            jpy=float(total_jpy),
        )
        try:
            br.set_cost(float(total_usd), float(total_jpy))
            wrote_cost = True
        except Exception:
            wrote_cost = False

    # ------------------------------------------------------------
    # note
    # ------------------------------------------------------------
    note = note_ok
    if not wrote_usage:
        note = note_no_usage
    if not wrote_cost:
        note = note if note != note_ok else note_no_cost

    try:
        br.add_finish_meta(note=str(note))
    except Exception:
        pass

    return AppliedOcrPostprocess(
        in_tokens=int(total_in) if has_usage else None,
        out_tokens=int(total_out) if has_usage else None,
        cost_obj=cost_summary,
        note=str(note),
    )