# -*- coding: utf-8 -*-
# common_lib/storage/external_sync_root.py
# ============================================================
# Sync root resolver（正本：storage.toml / sync専用）
#
# 役割:
# - command_station_app/.streamlit/storage.toml を正本として、
#   同期元SSD/HDDの root を解決する
# - backup / backup2 系の既存ロジックには一切触れない
#
# 参照キー:
# - [archive.sync.Home].root
# - [archive.sync.Prec].root
# - [archive.sync.Portable].root
# - [databases.sync.Home].root
# - [databases.sync.Prec].root
# - [databases.sync.Portable].root
#
# 注意:
# - root は物理rootを指す
# - 本モジュールは sync 専用
# - backup / backup2 とは分離する
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from pathlib import Path

# ============================================================
# imports（app）
# ============================================================
from common_lib.env.config import (
    get_location_from_command_station_secrets,
    read_toml_required,
)


# ============================================================
# command_station 側 storage.toml パス
# ============================================================
def _command_station_storage_toml_path(projects_root: Path) -> Path:
    return (
        projects_root
        / "command_station_project"
        / "command_station_app"
        / ".streamlit"
        / "storage.toml"
    )


# ============================================================
# subdir -> storage.toml 用途キー
# ============================================================
def _normalize_sync_purpose_key(subdir: str) -> str:
    key = (subdir or "").strip().lower()

    mapping = {
        "archive": "archive",
        "databases": "databases",
    }

    purpose_key = mapping.get(key)

    if purpose_key is None:
        raise ValueError(
            "\n".join(
                [
                    "sync root で未対応の subdir です。",
                    f"- subdir: {subdir}",
                    "許可: Archive / Databases",
                ]
            )
        )

    return purpose_key


# ============================================================
# sync root 解決
# ============================================================
def resolve_sync_root(
    projects_root: Path,
    *,
    subdir: str,
    location: str | None = None,
) -> Path:
    """
    storage.toml の [{purpose}.sync.{同期元location}].root を物理rootとして読み、
    backup page が作る同期元構造に合わせて実体フォルダーを返す。

    storage.toml:
      [archive.sync.Home]
      root = "/Volumes/SYNC_HOME_HDD4TB"

    実際に返すパス:
      /Volumes/SYNC_HOME_HDD4TB/aisv_Backups/Home/backups/archive
    """

    storage_toml = _command_station_storage_toml_path(projects_root)

    if not storage_toml.exists():
        raise FileNotFoundError(
            f"storage.toml が見つかりません: {storage_toml}"
        )

    sync_source_location = (location or "").strip()

    if not sync_source_location:
        sync_source_location = get_location_from_command_station_secrets(projects_root)

    purpose_key = _normalize_sync_purpose_key(subdir)

    data = read_toml_required(storage_toml)

    try:
        physical_root = data[purpose_key]["sync"][sync_source_location]["root"]
    except Exception as e:
        raise KeyError(
            f"{storage_toml} に [{purpose_key}.sync.{sync_source_location}] がありません"
        ) from e

    if not isinstance(physical_root, str) or not physical_root.strip():
        raise ValueError(
            f"{storage_toml} の {purpose_key}.sync.{sync_source_location}.root が未設定です"
        )

    sync_root = (
        Path(physical_root.strip())
        / "aisv_Backups"
        / sync_source_location
        / "backups"
        / purpose_key
        / "latest"
    )

    return sync_root


# ============================================================
# sync root 存在確認付き解決
# ============================================================
def resolve_existing_sync_root(
    projects_root: Path,
    *,
    subdir: str,
    location: str | None = None,
) -> Path:
    """
    sync root を解決し、存在しない場合は例外にする。
    """

    root = resolve_sync_root(
        projects_root,
        subdir=subdir,
        location=location,
    )

    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"同期元SSD/HDDが見つかりません: {root}")

    return root