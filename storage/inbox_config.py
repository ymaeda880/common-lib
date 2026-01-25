# common_lib/storage/inbox_config.py
# ============================================================
# inbox_config.py
# InBoxStorages のルート解決（正本）
# ============================================================
#
# 【設計背景と整理方針】
#
# 本モジュールは、InBoxStorages（Inbox）の配置場所を
# 「main / backup / backup2」という役割（role）と
# command_station の secrets.toml に基づいて一意に解決するための
# 正本APIを提供する。
#
# これまでの混乱点は以下にあった：
#   - Storages と Inbox で external SSD の解決方式が異なっていた
#   - Inbox 用に storage.toml 内に独立した
#       [inbox.storage.external.<location>]
#     ツリーを持っていたため、
#     「main のルートが二系統に分裂」していた
#
# 本設計ではそれを解消するため、以下の方針に統一している。
#
# ------------------------------------------------------------
# 【最重要方針】
#
# 1. external SSD の「物理 root 解決」はすべて
#      common_lib.storage.external_ssd_root.resolve_external_ssd_root()
#    に一本化する。
#
#    → storage.toml の正本は
#        [storage.external.<location>.<role>.root]
#      のみとし、Inbox 専用の external 定義は持たない。
#
# 2. InBoxStorages のディレクトリ名は常に固定：
#        "InBoxStorages"
#
#    external の場合も、
#        <external_ssd_root>/InBoxStorages
#    という構造に統一する。
#
# ------------------------------------------------------------
# 【role ごとの挙動】
#
# - role == "main"
#     secrets.toml の
#         [inbox].mode = "internal" | "external"
#     に従って配置を切り替える。
#
#     * internal:
#         projects_root / InBoxStorages
#
#     * external:
#         resolve_external_ssd_root(..., role="main") / InBoxStorages
#
# - role != "main"（backup / backup2）
#     Inbox の mode 設定に関係なく、
#     常に external SSD を使用する（強制）。
#
#     * backup / backup2:
#         resolve_external_ssd_root(..., role=role) / InBoxStorages
#
# ------------------------------------------------------------
# 【この設計で保証されること】
#
# - main の Storages / Inbox が「どこにあるか」は
#   secrets.toml と storage.toml を見れば一意に決まる
#
# - backup / backup2 は常に external に固定され、
#   誤って internal をバックアップしてしまう事故を防ぐ
#
# - 「main のルートが2系統に分かれる」問題を根本から防止する
#
# ------------------------------------------------------------
# 【利用者向けルール（重要）】
#
# ❌ 直接 Path を組み立てない：
#     projects_root / "InBoxStorages"
#
# ❌ resolve_storage_subdir_root(subdir="InBoxStorages") を使わない
#
# ✅ 必ず以下の API を使う：
#     resolve_inbox_root(projects_root)
#     resolve_inbox_root(projects_root, role="backup")
#
# これにより、Inbox の配置に関する判断は
# すべて本モジュールに集約される。
#
# ============================================================

from __future__ import annotations

from pathlib import Path
from typing import Literal

import streamlit as st

from common_lib.env.config import read_toml_required
from common_lib.storage.external_ssd_root import resolve_external_ssd_root

Role = Literal["main", "backup", "backup2"]

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


# ============================================================
# inbox mode の取得（正本：command_station secrets.toml）
# ============================================================
def get_inbox_mode_from_command_station_secrets(projects_root: Path) -> str:
    """
    command_station_app/.streamlit/secrets.toml を正本として inbox mode を返す。

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
        st.error(f'{p} の [inbox].mode は "internal" または "external" を指定してください')
        st.stop()

    return mode


# ============================================================
# InBoxStorages ルート解決（メインAPI）
# ============================================================
def resolve_inbox_root(projects_root: Path, *, role: Role = "main") -> Path:
    """
    InBoxStorages のルートディレクトリを解決して返す（正本API）。

    ✅ 方針（重要）
    - role == "main":
        secrets.toml の [inbox].mode に従って internal / external を切替
    - role != "main"（backup系）:
        mode に関係なく「常に external」を使用（強制）
    """
    # ------------------------------------------------------------
    # backup系は「常に external」を強制
    # ------------------------------------------------------------
    if role != "main":
        ssd_root = resolve_external_ssd_root(projects_root, role=role)
        inbox_root = ssd_root / _INTERNAL_INBOX_DIRNAME
        if not inbox_root.exists() or not inbox_root.is_dir():
            st.error(
                "\n".join(
                    [
                        "外部SSD上の InBoxStorages が見つかりません。",
                        f"- role     : {role}",
                        f"- 期待パス : {inbox_root}",
                        "外部SSDの構成（フォルダ）を確認してください（管理者対応）。",
                    ]
                )
            )
            st.stop()
        return inbox_root

    # ------------------------------------------------------------
    # main：mode に従う
    # ------------------------------------------------------------
    mode = get_inbox_mode_from_command_station_secrets(projects_root)

    # internal（固定運用）
    if mode == "internal":
        inbox_root = projects_root / _INTERNAL_INBOX_DIRNAME
        if not inbox_root.exists() or not inbox_root.is_dir():
            st.error(f"内部 InBoxStorages が存在しません: {inbox_root}")
            st.stop()
        return inbox_root

    # external（外部SSD / main）
    ssd_root = resolve_external_ssd_root(projects_root, role="main")
    inbox_root = ssd_root / _INTERNAL_INBOX_DIRNAME
    if not inbox_root.exists() or not inbox_root.is_dir():
        st.error(
            "\n".join(
                [
                    "外部SSD上の InBoxStorages が見つかりません。",
                    "- role     : main",
                    f"- 期待パス : {inbox_root}",
                    "外部SSDの構成（フォルダ）を確認してください（管理者対応）。",
                ]
            )
        )
        st.stop()

    return inbox_root
