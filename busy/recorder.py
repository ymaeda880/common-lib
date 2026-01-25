# common_lib/busy/recorder.py
# =============================================================================
# busy 永続記録（共通ライブラリ / busy）
# - ai_runs.db に run を INSERT/UPDATE（正本）
# - ai_busy_events に busy_start/busy_end 等のイベントを INSERT（永続）
# - 例外時も finally で必ず close（DB破損・ロックを避ける）
# - 時刻は JST ISO（sessions系と同じ思想）
# - ユーティリティ：
#   - RunTimer（elapsed_ms）
#   - new_run_start / new_finish_success / new_finish_error（データ束生成）
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any, Optional

from .db import connect, ensure_db
from .paths import resolve_ai_runs_db_path
from .types import CostSummary, RunFinish, RunStart, UsageSummary


def _now_jst_iso() -> str:
    """
    sessions系と同じ思想：JST固定のISO文字列。
    既存の time_utils があればそれを優先して使う。
    """
    try:
        from common_lib.sessions.time_utils import now_jst  # type: ignore
        dt = now_jst()
        return dt.isoformat(timespec="seconds")
    except Exception:
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        return datetime.now(jst).isoformat(timespec="seconds")


def _truncate(s: str, n: int = 2000) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def start_run(
    *,
    projects_root: Path,
    run: RunStart,
    event_phase: str = "api_call",
    event_message: str = "busy_start",
    event_meta: Optional[dict[str, Any]] = None,
) -> None:
    """
    run を開始（ai_runsへINSERT + busy_startイベント）。
    """
    db_path = resolve_ai_runs_db_path(projects_root)
    ensure_db(db_path)

    con = connect(db_path)
    try:
        con.execute(
            """
            INSERT INTO ai_runs(
              run_id, parent_run_id,
              user_sub, app_name, page_name,
              task_type, provider, model,
              status, started_at,
              meta_json
            )
            VALUES(
              :run_id, :parent_run_id,
              :user_sub, :app_name, :page_name,
              :task_type, :provider, :model,
              :status, :started_at,
              :meta_json
            )
            """,
            {
                "run_id": run.run_id,
                "parent_run_id": run.parent_run_id,
                "user_sub": run.user_sub,
                "app_name": run.app_name,
                "page_name": run.page_name,
                "task_type": run.task_type,
                "provider": run.provider,
                "model": run.model,
                "status": "running",
                "started_at": run.started_at,
                "meta_json": run.meta_json,
            },
        )

        con.execute(
            """
            INSERT INTO ai_busy_events(run_id, ts, event_type, phase, message, meta_json)
            VALUES(:run_id, :ts, :event_type, :phase, :message, :meta_json)
            """,
            {
                "run_id": run.run_id,
                "ts": run.started_at,
                "event_type": "busy_start",
                "phase": event_phase,
                "message": event_message,
                "meta_json": json.dumps(event_meta or {}, ensure_ascii=False),
            },
        )

        con.commit()
    finally:
        con.close()


