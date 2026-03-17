# common_lib/storage/external_ssd_root.py
# ============================================================
# Storage path resolver（正本：storage.toml）
#
# ■ 目的
# - command_station_app/.streamlit/storage.toml を単一の真実として、
#   InBoxStorages / Storages / Archive / Databases の保存先を解決する。
#
# ■ 設計方針（現行）
# - main は secrets.toml の mode（internal/external）に従う
# - external(main) は storage.toml の用途別 root を必ず読む
#   - [inbox.storage.external.{loc}].root
#   - [storages.storage.external.{loc}].root
#   - [archive.storage.external.{loc}].root
#   - [databases.storage.external.{loc}].root
# - backup/backup2 は「常に external」強制
#   - 新設定（v2）：[storage.backup.{loc}].root / [storage.backup2.{loc}].root を物理rootとして読む
#   - 物理root配下に用途フォルダ名（mainのroot末尾名）をぶら下げて解決する
# - main は未接続/未作成なら停止、backup系は Path を返して止めない
#
# ■ 互換（重要）
# - 既存の多数コードが resolve_storage_subdir_root(...) を呼んでいるため、
#   resolve_storage_subdir_root はラッパーとして残し、backup系のみ v2 に切替える。
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from pathlib import Path
from typing import Literal

# ============================================================
# imports（third party）
# ============================================================
import streamlit as st

# ============================================================
# imports（app）
# ============================================================
from common_lib.env.config import (
    get_location_from_command_station_secrets,
    read_toml_required,
)

# ============================================================
# types
# ============================================================
Role = Literal["main", "backup", "backup2"]

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
# backup 判定ヘルパー
# ============================================================
def _is_backup_role(role: Role) -> bool:
    return role != "main"


# ============================================================
# subdir -> storage.toml の用途キーへ正規化
# ============================================================
def _normalize_subdir_key(subdir: str) -> str:
    """
    subdir（論理名）を storage.toml の用途キーへ正規化する。

    許可:
      - InBoxStorages -> inbox
      - Storages      -> storages
      - Archive       -> archive
      - Databases     -> databases
    """
    k = (subdir or "").strip().lower()
    mapping = {
        "inboxstorages": "inbox",
        "storages": "storages",
        "archive": "archive",
        "databases": "databases",
    }
    key = mapping.get(k)
    if key is None:
        st.error(
            "\n".join(
                [
                    "未知の subdir です。",
                    f"- subdir: {subdir}",
                    "許可: InBoxStorages / Storages / Archive / Databases",
                ]
            )
        )
        st.stop()
    return key


# ============================================================
# main mode の取得（subdir 別：inbox / storages / archive / databases）
# ============================================================
def _main_mode_from_secrets(projects_root: Path, *, subdir: str) -> str:
    """
    main の internal/external を secrets.toml から subdir 別に取得する。

    正本:
      - [storages].mode
      - [inbox].mode
      - [archive].mode
      - [databases].mode
    """
    p = _command_station_secrets_path(projects_root)
    if not p.exists():
        st.error(f"command_station の secrets.toml が見つかりません：\n{p}")
        st.stop()

    data = read_toml_required(p)

    key = _normalize_subdir_key(subdir)

    tbl = data.get(key)
    if not isinstance(tbl, dict):
        st.error(f"{p} の [{key}] が不正です（テーブルではありません）")
        st.stop()

    mode = tbl.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        st.error(f"{p} の [{key}].mode が未設定です")
        st.stop()

    mode = mode.strip()
    if mode not in ("internal", "external"):
        st.error(f'{p} の [{key}].mode は "internal" または "external" を指定してください')
        st.stop()

    return mode


# ============================================================
# storage.toml から external の用途別 root を読む（main用）
# ============================================================
def _read_external_logical_root_from_storage_toml(
    projects_root: Path,
    *,
    loc: str,
    key: str,
) -> Path:
    """
    storage.toml の [{key}.storage.external.{loc}].root を読んで Path を返す。
    """
    storage_toml = _command_station_storage_toml_path(projects_root)
    if not storage_toml.exists():
        st.error(f"command_station の storage.toml が見つかりません：\n{storage_toml}")
        st.stop()

    data = read_toml_required(storage_toml)

    try:
        root = data[key]["storage"]["external"][loc]["root"]
    except Exception:
        st.error(f"{storage_toml} に [{key}.storage.external.{loc}] がありません")
        st.stop()

    if not isinstance(root, str) or not root.strip():
        st.error(f"{storage_toml} の {key}.storage.external.{loc}.root が未設定です")
        st.stop()

    return Path(root.strip())


