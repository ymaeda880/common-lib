# common_lib/ragbot/paths.py
# =============================================================================
# ragbot 用パス管理（共通ライブラリ）
#
# 役割:
# - Storages/<sub>/ragbot_app/ 配下の正本パスを返す
# - ragbot_app ディレクトリを必要に応じて作成する
# - logs ディレクトリを必要に応じて作成する
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from pathlib import Path


# =============================================================================
# 定数
# =============================================================================
RAGBOT_APP_DIRNAME = "ragbot_app"
RAGBOT_LOGS_DIRNAME = "logs"
RAGBOT_LATEST_FILENAME = "latest.json"
RAGBOT_HISTORY_DB_FILENAME = "ragbot_history.db"


# =============================================================================
# helper
# =============================================================================
def _normalize_user_sub(user_sub: str) -> str:
    # -------------------------------------------------------------------------
    # user_sub を安全に文字列化
    # -------------------------------------------------------------------------
    sub = str(user_sub or "").strip()
    if not sub:
        raise ValueError("user_sub が空です。")
    return sub


def _ensure_dir(path: Path) -> Path:
    # -------------------------------------------------------------------------
    # ディレクトリが無ければ作成
    # -------------------------------------------------------------------------
    path.mkdir(parents=True, exist_ok=True)
    return path


# =============================================================================
# public api
# =============================================================================
def get_storages_root(*, projects_root: str | Path) -> Path:
    # -------------------------------------------------------------------------
    # Storages ルートを返す
    # -------------------------------------------------------------------------
    root = Path(projects_root)
    return root / "Storages"


def get_user_storage_root(
    *,
    projects_root: str | Path,
    user_sub: str,
    create: bool = False,
) -> Path:
    # -------------------------------------------------------------------------
    # Storages/<sub>/ を返す
    # -------------------------------------------------------------------------
    storages_root = get_storages_root(projects_root=projects_root)
    sub = _normalize_user_sub(user_sub)
    path = storages_root / sub

    if create:
        _ensure_dir(path)

    return path


def get_ragbot_app_root(
    *,
    projects_root: str | Path,
    user_sub: str,
    create: bool = False,
) -> Path:
    # -------------------------------------------------------------------------
    # Storages/<sub>/ragbot_app/ を返す
    # -------------------------------------------------------------------------
    user_root = get_user_storage_root(
        projects_root=projects_root,
        user_sub=user_sub,
        create=create,
    )
    path = user_root / RAGBOT_APP_DIRNAME

    if create:
        _ensure_dir(path)

    return path


def get_ragbot_logs_dir(
    *,
    projects_root: str | Path,
    user_sub: str,
    create: bool = False,
) -> Path:
    # -------------------------------------------------------------------------
    # Storages/<sub>/ragbot_app/logs/ を返す
    # -------------------------------------------------------------------------
    app_root = get_ragbot_app_root(
        projects_root=projects_root,
        user_sub=user_sub,
        create=create,
    )
    path = app_root / RAGBOT_LOGS_DIRNAME

    if create:
        _ensure_dir(path)

    return path


def get_ragbot_latest_json_path(
    *,
    projects_root: str | Path,
    user_sub: str,
    create_parent: bool = False,
) -> Path:
    # -------------------------------------------------------------------------
    # latest.json のフルパスを返す
    # -------------------------------------------------------------------------
    app_root = get_ragbot_app_root(
        projects_root=projects_root,
        user_sub=user_sub,
        create=create_parent,
    )
    return app_root / RAGBOT_LATEST_FILENAME


def get_ragbot_history_db_path(
    *,
    projects_root: str | Path,
    user_sub: str,
    create_parent: bool = False,
) -> Path:
    # -------------------------------------------------------------------------
    # ragbot_history.db のフルパスを返す
    # -------------------------------------------------------------------------
    logs_dir = get_ragbot_logs_dir(
        projects_root=projects_root,
        user_sub=user_sub,
        create=create_parent,
    )
    return logs_dir / RAGBOT_HISTORY_DB_FILENAME