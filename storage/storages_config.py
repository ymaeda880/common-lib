# common_lib/storage/storages_config.py
from __future__ import annotations

from pathlib import Path
import streamlit as st

from common_lib.env.config import (
    get_location_from_command_station_secrets,
    read_toml_required,
)

# ============================================================
# internal Storages の固定仕様
# ============================================================
_INTERNAL_STORAGES_DIRNAME = "Storages"


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
# storages mode の取得（正本：command_station secrets.toml）
# ============================================================
def get_storages_mode_from_command_station_secrets(projects_root: Path) -> str:
    """
    command_station_app/.streamlit/secrets.toml を正本として
    storages mode を返す。

    必須:
      [storages]
      mode = "internal" | "external"
    """
    p = _command_station_secrets_path(projects_root)

    if not p.exists():
        st.error(f"command_station の secrets.toml が見つかりません：\n{p}")
        st.stop()

    data = read_toml_required(p)

    tbl = data.get("storages")
    if not isinstance(tbl, dict):
        st.error(f"{p} の [storages] が不正です（テーブルではありません）")
        st.stop()

    mode = tbl.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        st.error(f"{p} の [storages].mode が未設定です")
        st.stop()

    mode = mode.strip()
    if mode not in ("internal", "external"):
        st.error(
            f'{p} の [storages].mode は "internal" または "external" を指定してください'
        )
        st.stop()

    return mode


# ============================================================
# Storages ルート解決（メインAPI）
# ============================================================
def resolve_storages_root(projects_root: Path) -> Path:
    """
    Storages のルートディレクトリを解決して返す。

    正本:
      - storages.mode   : command_station secrets.toml
      - env.location    : command_station secrets.toml（external 時）
      - external root   : command_station storage.toml
      - internal root   : projects_root / Storages（固定）

    問題があれば Streamlit 上で明示エラーを出して停止する。
    """
    mode = get_storages_mode_from_command_station_secrets(projects_root)

    # ------------------------------------------------------------
    # internal（固定運用）
    # ------------------------------------------------------------
    if mode == "internal":
        storages_root = projects_root / _INTERNAL_STORAGES_DIRNAME

        if not storages_root.exists() or not storages_root.is_dir():
            st.error(f"内部 Storages が存在しません: {storages_root}")
            st.stop()

        return storages_root

    # ------------------------------------------------------------
    # external（外部SSD）
    # ------------------------------------------------------------
    loc = get_location_from_command_station_secrets(projects_root)

    storage_toml = _command_station_storage_toml_path(projects_root)
    if not storage_toml.exists():
        st.error(f"command_station の storage.toml が見つかりません：\n{storage_toml}")
        st.stop()

    data = read_toml_required(storage_toml)

    # [storages.storage.external.<location>].root を読む
    tbl = data.get("storages")
    if not isinstance(tbl, dict):
        st.error(f"{storage_toml} の [storages] が不正です")
        st.stop()

    storage_tbl = tbl.get("storage")
    if not isinstance(storage_tbl, dict):
        st.error(f"{storage_toml} の [storages.storage] が不正です")
        st.stop()

    external_tbl = storage_tbl.get("external")
    if not isinstance(external_tbl, dict):
        st.error(f"{storage_toml} の [storages.storage.external] が不正です")
        st.stop()

    loc_tbl = external_tbl.get(loc)
    if not isinstance(loc_tbl, dict):
        st.error(f"{storage_toml} に [storages.storage.external.{loc}] がありません")
        st.stop()

    root = loc_tbl.get("root")
    if not isinstance(root, str) or not root.strip():
        st.error(f"{storage_toml} の storages.storage.external.{loc}.root が未設定です")
        st.stop()

    storages_root = Path(root.strip())

    if not storages_root.exists() or not storages_root.is_dir():
        st.error(
            "\n".join(
                [
                    "外部SSDの Storages が見つかりません（未接続の可能性）。",
                    f"- location: {loc}",
                    f"- 期待パス: {storages_root}",
                    "外部SSDを接続してから再実行してください（管理者対応）。",
                ]
            )
        )
        st.stop()

    return storages_root