# ============================================================
# external SSD root 解決（物理 root：/Volumes/...）
# ============================================================
def resolve_external_ssd_root(
    projects_root: Path,
    *,
    role: Role = "main",
) -> Path:
    """
    外部SSDの「物理 root（/Volumes/...）」のみを解決して返す。

    ※ 旧設定互換（[storage.external.{loc}.{role}].root）を読む。
    ※ 新設定(v2)ではバックアップ物理rootは別関数で読む。
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
# internal / external を切り替えて subdir を返す（legacy：旧実装）
# ============================================================
def resolve_storage_subdir_root_legacy(
    projects_root: Path,
    *,
    subdir: str,
    role: Role = "main",
) -> Path:
    """
    旧実装（互換保持用）。
    - backup/backup2 は旧物理root（resolve_external_ssd_root）を使用する。
    - main は secrets.toml の mode に従う。
    """
    loc = get_location_from_command_station_secrets(projects_root)
    key = _normalize_subdir_key(subdir)

    # --------------------------------------------------------
    # backup系は「常に external」を強制（旧：storage.external.* を使用）
    # --------------------------------------------------------
    if _is_backup_role(role):
        ssd_root = resolve_external_ssd_root(projects_root, role=role)

        main_logical_root = _read_external_logical_root_from_storage_toml(
            projects_root,
            loc=loc,
            key=key,
        )
        folder_name = main_logical_root.name  # 例：InBoxStorages / Storages / Archive / Databases

        p = ssd_root / folder_name

        # backup 系は「未接続／未作成でも止めない」
        if not p.exists() or not p.is_dir():
            return p

        return p

    # --------------------------------------------------------
    # main は subdir 別の mode に従う
    # --------------------------------------------------------
    mode = _main_mode_from_secrets(projects_root, subdir=subdir)

    # internal は projects_root 配下（subdir名は呼び出し側の指定をそのまま使う）
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

    # external（main）：storage.toml の用途別 root を必ず使う
    p = _read_external_logical_root_from_storage_toml(
        projects_root,
        loc=loc,
        key=key,
    )

    if not p.exists() or not p.is_dir():
        st.error(
            "\n".join(
                [
                    f"外部SSD上の {subdir} が見つかりません。",
                    "- role     : main",
                    f"- 期待パス : {p}",
                    "外部SSDの構成（フォルダ）を確認してください（管理者対応）。",
                ]
            )
        )
        st.stop()

    return p


# ============================================================
# storage.toml から backup/backup2 の物理 root を読む（新設定 v2）
# ============================================================
def _read_backup_physical_root_from_storage_toml_v2(
    projects_root: Path,
    *,
    loc: str,
    role: Role,
    purpose_key: str,
) -> Path:
    """
    storage.toml の [{purpose_key}.{role}.{loc}].root を読んで Path を返す（用途別・新設定）。

    purpose_key 例：
      - storage    （Storages 用。※storages ではなく storage）
      - inbox
      - archive
      - databases

    role 例：
      - backup
      - backup2
    """
    if role == "main":
        raise RuntimeError("internal error: backup root reader called with role=main")

    storage_toml = _command_station_storage_toml_path(projects_root)
    if not storage_toml.exists():
        st.error(f"command_station の storage.toml が見つかりません：\n{storage_toml}")
        st.stop()

    data = read_toml_required(storage_toml)

    try:
        root = data[purpose_key][role][loc]["root"]
    except Exception:
        st.error(f"{storage_toml} に [{purpose_key}.{role}.{loc}] がありません（新設定・用途別）")
        st.stop()

    if not isinstance(root, str) or not root.strip():
        st.error(f"{storage_toml} の {purpose_key}.{role}.{loc}.root が未設定です（新設定・用途別）")
        st.stop()

    return Path(root.strip())


# ============================================================
# internal / external を切り替えて subdir を返す（新API：v2）
# ============================================================
def resolve_storage_subdir_root_v2(
    projects_root: Path,
    *,
    subdir: str,
    role: Role = "main",
) -> Path:
    """
    role に従って subdir のルートを返す（v2：新バックアップ設定を使用）。

    - main:
        legacy（旧main挙動）を利用（internal/external切替含む）
    - backup/backup2:
        storage.toml の新設定（[storage.{role}.{loc}].root）を必ず読む。
        フォルダ作成はしない。存在チェックで止めない（Path を返すだけ）。
    """
    loc = get_location_from_command_station_secrets(projects_root)
    key = _normalize_subdir_key(subdir)
    # --------------------------------------------------------
    # backup root の用途キー（storage.toml のテーブル名）
    # - storages -> storage（toml の都合）
    # - inbox/archive/databases はそのまま
    # --------------------------------------------------------
    purpose_key = "storage" if key == "storages" else key

    # --------------------------------------------------------
    # main は legacy を利用（循環防止：resolve_storage_subdir_root を呼ばない）
    # --------------------------------------------------------
    if role == "main":
        return resolve_storage_subdir_root_legacy(projects_root, subdir=subdir, role="main")

    # --------------------------------------------------------
    # backup/backup2（新設定 v2）
    # - 物理root：[storage.{role}.{loc}].root
    # - 用途フォルダ名：main(root)の末尾名から取得（決め打ち禁止）
    # --------------------------------------------------------
    physical_root = _read_backup_physical_root_from_storage_toml_v2(
        projects_root,
        loc=loc,
        role=role,
        purpose_key=purpose_key,
    )

    main_logical_root = _read_external_logical_root_from_storage_toml(
        projects_root,
        loc=loc,
        key=key,
    )
    folder_name = main_logical_root.name  # 例：InBoxStorages / Storages / Archive / Databases

    return physical_root / folder_name


# ============================================================
# internal / external を切り替えて subdir を返す（最終API：互換ラッパー）
# ============================================================
def resolve_storage_subdir_root(
    projects_root: Path,
    *,
    subdir: str,
    role: Role = "main",
) -> Path:
    """
    互換API（ラッパー）。

    目的：
    - 既存多数コードが resolve_storage_subdir_root(...) を呼んでいる前提で、
      呼び出し側を直さずに新設定へ移行する。

    ルール（固定）：
      - main   : legacy（旧挙動）を使用（internal/external切替含む）
      - backup : v2（新バックアップ設定）を使用
      - backup2: v2（新バックアップ設定）を使用
    """
    if role == "main":
        return resolve_storage_subdir_root_legacy(projects_root, subdir=subdir, role="main")

    return resolve_storage_subdir_root_v2(projects_root, subdir=subdir, role=role)