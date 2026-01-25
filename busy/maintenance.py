# common_lib/busy/maintenance.py
# =============================================================================
# ai_runs.db メンテナンス（共通ライブラリ / busy）
# - VACUUM（肥大化対策）
# - （必要なら）index再構築等を追加
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from .db import connect, ensure_db
from .paths import resolve_ai_runs_db_path


def vacuum(*, projects_root: Path) -> None:
    db_path = resolve_ai_runs_db_path(projects_root)
    ensure_db(db_path)
    con = connect(db_path)
    try:
        con.execute("VACUUM;")
        con.commit()
    finally:
        con.close()
