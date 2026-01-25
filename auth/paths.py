# -*- coding: utf-8 -*-
# common_lib/auth/paths.py
from __future__ import annotations

from pathlib import Path
import streamlit as st


def resolve_auth_data_root(projects_root: Path) -> Path:
    """
    auth_portal_app の認証データ（ユーザー/パスワード等）正本ディレクトリを返す。

    固定パス運用（external 切替はしない）：
      <projects_root>/auth_portal_project/auth_portal_app/data

    問題があれば Streamlit 上で明示エラーを出して停止する。
    """
    p = projects_root / "auth_portal_project" / "auth_portal_app" / "data"

    if not p.exists() or not p.is_dir():
        st.error(
            "\n".join(
                [
                    "auth データ（正本）ディレクトリが見つかりません。",
                    f"- 期待パス: {p}",
                    "auth_portal_project/auth_portal_app の構成を確認してください（管理者対応）。",
                ]
            )
        )
        st.stop()

    return p