def finish_run(
    *,
    projects_root: Path,
    finish: RunFinish,
    event_phase: str = "api_call",
    event_message: str = "busy_end",
    event_meta: Optional[dict[str, Any]] = None,
) -> None:
    """
    run を確定（ai_runs UPDATE + busy_endイベント）。
    """
    db_path = resolve_ai_runs_db_path(projects_root)
    ensure_db(db_path)

    con = connect(db_path)
    try:
        in_t = finish.usage.input_tokens
        out_t = finish.usage.output_tokens
        tot_t = finish.usage.total_tokens
        if tot_t is None and (in_t is not None or out_t is not None):
            tot_t = (in_t or 0) + (out_t or 0)

        cost_usd = finish.cost.cost_usd
        usd_jpy = finish.cost.usd_jpy
        cost_jpy = finish.cost.cost_jpy
        if cost_jpy is None and (cost_usd is not None and usd_jpy is not None):
            cost_jpy = float(cost_usd) * float(usd_jpy)

        con.execute(
            """
            UPDATE ai_runs
            SET
              status        = :status,
              finished_at   = :finished_at,
              elapsed_ms    = :elapsed_ms,
              input_tokens  = :input_tokens,
              output_tokens = :output_tokens,
              total_tokens  = :total_tokens,
              cost_usd      = :cost_usd,
              usd_jpy       = :usd_jpy,
              cost_jpy      = :cost_jpy,
              error_type    = :error_type,
              error_message = :error_message,
              meta_json     = COALESCE(:meta_json, meta_json)
            WHERE run_id = :run_id
            """,
            {
                "run_id": finish.run_id,
                "status": finish.status,
                "finished_at": finish.finished_at,
                "elapsed_ms": finish.elapsed_ms,
                "input_tokens": in_t,
                "output_tokens": out_t,
                "total_tokens": tot_t,
                "cost_usd": cost_usd,
                "usd_jpy": usd_jpy,
                "cost_jpy": cost_jpy,
                "error_type": finish.error_type,
                "error_message": finish.error_message,
                "meta_json": finish.meta_json,
            },
        )

        con.execute(
            """
            INSERT INTO ai_busy_events(run_id, ts, event_type, phase, message, meta_json)
            VALUES(:run_id, :ts, :event_type, :phase, :message, :meta_json)
            """,
            {
                "run_id": finish.run_id,
                "ts": finish.finished_at,
                "event_type": "busy_end",
                "phase": event_phase,
                "message": event_message,
                "meta_json": json.dumps(event_meta or {}, ensure_ascii=False),
            },
        )

        con.commit()
    finally:
        con.close()


class RunTimer:
    """
    簡易タイマ（elapsed_ms算出用）。
    """
    def __init__(self) -> None:
        self.t0 = time.perf_counter()

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)


def new_run_start(
    *,
    run_id: str,
    parent_run_id: Optional[str],
    user_sub: str,
    app_name: str,
    page_name: str,
    task_type: str,
    provider: str,
    model: str,
    meta: Optional[dict[str, Any]] = None,
) -> RunStart:
    return RunStart(
        run_id=run_id,
        parent_run_id=parent_run_id,
        user_sub=user_sub,
        app_name=app_name,
        page_name=page_name,
        task_type=task_type,
        provider=provider,
        model=model,
        started_at=_now_jst_iso(),
        meta_json=json.dumps(meta or {}, ensure_ascii=False),
    )


def new_finish_success(
    *,
    run_id: str,
    timer: Optional[RunTimer],
    usage: UsageSummary,
    cost: CostSummary,
    meta: Optional[dict[str, Any]] = None,
) -> RunFinish:
    return RunFinish(
        run_id=run_id,
        status="success",
        finished_at=_now_jst_iso(),
        elapsed_ms=(timer.elapsed_ms() if timer else None),
        usage=usage,
        cost=cost,
        meta_json=json.dumps(meta or {}, ensure_ascii=False) if meta else None,
    )


def new_finish_error(
    *,
    run_id: str,
    timer: Optional[RunTimer],
    exc: Exception,
    usage: Optional[UsageSummary] = None,
    cost: Optional[CostSummary] = None,
    meta: Optional[dict[str, Any]] = None,
) -> RunFinish:
    et = exc.__class__.__name__
    em = _truncate(str(exc), 2000)
    tb = _truncate("".join(traceback.format_exc()), 4000)

    meta2 = dict(meta or {})
    meta2.setdefault("traceback", tb)

    return RunFinish(
        run_id=run_id,
        status="error",
        finished_at=_now_jst_iso(),
        elapsed_ms=(timer.elapsed_ms() if timer else None),
        usage=usage or UsageSummary(),
        cost=cost or CostSummary(),
        error_type=et,
        error_message=em,
        meta_json=json.dumps(meta2, ensure_ascii=False),
    )
