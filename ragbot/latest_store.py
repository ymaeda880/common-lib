# common_lib/ragbot/latest_store.py
# =============================================================================
# ragbot 最新参照結果保存（common_lib）
#
# 役割:
# - latest.json を上書き保存する
# - 必要ディレクトリを自動作成する
# - 一時ファイル経由で安全に置換する
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# =============================================================================
# local imports
# =============================================================================
from common_lib.ragbot.paths import get_ragbot_latest_json_path


# =============================================================================
# helper
# =============================================================================
def _now_iso_utc() -> str:
    # -------------------------------------------------------------------------
    # UTC ISO文字列
    # -------------------------------------------------------------------------
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(*, path: Path, payload: dict[str, Any]) -> Path:
    # -------------------------------------------------------------------------
    # JSON を一時ファイル経由で安全に保存
    # -------------------------------------------------------------------------
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_name(f"{path.name}.tmp")

    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    )

    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)

    return path


# =============================================================================
# payload builder
# =============================================================================
def build_latest_payload(
    *,
    user_sub: str,
    question: str,
    answer: str,
    model_key: str,
    use_stream: bool,
    top_k: int,
    selected_years: list[int],
    used_references: list[dict[str, Any]],
    referenced_projects: list[dict[str, Any]],
) -> dict[str, Any]:
    # -------------------------------------------------------------------------
    # latest.json 用 payload を構築
    # -------------------------------------------------------------------------
    return {
        "updated_at": _now_iso_utc(),
        "user_sub": str(user_sub or "").strip(),
        "query": {
            "question": str(question or "").strip(),
            "model_key": str(model_key or "").strip(),
            "use_stream": bool(use_stream),
            "top_k": int(top_k),
            "selected_years": [int(y) for y in list(selected_years or [])],
        },
        "result": {
            "answer": str(answer or "").strip(),
        },
        "used_references": list(used_references or []),
        "referenced_projects": list(referenced_projects or []),
    }


# =============================================================================
# public api
# =============================================================================
def save_latest_result(
    *,
    projects_root: str | Path,
    user_sub: str,
    payload: dict[str, Any],
) -> Path:
    # -------------------------------------------------------------------------
    # latest.json を上書き保存
    # -------------------------------------------------------------------------
    path = get_ragbot_latest_json_path(
        projects_root=projects_root,
        user_sub=user_sub,
        create_parent=True,
    )
    return _write_json_atomic(path=path, payload=payload)