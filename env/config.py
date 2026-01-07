# common_lib/env/config.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


def read_toml_required(path: Path) -> Dict[str, Any]:
    """
    TOML を必須として読み込む。
    - 読めない / 構文不正 / dict でない → Streamlit でエラー表示して停止
    """
    if tomllib is None:
        st.error("tomllib が利用できません（Python 3.11+ が必要です）")
        st.stop()

    if not path.exists():
        st.error(f"TOML ファイルが見つかりません：\n{path}")
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


def _projects_root_from_common_lib() -> Path:
    """
    .../projects/common_lib/env/config.py -> parents[2] == .../projects
    """
    return Path(__file__).resolve().parents[2]


def get_location_from_command_station_secrets(projects_root: Path | None = None) -> str:
    """
    command_station の secrets.toml を正本として location を返す。
    - パスは設計上確定
    - 見つからない / 未設定なら Streamlit でエラー表示して停止
    - 暗黙デフォルトは使わない

    secrets.toml 必須:
      [env]
      location = "Home" など
    """
    if projects_root is None:
        projects_root = _projects_root_from_common_lib()

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

    data = read_toml_required(secrets_path)

    env_tbl = data.get("env")
    if not isinstance(env_tbl, dict):
        st.error(f"{secrets_path} の [env] が不正です（テーブルではありません）")
        st.stop()

    loc = env_tbl.get("location")
    if not isinstance(loc, str) or not loc.strip():
        st.error(f"{secrets_path} の [env].location が未設定です")
        st.stop()

    return loc.strip()
