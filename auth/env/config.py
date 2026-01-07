# common_lib/env/config.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


def _read_toml_required(path: Path) -> Dict[str, Any]:
    if tomllib is None:
        st.error("tomllib が利用できません（Python 3.11+ が必要です）")
        st.stop()

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        st.error(f"TOML の読み込みに失敗しました：\n{path}\n\n{e}")
        st.stop()

    if not isinstance(data, dict):
        st.error(f"TOML の形式が不正です（dict ではありません）：\n{path}")
        st.stop()

    return data


def get_location_from_command_station_secrets(projects_root: Path) -> str:
    """
    command_station の secrets.toml を正本として location を返す。
    - パスは設計上確定
    - 見つからない / 未設定なら Streamlit でエラー表示して停止
    - 暗黙デフォルトは使わない
    """
    secrets_path = (
        projects_root
        / "command_station_project"
        / "command_station_app"
        / ".streamlit"
        / "secrets.toml"
    )

    if not secrets_path.exists():
        st.error(f"command_station の secrets.toml が見つかりません：\n{secrets_path}")
        st.stop()

    data = _read_toml_required(secrets_path)
    env_tbl = data.get("env") or {}
    if not isinstance(env_tbl, dict):
        st.error(f"{secrets_path} の [env] が不正です（テーブルではありません）")
        st.stop()

    loc = env_tbl.get("location")
    if not isinstance(loc, str) or not loc.strip():
        st.error(f"{secrets_path} の [env].location が未設定です")
        st.stop()

    return loc.strip()
