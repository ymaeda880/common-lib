from __future__ import annotations

from pathlib import Path
from typing import Literal

import streamlit as st

from common_lib.env.config import (
    get_location_from_command_station_secrets,
    read_toml_required,
)

Role = Literal["main", "backup"]


# ============================================================
# command_station 側ファイルパス（設計上確定）
# ============================================================
def _command_station_secrets_path(projects_root: Path) -> Path:
    return (
        projects_root
        / "command_station_project"
        / "command_station_app"
        / ".streamlit"
        / "secrets.toml"
    )


def _command_station_storage_toml_path(projects_root: Path) -> Path:
    return (
        projects_root
        / "command_station_project"
        / "command_station_app"
        / ".streamlit"
        / "storage.toml"
    )


# ============================================================
# storage_policy.mode の取得（internal / external のみ）
# ============================================================
def _get_storage_policy_mode(projects_root: Path) -> str:
    p = _command_station_secrets_path(projects_root)
    if not p.exists():
        st.error(f"command_station の secrets.toml が見つかりません：\n{p}")
        st.stop()

    data = read_toml_required(p)

    tbl = data.get("storage_policy")
    if not isinstance(tbl, dict):
        st.error(f"{p} の [storage_policy] が不正です")
        st.stop()

    mode = tbl.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        st.error(f"{p} の [storage_policy].mode が未設定です")
        st.stop()

    mode = mode.strip()
    if mode not in ("internal", "external"):
        st.error(
            f'{p} の [storage_policy].mode は "internal" または "external" を指定してください'
        )
        st.stop()

    return mode


# ============================================================
# external SSD root 解決（external 専用）
# ============================================================
def resolve_external_ssd_root(
    projects_root: Path,
    *,
    role: Role = "main",
) -> Path:
    """
    外部SSDの「物理 root（/Volumes/...）」のみを解決して返す。
    """
    loc = get_location_from_command_station_secrets(projects_root)

    storage_toml = _command_station_storage_toml_path(projects_root)
    if not storage_toml.exists():
        st.error(f"command_station の storage.toml が見つかりません：\n{storage_toml}")
        st.stop()

    data = read_toml_required(storage_toml)

    try:
        root = (
            data["storage"]["external"][loc][role]["root"]
        )
    except Exception:
        st.error(f"{storage_toml} に [storage.external.{loc}.{role}] がありません")
        st.stop()

    if not isinstance(root, str) or not root.strip():
        st.error(
            f"{storage_toml} の storage.external.{loc}.{role}.root が未設定です"
        )
        st.stop()

    ssd_root = Path(root.strip())

    if not ssd_root.exists() or not ssd_root.is_dir():
        st.error(
            "\n".join(
                [
                    "外部SSDが見つかりません（未接続の可能性）。",
                    f"- location : {loc}",
                    f"- role     : {role}",
                    f"- 期待パス : {ssd_root}",
                    "外部SSDを接続してから再実行してください（管理者対応）。",
                ]
            )
        )
        st.stop()

    return ssd_root


# ============================================================
# internal / external を切り替えて subdir を返す（最終API）
# ============================================================
def resolve_storage_subdir_root(
    projects_root: Path,
    *,
    subdir: str,
    role: Role = "main",
) -> Path:
    """
    storage_policy.mode に従って subdir のルートを返す。

    - internal : projects_root / subdir
    - external : 外部SSD / subdir
    """
    mode = _get_storage_policy_mode(projects_root)

    # --------------------------------------------------------
    # internal（内蔵ディスク）
    # --------------------------------------------------------
    if mode == "internal":
        p = projects_root / subdir
        if not p.exists() or not p.is_dir():
            st.error(
                "\n".join(
                    [
                        f"internal {subdir} が見つかりません。",
                        f"- 期待パス : {p}",
                        "projects_root 配下の構成を確認してください（管理者対応）。",
                    ]
                )
            )
            st.stop()
        return p

    # --------------------------------------------------------
    # external（外部SSD）
    # --------------------------------------------------------
    ssd_root = resolve_external_ssd_root(projects_root, role=role)
    p = ssd_root / subdir

    if not p.exists() or not p.is_dir():
        st.error(
            "\n".join(
                [
                    f"外部SSD上の {subdir} が見つかりません。",
                    f"- role     : {role}",
                    f"- 期待パス : {p}",
                    "外部SSDの構成（フォルダ）を確認してください（管理者対応）。",
                ]
            )
        )
        st.stop()

    return p
