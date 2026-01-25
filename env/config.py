# common_lib/env/config.py

# ============================================================
# common_lib/env/config.py
#
# 【役割】
# - command_station_app を正本とする設定情報（secrets.toml 等）を読み取る
# - storages_config などの基盤ロジックから利用される「設定取得の正本」
#
# 【設計上の重要方針】
# - 本ファイルは「設定の解釈・検証」を担う基盤層であり、
#   UI（Streamlit 画面）そのものの責務は持たない
# - ただし、Streamlit アプリから直接呼ばれることが前提のため、
#   通常実行時は st.error / st.stop による明示的な停止を行う
#
# 【Streamlit 依存の扱い】
# - import 時点で streamlit が必須になる設計は避ける
#   （import しただけで落ちると、基盤ロジックとして再利用できなくなる）
# - streamlit が利用可能な場合：
#       st.error(...) + st.stop() により UI 上で明示的に停止
# - streamlit が利用できない場合（例：CLI / worker / import チェック）：
#       RuntimeError を raise して確実に停止
#
#   ※ これにより
#     - 「設定が壊れているのに黙って別経路に進む」
#     - 「main / Storages / sessions.db が分裂する」
#     といった後発トラブルを防止する
#
# 【暗黙デフォルト禁止】
# - location / storages.mode 等について暗黙の既定値は一切使わない
# - 設定が無い・不正な場合は必ず停止する
#
# 【正本関係】
# - secrets.toml / storage.toml の正本は command_station_app 配下に固定
# - 他アプリ（minutes_app, auth_portal_app 等）は
#   必ず本モジュール経由で設定を参照する
#
# ============================================================

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:
    import streamlit as st  # type: ignore
except ModuleNotFoundError:
    st = None  # streamlit 無し環境向け

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


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


def read_toml_required(path: Path) -> Dict[str, Any]:
    """
    TOML を必須として読み込む。
    - 読めない / 構文不正 / dict でない → Streamlit でエラー表示して停止
    """
    if tomllib is None:
        _error_stop_or_raise("tomllib が利用できません（Python 3.11+ が必要です）")

    if not path.exists():
        _error_stop_or_raise(f"TOML ファイルが見つかりません：\n{path}")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        _error_stop_or_raise(f"TOML の読み込みに失敗しました：\n{path}\n\n{e}")

    if not isinstance(data, dict):
        _error_stop_or_raise(f"TOML の形式が不正です（dict ではありません）：\n{path}")

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
        _error_stop_or_raise(
            f"command_station の secrets.toml が見つかりません：\n{secrets_path}"
        )

    data = read_toml_required(secrets_path)

    env_tbl = data.get("env")
    if not isinstance(env_tbl, dict):
        _error_stop_or_raise(f"{secrets_path} の [env] が不正です（テーブルではありません）")

    loc = env_tbl.get("location")
    if not isinstance(loc, str) or not loc.strip():
        _error_stop_or_raise(f"{secrets_path} の [env].location が未設定です")

    return loc.strip()
