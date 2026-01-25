# common_lib/storage/external_ssd_root.py
from __future__ import annotations

from pathlib import Path
from typing import Literal

import streamlit as st

from common_lib.env.config import (
    get_location_from_command_station_secrets,
    read_toml_required,
)

Role = Literal["main", "backup", "backup2"]


def _normalize_subdir_name(subdir: str) -> str:
    """
    論理名（Storages / InBoxStorages / Archive）
    → 実体フォルダ名（過去互換：小文字）
    """
    key = subdir.strip().lower()
    mapping = {
        "storages": "storages",
        "inboxstorages": "inbox",
        "archive": "archive",
    }
    if key not in mapping:
        st.error(f"未知の subdir です：{subdir}")
        st.stop()
    return mapping[key]


# ============================================================
# backup 判定ヘルパー
# ============================================================
def _is_backup_role(role: Role) -> bool:
    return role != "main"


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
# main mode の取得（subdir 別：storages / inbox / archive）
# ============================================================
def _main_mode_from_secrets(projects_root: Path, *, subdir: str) -> str:
    """
    main の internal/external を secrets.toml から subdir 別に取得する。

    正本:
      - Storages      -> [storages].mode
      - InBoxStorages -> [inbox].mode
      - Archive       -> [archive].mode
    """
    p = _command_station_secrets_path(projects_root)
    if not p.exists():
        st.error(f"command_station の secrets.toml が見つかりません：\n{p}")
        st.stop()

    data = read_toml_required(p)

    key_map = {
        "storages": "storages",
        "inboxstorages": "inbox",
        "archive": "archive",
    }

    k = key_map.get(str(subdir).strip().lower())
    if k is None:
        st.error(
            "\n".join(
                [
                    "未知の subdir です（main mode を決められません）。",
                    f"- subdir: {subdir}",
                    "許可: Storages / InBoxStorages / Archive",
                ]
            )
        )
        st.stop()

    tbl = data.get(k)
    if not isinstance(tbl, dict):
        st.error(f"{p} の [{k}] が不正です（テーブルではありません）")
        st.stop()

    mode = tbl.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        st.error(f"{p} の [{k}].mode が未設定です")
        st.stop()

    mode = mode.strip()
    if mode not in ("internal", "external"):
        st.error(f'{p} の [{k}].mode は "internal" または "external" を指定してください')
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
        root = data["storage"]["external"][loc][role]["root"]
    except Exception:
        st.error(f"{storage_toml} に [storage.external.{loc}.{role}] がありません")
        st.stop()

    if not isinstance(root, str) or not root.strip():
        st.error(f"{storage_toml} の storage.external.{loc}.{role}.root が未設定です")
        st.stop()

    ssd_root = Path(root.strip())

    if not ssd_root.exists() or not ssd_root.is_dir():
        # 未接続：backup 系では「存在しない Path」を返すだけ（UI 側で表示）
        if role != "main":
            return ssd_root
        # main は従来どおりエラー停止
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
    role に従って subdir のルートを返す。
    """

    real_subdir = _normalize_subdir_name(subdir)

    # --------------------------------------------------------
    # backup系は「常に external」を強制
    # --------------------------------------------------------
    if _is_backup_role(role):
        ssd_root = resolve_external_ssd_root(projects_root, role=role)
        p = ssd_root / real_subdir

        # backup 系は「未接続／未作成でも止めない」
        if not p.exists() or not p.is_dir():
            # Path は返す（UI 側で「未接続」「未作成」と表示させる）
            return p

        return p


    # --------------------------------------------------------
    # main は subdir 別の mode に従う
    # --------------------------------------------------------
    mode = _main_mode_from_secrets(projects_root, subdir=subdir)

    # internal は論理名（subdir）をそのまま使う
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

    # external（main）
    ssd_root = resolve_external_ssd_root(projects_root, role="main")
    p = ssd_root / real_subdir

    if not p.exists() or not p.is_dir():
        st.error(
            "\n".join(
                [
                    f"外部SSD上の {real_subdir} が見つかりません。",
                    "- role     : main",
                    f"- 期待パス : {p}",
                    "外部SSDの構成（フォルダ）を確認してください（管理者対応）。",
                ]
            )
        )
        st.stop()

    return p
