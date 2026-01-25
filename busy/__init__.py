# common_lib/busy/__init__.py
# =============================================================================
# busy パブリックAPI（共通ライブラリ / busy）
# - 外部（pages等）から使う関数・型をここでまとめて export
# - 直接 import の乱立を避ける
# - 選択肢A：helpers と context（busy_run）も public API に昇格
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

from .paths import resolve_ai_runs_db_path
from .db import ensure_db, connect
from .types import UsageSummary, CostSummary, RunStart, RunFinish
from .recorder import (
    RunTimer,
    new_run_start,
    new_finish_success,
    new_finish_error,
    start_run,
    finish_run,
)
from .query import (
    list_recent_runs,
    list_running_runs,
    get_run,
    list_events_for_run,
)

# ------------------------------------------------------------
# helpers（読みやすい手続き型API）
# ------------------------------------------------------------
from .helpers import (
    busy_start,
    busy_finish_success,
    busy_finish_error,
)

# ------------------------------------------------------------
# usage / cost 反映（補助API）
# - AI result に含まれる実測値のみを busy_run に反映
# ------------------------------------------------------------
from .apply_usage_cost import apply_usage_cost_if_any


# ------------------------------------------------------------
# context manager（高レベルAPI）
# - with busy_run(...) as br: で開始/終了記録を自動化
# ------------------------------------------------------------
from .context import BusyRun, busy_run

__all__ = [
    # paths / db
    "resolve_ai_runs_db_path",
    "ensure_db",
    "connect",

    # types
    "UsageSummary",
    "CostSummary",
    "RunStart",
    "RunFinish",

    # recorder（低レベル）
    "RunTimer",
    "new_run_start",
    "new_finish_success",
    "new_finish_error",
    "start_run",
    "finish_run",

    # query
    "list_recent_runs",
    "list_running_runs",
    "get_run",
    "list_events_for_run",

    # helpers（中レベル）
    "busy_start",
    "busy_finish_success",
    "busy_finish_error",

    # context manager（高レベル）
    "BusyRun",   # busy_run(...) が返すコンテキスト本体（run_id 等を保持）
    "busy_run",  # with busy_run(...) as br: のファクトリ

    "apply_usage_cost_if_any",
]
