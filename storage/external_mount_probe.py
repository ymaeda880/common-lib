# -*- coding: utf-8 -*-
# common_lib/storage/external_mount_probe.py
# ============================================================
# Backup mount probe（正本：storage.toml / 新設定のみ）
#
# 目的：
# - backup / backup2 の「接続状況」を UI 側で表示するために、
#   外部SSDのマウントパスを role ごとに probe する（停止しない）
#
# 方針：
# - Streamlit（st）依存を入れない（st.stop しない）
# - 返すのは Path or None と reason（文字列）だけ
# - 旧設定（storage.external.*）は「物理削除扱い」なので参照しない
#
# 参照キー（新設定・正本）：
# - [storage.backup.<loc>].root
# - [storage.backup2.<loc>].root
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from common_lib.env.config import (
    get_location_from_command_station_secrets,
    read_toml_required,
)


# ============================================================
# command_station 側ファイルパス（設計上確定）
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
# Probe Result（停止しない）
# ============================================================
@dataclass(frozen=True)
class MountProbeResult:
    role: str
    path: Optional[Path]      # 接続中なら Path / それ以外 None
    reason: Optional[str]     # None ならOK、None以外は理由（UI表示用）
    storage_toml: Path
    location: str


# ============================================================
# 汎用：storage.toml から backup root を probe（停止しない）
# 想定キー（新設定）: [storage.<role>.<loc>].root
#   - role: backup / backup2
# ============================================================
def probe_backup_roots_v2(
    projects_root: Path,
    *,
    roles: Sequence[str],
    purpose_key: str,
    location: str | None = None,
) -> list[MountProbeResult]:
    """
    command_station の storage.toml を参照し、
    backup root（/Volumes/...）の接続状態を role ごとに probe する（停止しない）。

    参照（用途別・新設定）:
      key: {purpose_key}.{role}.{loc}.root
        例: storage.backup.Home.root / inbox.backup2.Prec.root
    """
    storage_toml = _command_station_storage_toml_path(projects_root)

    # location は secrets.toml 正本から取る（指定があれば優先）
    try:
        loc = (location or "").strip() or get_location_from_command_station_secrets(projects_root)
    except Exception as e:
        loc_fallback = (location or "").strip()
        return [
            MountProbeResult(
                role=r,
                path=None,
                reason=f"location 取得失敗: {e}",
                storage_toml=storage_toml,
                location=loc_fallback,
            )
            for r in roles
        ]

    if not storage_toml.exists():
        return [
            MountProbeResult(
                role=r,
                path=None,
                reason=f"storage.toml が見つかりません: {storage_toml}",
                storage_toml=storage_toml,
                location=loc,
            )
            for r in roles
        ]

    # storage.toml 読み込み
    try:
        data = read_toml_required(storage_toml)
    except Exception as e:
        return [
            MountProbeResult(
                role=r,
                path=None,
                reason=f"storage.toml 読み込み失敗: {e}",
                storage_toml=storage_toml,
                location=loc,
            )
            for r in roles
        ]

    results: list[MountProbeResult] = []

    for role in roles:
        try:
            root = data[purpose_key][role][loc]["root"]
        except Exception:
            results.append(
                MountProbeResult(
                    role=role,
                    path=None,
                    reason=f"[{purpose_key}.{role}.{loc}] が storage.toml にありません（新設定・用途別）",
                    storage_toml=storage_toml,
                    location=loc,
                )
            )
            continue

        if not isinstance(root, str) or not root.strip():
            results.append(
                MountProbeResult(
                    role=role,
                    path=None,
                    reason=f"{purpose_key}.{role}.{loc}.root が未設定です（新設定・用途別）",
                    storage_toml=storage_toml,
                    location=loc,
                )
            )
            continue

        cand = Path(root.strip())
        if not cand.exists() or not cand.is_dir():
            results.append(
                MountProbeResult(
                    role=role,
                    path=None,
                    reason=f"未接続の可能性: {cand}",
                    storage_toml=storage_toml,
                    location=loc,
                )
            )
            continue

        results.append(
            MountProbeResult(
                role=role,
                path=cand,
                reason=None,
                storage_toml=storage_toml,
                location=loc,
            )
        )

    return results

# ============================================================
# 追加
# ============================================================
def probe_backup_mounts_by_purpose(
    projects_root: Path,
    *,
    purpose_key: str,
    roles: Sequence[str] = ("backup", "backup2"),
    location: str | None = None,
) -> list[MountProbeResult]:
    """
    用途別の標準probe（新設定・用途別）。

    purpose_key:
      - storage / inbox / archive / databases
    """
    return probe_backup_roots_v2(
        projects_root,
        roles=roles,
        purpose_key=purpose_key,
        location=location,
    )

# ============================================================
# 便利関数：backup/backup2 の標準probe（新設定 v2）
# ============================================================
def probe_backup_mounts(
    projects_root: Path,
    *,
    roles: Sequence[str] = ("backup", "backup2"),
    location: str | None = None,
) -> list[MountProbeResult]:
    """
    互換名（従来ページ用）：
    Storages 用（purpose_key="storage"）として新設定の probe を呼ぶ。
    """
    return probe_backup_roots_v2(projects_root, roles=roles, purpose_key="storage", location=location)