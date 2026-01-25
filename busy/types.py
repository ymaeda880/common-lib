# common_lib/busy/types.py
# =============================================================================
# 型定義（共通ライブラリ / busy）
# - DB記録用のデータ束（RunStart / RunFinish）
# - tokens/cost の小型サマリ（UsageSummary / CostSummary）
# - RunTimer はここに置かない（recorder.py が正本）
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


RunStatus = Literal["running", "success", "error"]


@dataclass(frozen=True)
class UsageSummary:
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


@dataclass(frozen=True)
class CostSummary:
    cost_usd: Optional[float] = None
    usd_jpy: Optional[float] = None
    cost_jpy: Optional[float] = None


@dataclass(frozen=True)
class RunStart:
    run_id: str
    parent_run_id: Optional[str]
    user_sub: str
    app_name: str
    page_name: str
    task_type: str
    provider: str
    model: str
    started_at: str
    meta_json: Optional[str] = None


@dataclass(frozen=True)
class RunFinish:
    run_id: str
    status: RunStatus
    finished_at: str
    elapsed_ms: Optional[int]
    usage: UsageSummary
    cost: CostSummary
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    meta_json: Optional[str] = None
