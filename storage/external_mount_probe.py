# -*- coding: utf-8 -*-
# common_lib/storage/external_mount_probe.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

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
    path: Optional[Path]          # 接続中なら Path / それ以外 None
    reason: Optional[str]         # None ならOK、None以外は理由（UI表示用）
    storage_toml: Path
    location: str


# ============================================================
# 汎用：storage.toml から external root を probe（停止しない）
# 想定キー: [storage.external.<loc>.<role>].root
# ============================================================
def probe_external_roots(
    projects_root: Path,
    *,
    roles: Sequence[str],
    location: str | None = None,
) -> list[MountProbeResult]:
    """
    command_station の storage.toml を参照し、
    external root（/Volumes/...）の接続状態を role ごとに probe する。

    - 正本API（resolve_external_ssd_root等）と違い、st.stop しない
    - UIで「接続中/未接続/設定不備」を表示する用途

    参照:
      storage_toml: command_station_project/command_station_app/.streamlit/storage.toml
      key: storage.external.<loc>.<role>.root
    """
    storage_toml = _command_station_storage_toml_path(projects_root)

    # location は secrets.toml 正本から取る（指定があれば優先）
    try:
        loc = (location or "").strip() or get_location_from_command_station_secrets(projects_root)
    except Exception as e:
        # location が取れない時点で全roleが判定不能
        return [
            MountProbeResult(
                role=r,
                path=None,
                reason=f"location 取得失敗: {e}",
                storage_toml=storage_toml,
                location=location or "",
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
        reason: str | None = None
        p: Path | None = None

        try:
            root = data["storage"]["external"][loc][role]["root"]
        except Exception:
            results.append(
                MountProbeResult(
                    role=role,
                    path=None,
                    reason=f"[storage.external.{loc}.{role}] が storage.toml にありません",
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
                    reason=f"storage.external.{loc}.{role}.root が未設定です",
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

        # OK
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
# 便利関数：roleが backup 系だけの標準probe
# ============================================================
def probe_backup_mounts(
    projects_root: Path,
    *,
    roles: Sequence[str] = ("backup", "backup2"),
    location: str | None = None,
) -> list[MountProbeResult]:
    return probe_external_roots(projects_root, roles=roles, location=location)
