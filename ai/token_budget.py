"""通常テキストの概算と容量確認。API呼出し・自動切捨て・自動分割は行わない。"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any

from .model_limits import TextModelLimits, get_text_model_limits


def estimate_text_request_tokens(
    *, prompt: str, system: str | None = None, extra: dict[str, Any] | None = None,
) -> int:
    """文字種による概算。本文・指示・形式指定を含む。画像等には使用しない。

    英数字3字/token、空白4字/token、その他ASCII 1字/token、
    非ASCII 1.25token/字、補助面文字4token/字とし、包絡分256を加える。
    APIの実測値ではなく、表・OCRの乱れ等によって誤差が出る。
    """
    text = "\n".join((str(system or ""), str(prompt), json.dumps(extra or {}, ensure_ascii=False)))
    words = len(re.findall(r"[A-Za-z0-9]", text))
    spaces = sum(c.isspace() for c in text)
    other_ascii = sum(ord(c) < 128 and not c.isspace() and not c.isalnum() for c in text)
    non_ascii = sum(128 <= ord(c) <= 0xFFFF and not c.isspace() for c in text)
    supplementary = sum(ord(c) > 0xFFFF and not c.isspace() for c in text)
    estimate = words / 3 + spaces / 4 + other_ascii + non_ascii * 1.25 + supplementary * 4 + 256
    return int(math.ceil(estimate / 100) * 100)


@dataclass(frozen=True)
class TextBudget:
    state: str
    estimated_input_tokens: int
    guarded_input_tokens: int
    max_output_tokens: int
    limits: TextModelLimits | None
    message: str
    detail: str


def assess_text_budget(
    *, provider: str, model: str, estimated_input_tokens: int, max_output_tokens: int,
) -> TextBudget:
    """入力概算に20%の確認用余裕を加えて比較。出力が足りるかの予測ではない。"""
    estimated = max(0, int(estimated_input_tokens))
    output = max(0, int(max_output_tokens))
    guarded = math.ceil(estimated * 1.2)
    limits = get_text_model_limits(provider, model)
    state, message = "unknown", "選択モデルの容量情報が未登録のため、送信容量は事前確認できません。"
    details: list[str] = []
    if limits:
        ratios = []
        if limits.context_tokens is not None:
            ratios.append((guarded + output) / limits.context_tokens)
            details.append(f"推定入力＋出力枠：約{estimated + output:,} ／ 合計上限 {limits.context_tokens:,}トークン")
        if limits.input_tokens is not None:
            ratios.append(guarded / limits.input_tokens)
            details.append(f"入力上限 {limits.input_tokens:,}トークン")
        details.append(f"モデルの出力上限 {limits.output_tokens:,}トークン")
        if output > limits.output_tokens:
            state, message = "output_over", f"出力設定がモデルの上限を超えています。最大出力トークンを{limits.output_tokens:,}以下にしてください。"
        elif any(r > 1 for r in ratios):
            state, message = "over", "入力と出力枠が送信容量を超える可能性があります。資料の選択や解析モデルを見直してください。出力上限を増やしても、入力が多すぎる問題は解消しません。"
        elif any(r >= 0.9 for r in ratios):
            state, message = "near", "送信容量の上限に近づいています。文字からの概算のため、実際のトークン数によっては送信できない場合があります。"
        else:
            state, message = "within", "概算では、現在の入力と出力枠は選択モデルの送信容量に収まる見込みです。"
    return TextBudget(state, estimated, guarded, output, limits, message, " ／ ".join(details))


def suggest_output_token_limit(
    *, provider: str, model: str, failed_limit: int, estimated_input_tokens: int,
    ui_max_output_tokens: int,
) -> int | None:
    """次の再試行値を返す。成功保証ではない。容量不明・余裕なしなら値を作らない。"""
    limits = get_text_model_limits(provider, model)
    if limits is None:
        return None
    guarded = math.ceil(max(0, int(estimated_input_tokens)) * 1.2)
    if limits.input_tokens is not None and guarded > limits.input_tokens:
        return None
    ceiling = min(int(ui_max_output_tokens), limits.output_tokens)
    if limits.context_tokens is not None:
        ceiling = min(ceiling, limits.context_tokens - guarded)
    failed = int(failed_limit)
    target = 30_000 if failed < 30_000 else 50_000 if failed < 50_000 else math.ceil(failed * 1.5 / 1000) * 1000
    candidate = min(target, (ceiling // 1000) * 1000)
    return candidate if candidate > failed else None
