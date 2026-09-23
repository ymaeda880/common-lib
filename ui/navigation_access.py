# -*- coding: utf-8 -*-
# common_lib/ui/navigation_access.py
# ============================================================
# 権限対応 navigation helper
#
# 機能：
# - st.Page を生成する
# - ページ単位で login=True / False を指定できる
# - ページ単位で admin_only=True を指定できる
# - ページ単位で developer_only=True を指定できる
# - navigation グループ単位で login=True / False を指定できる
# - navigation グループ単位で admin_only=True を指定できる
# - navigation グループ単位で developer_only=True を指定できる
# - デバッグ時に一般ユーザー表示へ強制切替できる
#
# 方針：
# - Streamlit の st.Page 自体は拡張しない
# - 権限により非表示となるページは None として除去する
# - グループ内に表示可能なページが0件の場合は空リストを返す
# - 実際のアクセス制御は各ページ側でも継続する
# - DEBUG_FORCE_GENERAL_USER は表示確認専用とする
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================

from typing import Any

import streamlit as st

from common_lib.auth.navigation_auth import (
    is_navigation_admin,
    is_navigation_developer,
    is_navigation_logged_in,
    is_navigation_planning,
)

# ============================================================
# DEBUG override
# ============================================================

_DEBUG_FORCE_GENERAL_USER = False


def set_navigation_debug_general_user(
    enabled: bool,
) -> None:
    # ------------------------------------------------------------
    # navigation表示だけを一般ユーザー状態へ強制する
    #
    # True:
    #   管理者・開発者でログインしていても
    #   「ログイン済み一般ユーザー」として表示判定する
    #
    # False:
    #   実際の権限に従う
    # ------------------------------------------------------------

    global _DEBUG_FORCE_GENERAL_USER

    _DEBUG_FORCE_GENERAL_USER = bool(
        enabled
    )


# ============================================================
# navigation login
# ============================================================

def _can_show_login_item() -> bool:
    # ------------------------------------------------------------
    # navigation表示用のログイン判定
    #
    # DEBUG_FORCE_GENERAL_USER=True の場合は，
    # ログイン済み一般ユーザーとして扱う
    # ------------------------------------------------------------

    if _DEBUG_FORCE_GENERAL_USER:
        return True

    return bool(
        is_navigation_logged_in()
    )


# ============================================================
# navigation admin
# ============================================================

def _can_show_admin_item() -> bool:
    # ------------------------------------------------------------
    # navigation表示用の管理者判定
    #
    # DEBUG_FORCE_GENERAL_USER=True の場合は，
    # 管理者用項目を非表示にする
    # ------------------------------------------------------------

    if _DEBUG_FORCE_GENERAL_USER:
        return False

    return bool(
        is_navigation_admin()
    )


# ============================================================
# navigation developer
# ============================================================

def _can_show_developer_item() -> bool:
    # ------------------------------------------------------------
    # navigation表示用の開発者判定
    #
    # DEBUG_FORCE_GENERAL_USER=True の場合は，
    # 開発者用項目を非表示にする
    # ------------------------------------------------------------

    if _DEBUG_FORCE_GENERAL_USER:
        return False

    return bool(
        is_navigation_developer()
    )




# ============================================================
# navigation planning
# ============================================================

def _can_show_planning_item() -> bool:
    # ------------------------------------------------------------
    # navigation表示用の企画部門判定
    #
    # DEBUG_FORCE_GENERAL_USER=True の場合は，
    # 企画部門用項目を非表示にする
    # ------------------------------------------------------------

    if _DEBUG_FORCE_GENERAL_USER:
        return False

    return bool(
        is_navigation_planning()
    )

# ============================================================
# page
# ============================================================

