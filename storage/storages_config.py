# common_lib/storage/storages_config.py
from __future__ import annotations

from pathlib import Path

try:
    import streamlit as st  # type: ignore
except ModuleNotFoundError:
    st = None  # CLI / worker 等 streamlit 無し環境向け

from common_lib.env.config import (
    get_location_from_command_station_secrets,
    read_toml_required,
)

# ============================================================
# Streamlit あり/なし両対応：エラー表示＋停止
# ============================================================
def _error_stop_or_raise(msg: str) -> None:
    """
    Streamlit 実行時は st.error + st.stop。
    streamlit が無い環境では RuntimeError で停止。
    """
    if st is not None:
        st.error(msg)
        st.stop()
        return
    raise RuntimeError(msg)


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
        _error_stop_or_raise(f"command_station の secrets.toml が見つかりません：\n{p}")

    data = read_toml_required(p)

    tbl = data.get("storages")
    if not isinstance(tbl, dict):
        _error_stop_or_raise(f"{p} の [storages] が不正です（テーブルではありません）")

    mode = tbl.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        _error_stop_or_raise(f"{p} の [storages].mode が未設定です")

    mode = mode.strip()
    if mode not in ("internal", "external"):
        _error_stop_or_raise(
            f'{p} の [storages].mode は "internal" または "external" を指定してください'
        )

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
            _error_stop_or_raise(f"内部 Storages が存在しません: {storages_root}")

        return storages_root

    # ------------------------------------------------------------
    # external（外部SSD）
    # ------------------------------------------------------------
    loc = get_location_from_command_station_secrets(projects_root)

    storage_toml = _command_station_storage_toml_path(projects_root)
    if not storage_toml.exists():
        _error_stop_or_raise(
            f"command_station の storage.toml が見つかりません：\n{storage_toml}"
        )

    data = read_toml_required(storage_toml)

    # [storages.storage.external.<location>].root を読む
    tbl = data.get("storages")
    if not isinstance(tbl, dict):
        _error_stop_or_raise(f"{storage_toml} の [storages] が不正です")

    storage_tbl = tbl.get("storage")
    if not isinstance(storage_tbl, dict):
        _error_stop_or_raise(f"{storage_toml} の [storages.storage] が不正です")

    external_tbl = storage_tbl.get("external")
    if not isinstance(external_tbl, dict):
        _error_stop_or_raise(f"{storage_toml} の [storages.storage.external] が不正です")

    loc_tbl = external_tbl.get(loc)
    if not isinstance(loc_tbl, dict):
        _error_stop_or_raise(f"{storage_toml} に [storages.storage.external.{loc}] がありません")

    root = loc_tbl.get("root")
    if not isinstance(root, str) or not root.strip():
        _error_stop_or_raise(
            f"{storage_toml} の storages.storage.external.{loc}.root が未設定です"
        )

    storages_root = Path(root.strip())

    if not storages_root.exists() or not storages_root.is_dir():
        _error_stop_or_raise(
            "\n".join(
                [
                    "外部SSDの Storages が見つかりません（未接続の可能性）。",
                    f"- location: {loc}",
                    f"- 期待パス: {storages_root}",
                    "外部SSDを接続してから再実行してください（管理者対応）。",
                ]
            )
        )

    return storages_root
