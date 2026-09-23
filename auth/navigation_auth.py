# -*- coding: utf-8 -*-
# common_lib/auth/navigation_auth.py
# ============================================================
# navigation表示用 認証参照
#
# 機能：
# - 現在ログイン中のユーザーをCookie(JWT)から参照する
# - navigation表示用にログイン判定を行う
# - navigation表示用に管理者判定を行う
#
# 方針：
# - auth_helpers.py は変更しない
# - CookieManager コンポーネントは生成しない
# - Streamlit の st.context.cookies を読み取るだけ
# - session_state["current_user"] は変更・削除しない
# - navigationや表示切替専用として使用する
# - login/logout処理には使用しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================

from typing import Optional

# ============================================================
# imports（3rd party）
# ============================================================

import streamlit as st

# ============================================================
# common_lib（auth）
# ============================================================

from common_lib.auth.auth_helpers import (
    is_admin,
    is_developer,
    is_planning,
)
from common_lib.auth.config import (
    COOKIE_NAME,
)
from common_lib.auth.jwt_utils import (
    verify_jwt,
)


# ============================================================
# current user
# ============================================================

def get_navigation_current_user() -> Optional[str]:
    # ------------------------------------------------------------
    # Streamlitのrequest contextからCookie(JWT)を参照する
    #
    # 重要：
    # - CookieManagerは生成しない
    # - session_stateは変更しない
    # - Cookieを削除・更新しない
    # - navigation表示判定だけに使用する
    # ------------------------------------------------------------

    try:
        token = st.context.cookies.get(
            COOKIE_NAME
        )
    except Exception:
        return None

    if not token:
        return None

    try:
        payload = verify_jwt(
            token
        )
    except Exception:
        return None

    if not payload:
        return None

    user = str(
        payload.get(
            "sub",
            "",
        )
        or ""
    ).strip()

    if not user:
        return None

    return user


# ============================================================
# logged in
# ============================================================

def is_navigation_logged_in() -> bool:
    # ------------------------------------------------------------
    # navigation表示用のログイン判定
    #
    # Cookie(JWT)から有効なユーザー名を取得できれば
    # ログイン済みと判定する
    # ------------------------------------------------------------

    user = get_navigation_current_user()

    return bool(
        user
    )


# ============================================================
# admin
# ============================================================

def is_navigation_admin() -> bool:
    # ------------------------------------------------------------
    # navigation表示用の管理者判定
    # ------------------------------------------------------------

    user = get_navigation_current_user()

    if not user:
        return False

    return bool(
        is_admin(
            user
        )
    )

# ============================================================
# developer
# ============================================================

def is_navigation_developer() -> bool:
    # ------------------------------------------------------------
    # navigation表示用の開発者判定
    # ------------------------------------------------------------

    user = get_navigation_current_user()

    if not user:
        return False

    return bool(
        is_developer(
            user
        )
    )



# ============================================================
# planning
# ============================================================

def is_navigation_planning() -> bool:
    # ------------------------------------------------------------
    # navigation表示用の企画部門判定
    # ------------------------------------------------------------

    user = get_navigation_current_user()

    if not user:
        return False

    return bool(
        is_planning(
            user
        )
    )