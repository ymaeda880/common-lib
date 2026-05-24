# common_lib/ui/page_header.py
# ============================================================
# Standard page header UI
#
# 機能：
# - 各 Streamlit 処理ページの共通ヘッダーを描画する
# - settings.toml から BANNER_KEY を読み込む
# - バナー、theme、intro CSS を初期化する
# - page_session_heartbeat を実行する
# - タイトル、サブタイトル、ログイン中ユーザー表示を描画する
#
# 注意：
# - st.set_page_config() は各 page.py 側で先に実行する
# - ページ固有の説明文は app/lib/.../explanation.py 側に置く
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from pathlib import Path
from typing import Any
import tomllib

import streamlit as st

# ============================================================
# common_lib imports
# ============================================================
from common_lib.sessions.page_entry import page_session_heartbeat
from common_lib.ui.banner_lines import render_banner_line_by_key
from common_lib.ui.theme_colors import get_theme_colors_from_banner_key
from common_lib.ui.intro_panel import render_intro_css
from common_lib.ui.ui_basics import subtitle


# ============================================================
# settings.toml 読み込み
# ============================================================
def load_app_settings_toml(
    *,
    app_dir: Path,
) -> dict[str, Any]:
    settings_path = app_dir / ".streamlit" / "settings.toml"

    if not settings_path.exists():
        raise RuntimeError(
            f"settings.toml が見つかりません: {settings_path}"
        )

    with open(settings_path, "rb") as f:
        return tomllib.load(f)


# ============================================================
# BANNER_KEY 取得
# ============================================================
def get_banner_key_from_settings(
    *,
    settings: dict[str, Any],
    default: str = "navy_dark",
) -> str:
    banner_key = settings.get("BANNER_KEY", default)

    if not isinstance(banner_key, str) or not banner_key.strip():
        return default

    return banner_key.strip()


# ============================================================
# theme / banner 初期化
# ============================================================
def setup_page_theme_from_settings(
    *,
    app_dir: Path,
    default_banner_key: str = "navy_dark",
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    settings = load_app_settings_toml(
        app_dir=app_dir,
    )

    banner_key = get_banner_key_from_settings(
        settings=settings,
        default=default_banner_key,
    )

    render_banner_line_by_key(
        banner_key,
    )

    theme = get_theme_colors_from_banner_key(
        banner_key,
    )

    render_intro_css(
        theme,
    )

    return settings, banner_key, theme


# ============================================================
# ログイン中表示
# ============================================================
def render_login_status(
    *,
    user_sub: str,
) -> None:
    st.success(
        f"✅ ログイン中: **{user_sub}**"
    )


# ============================================================
# タイトル行描画
# ============================================================
def render_page_title_row(
    *,
    title: str,
    user_sub: str,
    title_col_ratio: int = 2,
    status_col_ratio: int = 1,
) -> None:
    left, right = st.columns(
        [title_col_ratio, status_col_ratio],
    )

    with left:
        st.title(
            title,
        )

    with right:
        render_login_status(
            user_sub=user_sub,
        )


# ============================================================
# 標準ページヘッダー
# ============================================================
def render_standard_page_header(
    *,
    st_module: Any,
    projects_root: Path,
    app_dir: Path,
    app_name: str,
    page_name: str,
    title: str,
    subtitle_text: str = "",
    default_banner_key: str = "navy_dark",
) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
    settings, banner_key, theme = setup_page_theme_from_settings(
        app_dir=app_dir,
        default_banner_key=default_banner_key,
    )

    user_sub = page_session_heartbeat(
        st_module,
        projects_root,
        app_name=app_name,
        page_name=page_name,
    )

    render_page_title_row(
        title=title,
        user_sub=user_sub,
    )

    if subtitle_text:
        subtitle(
            subtitle_text,
        )

    return user_sub, theme, banner_key, settings