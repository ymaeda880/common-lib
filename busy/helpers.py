# common_lib/busy/helpers.py
# =============================================================================
# busy（ai_runs.db）記録ヘルパ（共通ライブラリ / busy）
# - ページ側の可読性を落とさず busy 記録を差し込むための短い関数群
# - busy_start / busy_finish_success / busy_finish_error
# - RunTimer の正本は recorder.py（types から import しない）
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from .types import UsageSummary, CostSummary
from .recorder import RunTimer
from .recorder import (
    new_run_start,
    start_run,
    new_finish_success,
    new_finish_error,
    finish_run,
)


def busy_start(
    *,
    projects_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    task_type: str,  # "text" / "image" / "transcribe" / ...
    provider: str,   # "openai" / "gemini" / ...
    model: str,
    meta: Optional[dict[str, Any]] = None,
    parent_run_id: str | None = None,
    phase: str = "api_call",
) -> tuple[str, RunTimer]:
    run_id = str(uuid.uuid4())
    timer = RunTimer()

    rs = new_run_start(
        run_id=run_id,
        parent_run_id=parent_run_id,
        user_sub=str(user_sub),
        app_name=str(app_name),
        page_name=str(page_name),
        task_type=str(task_type),
        provider=str(provider),
        model=str(model),
        meta=meta or {},
    )

    start_run(
        projects_root=projects_root,
        run=rs,
        event_phase=phase,
        event_message="busy_start",
        event_meta={"phase": phase},
    )
    return run_id, timer


def busy_finish_success(
    *,
    projects_root: Path,
    run_id: str,
    timer: RunTimer,
    in_tok: Optional[int] = None,
    out_tok: Optional[int] = None,
    cost_usd: Optional[float] = None,
    usd_jpy: Optional[float] = None,
    cost_jpy: Optional[float] = None,
    meta: Optional[dict[str, Any]] = None,
    phase: str = "api_call",
) -> None:
    fin = new_finish_success(
        run_id=str(run_id),
        timer=timer,
        usage=UsageSummary(
            input_tokens=int(in_tok) if in_tok is not None else None,
            output_tokens=int(out_tok) if out_tok is not None else None,
            total_tokens=(int(in_tok) + int(out_tok)) if (in_tok is not None and out_tok is not None) else None,
        ),
        cost=CostSummary(
            cost_usd=float(cost_usd) if cost_usd is not None else None,
            usd_jpy=float(usd_jpy) if usd_jpy is not None else None,
            cost_jpy=float(cost_jpy) if cost_jpy is not None else None,
        ),
        meta=meta or {},
    )

    finish_run(
        projects_root=projects_root,
        finish=fin,
        event_phase=phase,
        event_message="busy_end",
        event_meta={"status": "success", "phase": phase},
    )


def busy_finish_error(
    *,
    projects_root: Path,
    run_id: str,
    timer: RunTimer,
    exc: Exception,
    in_tok: Optional[int] = None,
    out_tok: Optional[int] = None,
    cost_usd: Optional[float] = None,
    usd_jpy: Optional[float] = None,
    cost_jpy: Optional[float] = None,
    meta: Optional[dict[str, Any]] = None,
    phase: str = "api_call",
) -> None:
    fin = new_finish_error(
        run_id=str(run_id),
        timer=timer,
        exc=exc,
        usage=UsageSummary(
            input_tokens=int(in_tok) if in_tok is not None else None,
            output_tokens=int(out_tok) if out_tok is not None else None,
            total_tokens=(int(in_tok) + int(out_tok)) if (in_tok is not None and out_tok is not None) else None,
        ),
        cost=CostSummary(
            cost_usd=float(cost_usd) if cost_usd is not None else None,
            usd_jpy=float(usd_jpy) if usd_jpy is not None else None,
            cost_jpy=float(cost_jpy) if cost_jpy is not None else None,
        ),
        meta=meta or {},
    )

    finish_run(
        projects_root=projects_root,
        finish=fin,
        event_phase=phase,
        event_message="busy_end",
        event_meta={"status": "error", "phase": phase},
    )
