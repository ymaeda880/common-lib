# common_lib/busy/paths.py
# =============================================================================
# ai_runs.db パス解決ユーティリティ（共通ライブラリ / busy）
# - Storages/_admin/ai_runs/ai_runs.db の正本パスを解決
# - sessions系と同じ思想で、resolve_storage_subdir_root を起点にする
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from common_lib.storage.external_ssd_root import resolve_storage_subdir_root


def resolve_ai_runs_db_path(projects_root: Path) -> Path:
    """
    ai_runs.db 正本パス（sessions系と同じ思想）：
      Storages/_admin/ai_runs/ai_runs.db
    """
    storage_root = resolve_storage_subdir_root(
        projects_root,
        subdir="Storages",
        role="main",
    )
    return storage_root / "_admin" / "ai_runs" / "ai_runs.db"