def nav_page(
    page: str,
    *,
    title: str,
    icon: str | None = None,
    url_path: str | None = None,
    default: bool = False,
    login: bool | None = None,
    admin_only: bool = False,
    developer_only: bool = False,
    planning_only: bool = False,
) -> Any | None:
    # ------------------------------------------------------------
    # 権限付き st.Page
    #
    # login=None
    #   → ログイン状態に関係なく表示
    #
    # login=True
    #   → ログイン済みの場合だけ表示
    #
    # login=False
    #   → 未ログインの場合だけ表示
    #
    # admin_only=True
    #   → 管理者だけに表示
    #
    # developer_only=True
    #   → 開発者だけに表示
    #
    # developer_only=True / admin_only=True の場合は，
    # login の指定より権限判定を優先する
    # ------------------------------------------------------------

    # --------------------------------------------------------
    # 企画部門専用
    # --------------------------------------------------------

    if (
        planning_only
        and not _can_show_planning_item()
    ):
        return None
    
    # --------------------------------------------------------
    # 開発者専用
    # --------------------------------------------------------

    if (
        developer_only
        and not _can_show_developer_item()
    ):
        return None

    # --------------------------------------------------------
    # 管理者専用
    # --------------------------------------------------------

    if (
        admin_only
        and not _can_show_admin_item()
    ):
        return None

    # --------------------------------------------------------
    # ログイン状態による表示制御
    #
    # developer_only=True / admin_only=True の場合は，
    # 権限判定だけを使用する
    # --------------------------------------------------------

    if (
        not developer_only
        and not admin_only
        and not planning_only
    ):

        # ----------------------------------------------------
        # login=True
        #   → ログイン済みの場合だけ表示
        # ----------------------------------------------------

        if (
            login is True
            and not _can_show_login_item()
        ):
            return None

        # ----------------------------------------------------
        # login=False
        #   → 未ログインの場合だけ表示
        # ----------------------------------------------------

        if (
            login is False
            and _can_show_login_item()
        ):
            return None

    kwargs: dict[str, Any] = {
        "title": title,
        "default": bool(
            default
        ),
    }

    if icon is not None:
        kwargs["icon"] = icon

    if url_path is not None:
        kwargs["url_path"] = url_path

    return st.Page(
        page,
        **kwargs,
    )


# ============================================================
# group
# ============================================================

def nav_group(
    pages: list[Any | None],
    *,
    login: bool | None = None,
    admin_only: bool = False,
    developer_only: bool = False,
    planning_only: bool = False,
) -> list[Any]:
    # ------------------------------------------------------------
    # navigationカテゴリ単位の権限制御
    #
    # login=None
    #   → ログイン状態に関係なく表示
    #
    # login=True
    #   → ログイン済みの場合だけ表示
    #
    # login=False
    #   → 未ログインの場合だけ表示
    #
    # admin_only=True
    #   → 管理者だけグループを表示
    #
    # developer_only=True
    #   → 開発者だけグループを表示
    #
    # planning_only=True
    #   → 企画部門ユーザーだけグループを表示
    #     開発者も表示対象とする
    #
    # 各ページ側の None もここで除去する
    # ------------------------------------------------------------

    # --------------------------------------------------------
    # 企画部門専用グループ
    # --------------------------------------------------------

    if (
        planning_only
        and not _can_show_planning_item()
    ):
        return []
    
    # --------------------------------------------------------
    # 開発者専用グループ
    # --------------------------------------------------------

    if (
        developer_only
        and not _can_show_developer_item()
    ):
        return []

    # --------------------------------------------------------
    # 管理者専用グループ
    # --------------------------------------------------------

    if (
        admin_only
        and not _can_show_admin_item()
    ):
        return []

    # --------------------------------------------------------
    # ログイン状態によるグループ表示制御
    #
    # developer_only=True / admin_only=True /
    # planning_only=True の場合は，
    # 権限判定だけを使用する
    # --------------------------------------------------------

    if (
        not developer_only
        and not admin_only
        and not planning_only
    ):

        # ----------------------------------------------------
        # login=True
        #   → ログイン済みの場合だけ表示
        # ----------------------------------------------------

        if (
            login is True
            and not _can_show_login_item()
        ):
            return []

        # ----------------------------------------------------
        # login=False
        #   → 未ログインの場合だけ表示
        # ----------------------------------------------------

        if (
            login is False
            and _can_show_login_item()
        ):
            return []

    return [
        page
        for page in pages
        if page is not None
    ]


# ============================================================
# remove empty groups
# ============================================================

def clean_navigation_groups(
    navigation_pages: dict[
        str,
        list[Any],
    ],
) -> dict[
    str,
    list[Any],
]:
    # ------------------------------------------------------------
    # ページが0件になったグループをnavigationから除外する
    # ------------------------------------------------------------

    return {
        group_name: pages
        for group_name, pages
        in navigation_pages.items()
        if pages
    }