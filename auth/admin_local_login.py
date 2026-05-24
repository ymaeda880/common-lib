# common_lib/auth/admin_local_login.py
# ============================================================
# Admin local login helper
#
# 機能：
# - 各アプリに置く「開発用・管理者専用ログインページ」から呼び出す
# - users.json のユーザー名・パスワードを検証する
# - settings.toml の admin_users に含まれるユーザーだけログイン許可する
# - JWT を発行し、共通 COOKIE_NAME に保存する
#
# 注意：
# - 本番用の一般ログインではなく、開発時の管理者ログイン補助用
# - CookieManager は呼び出し側ページで作成して渡す
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import datetime as dt
from pathlib import Path
from typing import Any

import streamlit as st
from werkzeug.security import check_password_hash

from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import issue_jwt


# ============================================================
# admin_users 取得
# ============================================================
def extract_admin_users(access_settings: dict[str, Any]) -> set[str]:
    raw_admin = access_settings.get("admin_users", [])

    if isinstance(raw_admin, dict):
        return set(raw_admin.get("users", []) or [])

    if isinstance(raw_admin, (list, tuple, set)):
        return set(raw_admin)

    return set()


# ============================================================
# users.json 認証
# ============================================================
def verify_user_password(
    *,
    users_db: dict[str, Any],
    username: str,
    password: str,
) -> bool:
    user_key = (username or "").strip()
    if not user_key:
        return False

    rec = (users_db.get("users") or {}).get(user_key)
    if not rec:
        return False

    return check_password_hash(rec.get("pw", ""), password or "")


# ============================================================
# 管理者判定
# ============================================================
def is_admin_user(
    *,
    username: str,
    admin_users: set[str],
) -> bool:
    user_key = (username or "").strip()
    return bool(user_key and user_key in admin_users)


# ============================================================
# JWT 発行
# ============================================================
def issue_admin_login_cookie(
    *,
    cookie_manager: Any,
    username: str,
) -> tuple[str, int]:
    user_key = (username or "").strip()
    if not user_key:
        raise RuntimeError("username is empty")

    try:
        token, exp = issue_jwt(user_key)
    except TypeError:
        token, exp = issue_jwt(user_key, [])

    cookie_manager.set(
        COOKIE_NAME,
        token,
        expires_at=dt.datetime.fromtimestamp(exp),
        path="/",
    )

    return token, exp


# ============================================================
# 管理者専用ログインフォーム描画
# ============================================================
def render_admin_local_login_form(
    *,
    cookie_manager: Any,
    users_db: dict[str, Any],
    access_settings: dict[str, Any],
    session_user_key: str = "current_user",
    show_login_state_key: str = "show_login_form",
    title: str = "🔐 開発用 管理者ログイン",
) -> str | None:
    st.subheader(title)

    st.caption(
        "このページは開発用の管理者専用ログインです。"
        " 管理者以外のユーザーはログインできません。"
    )

    admin_users = extract_admin_users(access_settings)

    c1, c2, c3 = st.columns([1, 1, 1])

    with c1:
        username = st.text_input(
            "ユーザー名",
            key="admin_local_login_username",
        )

    with c2:
        password = st.text_input(
            "パスワード",
            type="password",
            key="admin_local_login_password",
        )

    with c3:
        st.markdown("&nbsp;")
        do_login = st.button(
            "管理者ログイン",
            key="btn_admin_local_login",
        )

    if not do_login:
        return None

    user_key = (username or "").strip()

    if not user_key or not password:
        st.error("ユーザー名とパスワードを入力してください。")
        return None

    if not verify_user_password(
        users_db=users_db,
        username=user_key,
        password=password,
    ):
        st.error("ユーザー名またはパスワードが違います。")
        return None

    if not is_admin_user(
        username=user_key,
        admin_users=admin_users,
    ):
        st.error("管理者のみログインできます。")
        return None

    issue_admin_login_cookie(
        cookie_manager=cookie_manager,
        username=user_key,
    )

    st.session_state[session_user_key] = user_key
    st.session_state[show_login_state_key] = False

    st.success(f"✅ 管理者としてログインしました：{user_key}")

    return user_key