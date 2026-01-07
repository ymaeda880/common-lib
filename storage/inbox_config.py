# common_lib/storage/inbox_config.py
from __future__ import annotations

from pathlib import Path
import streamlit as st

from common_lib.env.config import (
    get_location_from_command_station_secrets,
    read_toml_required,
)

# ============================================================
# internal Inbox の固定仕様
# ============================================================
_INTERNAL_INBOX_DIRNAME = "InBoxStorages"


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
# inbox mode の取得（正本：command_station secrets.toml）
# ============================================================
def get_inbox_mode_from_command_station_secrets(projects_root: Path) -> str:
    """
    command_station_app/.streamlit/secrets.toml を正本として
    inbox mode を返す。

    必須:
      [inbox]
      mode = "internal" | "external"
    """
    p = _command_station_secrets_path(projects_root)

    if not p.exists():
        st.error(f"command_station の secrets.toml が見つかりません：\n{p}")
        st.stop()

    data = read_toml_required(p)

    inbox_tbl = data.get("inbox")
    if not isinstance(inbox_tbl, dict):
        st.error(f"{p} の [inbox] が不正です（テーブルではありません）")
        st.stop()

    mode = inbox_tbl.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        st.error(f"{p} の [inbox].mode が未設定です")
        st.stop()

    mode = mode.strip()
    if mode not in ("internal", "external"):
        st.error(
            f'{p} の [inbox].mode は "internal" または "external" を指定してください'
        )
        st.stop()

    return mode


# ============================================================
# InBoxStorages ルート解決（メインAPI）
# ============================================================
def resolve_inbox_root(projects_root: Path) -> Path:
    """
    InBoxStorages のルートディレクトリを解決して返す。

    正本:
      - inbox.mode      : command_station secrets.toml
      - env.location    : command_station secrets.toml（external 時）
      - external root   : command_station storage.toml
      - internal root   : projects_root / InBoxStorages（固定）

    問題があれば Streamlit 上で明示エラーを出して停止する。
    """
    mode = get_inbox_mode_from_command_station_secrets(projects_root)

    # ------------------------------------------------------------
    # internal（固定運用）
    # ------------------------------------------------------------
    if mode == "internal":
        inbox_root = projects_root / _INTERNAL_INBOX_DIRNAME

        if not inbox_root.exists() or not inbox_root.is_dir():
            st.error(f"内部 InBoxStorages が存在しません: {inbox_root}")
            st.stop()

        return inbox_root

    # ------------------------------------------------------------
    # external（外部SSD）
    # ------------------------------------------------------------
    loc = get_location_from_command_station_secrets(projects_root)

    storage_toml = _command_station_storage_toml_path(projects_root)
    if not storage_toml.exists():
        st.error(f"command_station の storage.toml が見つかりません：\n{storage_toml}")
        st.stop()

    data = read_toml_required(storage_toml)

    # [inbox.storage.external.<location>].root を読む
    inbox_tbl = data.get("inbox")
    if not isinstance(inbox_tbl, dict):
        st.error(f"{storage_toml} の [inbox] が不正です")
        st.stop()

    storage_tbl = inbox_tbl.get("storage")
    if not isinstance(storage_tbl, dict):
        st.error(f"{storage_toml} の [inbox.storage] が不正です")
        st.stop()

    external_tbl = storage_tbl.get("external")
    if not isinstance(external_tbl, dict):
        st.error(f"{storage_toml} の [inbox.storage.external] が不正です")
        st.stop()

    loc_tbl = external_tbl.get(loc)
    if not isinstance(loc_tbl, dict):
        st.error(f"{storage_toml} に [inbox.storage.external.{loc}] がありません")
        st.stop()

    root = loc_tbl.get("root")
    if not isinstance(root, str) or not root.strip():
        st.error(f"{storage_toml} の inbox.storage.external.{loc}.root が未設定です")
        st.stop()

    inbox_root = Path(root.strip())

    if not inbox_root.exists() or not inbox_root.is_dir():
        st.error(
            "\n".join(
                [
                    "外部SSDの InBoxStorages が見つかりません（未接続の可能性）。",
                    f"- location: {loc}",
                    f"- 期待パス: {inbox_root}",
                    "外部SSDを接続してから再実行してください（管理者対応）。",
                ]
            )
        )
        st.stop()

    return inbox_root
