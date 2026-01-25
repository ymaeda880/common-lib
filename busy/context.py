# common_lib/busy/context.py
# =============================================================================
# busy（ai_runs.db）コンテキストマネージャ（共通ライブラリ / busy）
# - with busy_run(...) as br: で開始/終了記録を自動化してページ側を短くする
# - __enter__ で開始記録、__exit__ で success/error を自動確定
# - 例外は握りつぶさない（ログだけ残す）
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .recorder import RunTimer
from .helpers import busy_start, busy_finish_success, busy_finish_error


@dataclass
class BusyRun:
    projects_root: Path
    user_sub: str
    app_name: str
    page_name: str
    task_type: str
    provider: str
    model: str
    meta: dict[str, Any] = field(default_factory=dict)

    usd_jpy: Optional[float] = None
    phase: str = "api_call"

    # runtime
    run_id: str = ""
    timer: Optional[RunTimer] = None

    # metrics（ページ側でセット）
    in_tok: Optional[int] = None
    out_tok: Optional[int] = None
    cost_usd: Optional[float] = None
    cost_jpy: Optional[float] = None
    finish_meta: dict[str, Any] = field(default_factory=dict)

    def __enter__(self) -> "BusyRun":
        rid, t = busy_start(
            projects_root=self.projects_root,
            user_sub=self.user_sub,
            app_name=self.app_name,
            page_name=self.page_name,
            task_type=self.task_type,
            provider=self.provider,
            model=self.model,
            meta=self.meta,
            parent_run_id=None,
            phase=self.phase,
        )
        self.run_id = rid
        self.timer = t
        return self

    def set_usage(self, in_tok: Optional[int], out_tok: Optional[int]) -> None:
        self.in_tok = int(in_tok) if in_tok is not None else None
        self.out_tok = int(out_tok) if out_tok is not None else None

    def set_cost(self, cost_usd: Optional[float], cost_jpy: Optional[float]) -> None:
        self.cost_usd = float(cost_usd) if cost_usd is not None else None
        self.cost_jpy = float(cost_jpy) if cost_jpy is not None else None

    def add_finish_meta(self, **kwargs: Any) -> None:
        self.finish_meta.update(kwargs)

    def __exit__(self, exc_type, exc, tb) -> bool:
        timer = self.timer if self.timer is not None else RunTimer()

        if exc is None:
            busy_finish_success(
                projects_root=self.projects_root,
                run_id=self.run_id,
                timer=timer,
                in_tok=self.in_tok,
                out_tok=self.out_tok,
                cost_usd=self.cost_usd,
                usd_jpy=self.usd_jpy,
                cost_jpy=self.cost_jpy,
                meta=self.finish_meta,
                phase=self.phase,
            )
            return False

        busy_finish_error(
            projects_root=self.projects_root,
            run_id=self.run_id,
            timer=timer,
            exc=exc,
            in_tok=self.in_tok,
            out_tok=self.out_tok,
            cost_usd=self.cost_usd,
            usd_jpy=self.usd_jpy,
            cost_jpy=self.cost_jpy,
            meta=self.finish_meta,
            phase=self.phase,
        )
        return False


# ============================================================
# ★ ここが ImportError の根（busy_run をトップレベルで必ず定義）
# ============================================================
def busy_run(
    *,
    projects_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    task_type: str,
    provider: str,
    model: str,
    meta: Optional[dict[str, Any]] = None,
    usd_jpy: Optional[float] = None,
    phase: str = "api_call",
) -> BusyRun:
    return BusyRun(
        projects_root=projects_root,
        user_sub=str(user_sub),
        app_name=str(app_name),
        page_name=str(page_name),
        task_type=str(task_type),
        provider=str(provider),
        model=str(model),
        meta=meta or {},
        usd_jpy=usd_jpy,
        phase=phase,
    )
