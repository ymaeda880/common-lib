"""通常テキスト応答の終了確認と案内。画面・業務固有の定義は持たない。"""
from __future__ import annotations

from .token_budget import assess_text_budget, suggest_output_token_limit


class TextResponseIncompleteError(ValueError):
    pass


class TextOutputLimitError(TextResponseIncompleteError):
    pass


def get_text_completion_status(result) -> str:
    raw = getattr(result, "raw", None)
    if not isinstance(raw, dict):
        return "unknown"
    details = raw.get("incomplete_details") or {}
    reason = details.get("reason", "") if isinstance(details, dict) else ""
    finish = str(raw.get("finish_reason", "") or "").rsplit(".", 1)[-1]
    if reason == "max_output_tokens" or finish == "MAX_TOKENS":
        return "output_limit"
    if raw.get("refusal") or raw.get("prompt_block_reason"):
        return "refused"
    # AzureのrawはAPI応答全体。OpenAI追加版は必要な終了情報のみを保持する。
    for item in raw.get("output") or []:
        if isinstance(item, dict):
            if any(isinstance(c, dict) and c.get("type") == "refusal" for c in item.get("content") or []):
                return "refused"
    if raw.get("status") in {"incomplete", "failed", "cancelled"}:
        return "incomplete"
    if finish and finish != "STOP":
        return "incomplete"
    if raw.get("status") == "completed" or finish == "STOP":
        return "completed"
    return "unknown"


def ensure_text_response_completed(result) -> None:
    """使用量・料金の記録後、業務結果の解析・保存前に呼ぶ。"""
    state = get_text_completion_status(result)
    if state == "output_limit":
        raise TextOutputLimitError("AIの出力が上限に達して途中で終了しました。")
    if state == "refused":
        raise TextResponseIncompleteError("AIが応答の生成を見送りました。出力上限による停止ではありません。")
    if state == "unknown":
        raise TextResponseIncompleteError("AIの終了状態を確認できませんでした。")
    if state != "completed":
        raise TextResponseIncompleteError("AIの応答が正常に完了していません。")
    if not str(getattr(result, "text", "") or "").strip():
        raise TextResponseIncompleteError("AIの応答本文が空でした。")


def build_output_limit_guidance(
    *, provider: str, model: str, failed_limit: int, current_limit: int,
    estimated_input_tokens: int, ui_max_output_tokens: int,
    setting_label: str = "最大出力トークン", action_label: str = "実行",
) -> str:
    prefix = f"前回は出力上限{int(failed_limit):,}トークンに達して途中で終了しました。"
    next_limit = suggest_output_token_limit(
        provider=provider, model=model, failed_limit=failed_limit,
        estimated_input_tokens=estimated_input_tokens, ui_max_output_tokens=ui_max_output_tokens,
    )
    if next_limit is None:
        return prefix + "この画面の設定範囲とモデル容量から、増やせる値を案内できません。管理担当者に解析条件の確認を依頼してください。"
    current_budget = assess_text_budget(
        provider=provider, model=model, estimated_input_tokens=estimated_input_tokens,
        max_output_tokens=current_limit,
    )
    if int(current_limit) >= next_limit and current_budget.state not in {"over", "output_over"}:
        return prefix + f"現在の設定は{int(current_limit):,}です。「{action_label}」を再実行してください。"
    if int(current_limit) > next_limit:
        return prefix + f"現在の出力設定では送信容量を超える可能性があります。サイドバーの「{setting_label}」を{next_limit:,}に設定して、「{action_label}」を再実行してください。この値は再試行の目安です。"
    return prefix + f"サイドバーの「{setting_label}」を{next_limit:,}に上げて、「{action_label}」を再実行してください。この値は再試行の目安です。"
