# ============================================================
# common_lib/auth/auth_helpers.py  （固定パス・シンプル版）
# ------------------------------------------------------------
# - 設定ファイルは projects/auth_portal_project/auth_portal_app/.streamlit/settings.toml を最優先で参照
# - 環境変数 ADMIN_SETTINGS_FILE があれば最優先
# - それでも見つからなければ、上方探索で auth_portal_app/.streamlit/settings.toml を検索
# - 管理者/制限ユーザーは TOML から読み込み（大文字小文字は無視して比較）
# - debug_dump_admins() でコンソールに設定パスと管理者一覧を出力
# ============================================================

from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Set
from functools import lru_cache
import os
import json

import streamlit as st

# toml ライブラリ
try:
    import toml  # type: ignore
except Exception:  # pragma: no cover
    toml = None  # type: ignore

# extra_streamlit_components が無くても import エラーで落ちないように
try:
    import extra_streamlit_components as stx  # type: ignore
except Exception:  # pragma: no cover
    stx = None  # type: ignore

# JWT 関連（存在しない環境でも ImportError で落ちないよう防御）
try:
    from common_lib.auth.config import COOKIE_NAME  # type: ignore
    from common_lib.auth.jwt_utils import verify_jwt  # type: ignore
except Exception:  # pragma: no cover
    COOKIE_NAME = "auth_portal_token"  # フォールバック
    def verify_jwt(token: Optional[str]) -> Optional[dict]:  # type: ignore
        return None


# ============================================================
# 設定ファイルの解決
# 優先順位:
#   0) ENV ADMIN_SETTINGS_FILE
#   1) projects/ を起点に固定相対
#        (auth_portal_project/auth_portal_app/.streamlit/settings.toml)
#   2) 上方探索: 任意の上位で auth_portal_app/.streamlit/settings.toml
# ============================================================

ENV_KEY = "ADMIN_SETTINGS_FILE"

# projects 直下からの固定相対
PROJECT_FIXED_REL_PATH = Path("auth_portal_project/auth_portal_app/.streamlit/settings.toml")
# print(PROJECT_FIXED_REL_PATH)

# 上方探索時の相対（親ディレクトリ配下にそのままぶら下がっているケースに対応）
UPWARD_REL_PATH = Path("auth_portal_app/.streamlit/settings.toml")


@lru_cache(maxsize=1)
def _resolve_settings_path() -> Optional[Path]:
    """settings.toml の最終解決パスを返す。見つからなければ None。"""

    # 0) 環境変数優先
    env = os.environ.get(ENV_KEY)
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p

    here = Path(__file__).resolve()

    # 1) projects/ 直下を起点に固定相対で解決
    #    .../projects/common_lib/auth/auth_helpers.py
    #    -> parents[2] == .../projects
    try:
        projects_root = here.parents[2]
        cand = (projects_root / PROJECT_FIXED_REL_PATH).resolve()
        if cand.exists():
            return cand
    except Exception:
        pass

    # 2) 最後の保険として「上方探索」:
    #    任意の上位に auth_portal_app/.streamlit/settings.toml が居る構成
    for base in [here, *here.parents]:
        cand = (base / UPWARD_REL_PATH).resolve()
        if cand.exists():
            return cand

    return None


@lru_cache(maxsize=1)
def _load_settings() -> Dict[str, Any]:
    """TOML をロード（失敗時は空 dict を返す）"""
    p = _resolve_settings_path()
    if not p or toml is None:
        return {}
    try:
        return toml.load(p) or {}
    except Exception:
        return {}


# ============================================================
# ACL 読み出し
# ============================================================

@lru_cache(maxsize=1)
def get_admin_users() -> Set[str]:
    """
    [admin_users]
    users = ["maeda", "admin"]
    """
    data = _load_settings()
    users = set()
    try:
        users = set(data.get("admin_users", {}).get("users", []))
    except Exception:
        users = set()
    # 前後スペース排除
    return {str(u).strip() for u in users if str(u).strip()}

@lru_cache(maxsize=128)
def get_restricted_users(app_key: str) -> Set[str]:
    """
    [restricted_users]
    login_test = ["maeda","admin"]
    """
    data = _load_settings()
    tbl = data.get("restricted_users", {})
    if not isinstance(tbl, dict):
        return set()
    users = tbl.get(app_key, [])
    if not isinstance(users, list):
        return set()
    return {str(u).strip() for u in users if str(u).strip()}


# ============================================================
# ログイン取得
# ============================================================

def get_current_user_from_session_or_cookie(st) -> Tuple[Optional[str], Optional[dict]]:
    """
    1) st.session_state["current_user"]
    2) Cookie（extra_streamlit_components + jwt_utils.verify_jwt）
    の順でユーザー名（sub）を取り出す。
    返り値: (username or None, payload or None)
    """
    # 1) セッション優先
    u = st.session_state.get("current_user")
    if u:
        return u, None

    # 2) Cookie → JWT 検証
    try:
        if stx is None:
            raise RuntimeError("extra_streamlit_components is not available")
        cm = stx.CookieManager(key="cm_any_app")  # アプリごとにユニーク key 推奨
        token = cm.get(COOKIE_NAME)
        payload = verify_jwt(token) if token else None
        if payload and payload.get("sub"):
            user = str(payload["sub"])
            st.session_state["current_user"] = user  # セッションに反映
            return user, payload
    except Exception:
        pass

    return None, None


def require_login(st) -> Optional[str]:
    """
    未ログインなら警告を出して None。
    ログイン中ならユーザー名を返す。
    """
    user, _ = get_current_user_from_session_or_cookie(st)
    if not user:
        st.warning("未ログイン（Cookie 未検出）")
        return None
    return user


# ============================================================
# 権限チェック
# ============================================================

def is_admin(user: Optional[str]) -> bool:
    """
    ユーザーが管理者か？（TOML: [admin_users].users）
    大文字小文字の差は無視して判定。
    """
    if not user:
        return False
    admins = get_admin_users()
    u = user.strip().lower()
    admins_lower = {a.strip().lower() for a in admins}
    return u in admins_lower


def require_admin(st) -> Optional[str]:
    """
    管理者のみ閲覧可にしたい場合に使用。
    管理者でなければエラー表示し None を返す。
    管理者ならユーザー名を返す。
    """
    user = require_login(st)
    if not user:
        return None
    if not is_admin(user):
        st.error("権限エラー：このページは管理者のみ利用できます。")
        _debug_print_access_config(prefix="[require_admin]")
        return None
    return user


def is_restricted_allowed(user: Optional[str], app_key: str) -> bool:
    """
    制限アプリ（restricted）の許可ユーザー判定。
    app_key: TOML の [restricted_users] セクションのキー名（例: 'login_test'）
    管理者は常に許可。
    """
    if not user:
        return False
    if is_admin(user):
        return True
    allowed = get_restricted_users(app_key)
    u = user.strip().lower()
    allowed_lower = {a.strip().lower() for a in allowed}
    return u in allowed_lower


def require_restricted(st, app_key: str) -> Optional[str]:
    """
    指定の制限アプリに許可されたユーザーのみ通す。
    未ログイン・未許可ならエラーを出して None を返す。
    """
    user = require_login(st)
    if not user:
        return None
    if not is_restricted_allowed(user, app_key):
        st.error(f"権限エラー：この機能（{app_key}）は許可ユーザーのみ利用できます。")
        _debug_print_access_config(prefix=f"[require_restricted:{app_key}]")
        return None
    return user


# ============================================================
# UI バッジ（任意）
# ============================================================

def render_login_badge(st) -> Optional[str]:
    user, _ = get_current_user_from_session_or_cookie(st)
    if user:
        st.success(f"ログイン中: **{user}**")
    else:
        st.warning("未ログイン（Cookie 未検出）")
    return user


# ============================================================
# デバッグ支援
# ============================================================

def _debug_print_access_config(prefix: str = "[auth_debug]") -> None:
    """
    コンソール（サーバの標準出力）に設定パスと管理者・制限ユーザーを出力。
    Streamlit の UI には出しません。
    """
    p = _resolve_settings_path()
    admins = sorted(get_admin_users())
    info = {
        "settings_path": str(p) if p else None,
        "admin_users": admins,
    }
    print(f"{prefix} {json.dumps(info, ensure_ascii=False)}")


def debug_dump_admins() -> None:
    """手動で呼ぶ用途: 管理者一覧をコンソールに出す。"""
    _debug_print_access_config(prefix="[debug_dump_admins]")


# --- キャッシュを手動でクリア（設定反映用） ---
def clear_auth_caches() -> None:
    try: _resolve_settings_path.cache_clear()   # type: ignore[attr-defined]
    except Exception: pass
    try: _load_settings.cache_clear()           # type: ignore[attr-defined]
    except Exception: pass
    try: get_admin_users.cache_clear()          # type: ignore[attr-defined]
    except Exception: pass
    try: get_restricted_users.cache_clear()     # type: ignore[attr-defined]
    except Exception: pass


# ============================================================
# CLI: 直接実行用テストハーネス
# ------------------------------------------------------------
# 例:
#   python common_lib/auth/auth_helpers.py
#   python common_lib/auth/auth_helpers.py --user maeda
#   python common_lib/auth/auth_helpers.py --settings /abs/path/to/auth_portal_project/auth_portal_app/.streamlit/settings.toml
#   python common_lib/auth/auth_helpers.py --user maeda --app-key login_test
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="auth_helpers quick tester")
    parser.add_argument("--settings", type=str, default=None,
                        help="Absolute path to settings.toml (if omitted, try projects/ fixed path, then upward search).")
    parser.add_argument("--user", type=str, default=None, help="User name to test is_admin / restricted.")
    parser.add_argument("--app-key", type=str, default=None, help="restricted app key (e.g., login_test).")
    args = parser.parse_args()

    # settings の上書き（優先）
    if args.settings:
        os.environ[ENV_KEY] = args.settings

    # キャッシュクリア
    clear_auth_caches()

    # 設定の解決と管理者一覧を表示
    p = _resolve_settings_path()
    admins = sorted(get_admin_users())
    payload = {
        "settings_path": str(p) if p else None,
        "admin_users": admins,
    }
    print("[auth_helpers:settings]", json.dumps(payload, ensure_ascii=False, indent=2))

    # is_admin テスト
    if args.user:
        print(f"[auth_helpers:is_admin] user={args.user!r} -> {is_admin(args.user)}")

    # restricted テスト
    if args.user and args.app_key:
        print(f"[auth_helpers:is_restricted_allowed] user={args.user!r}, app_key={args.app_key!r} -> "
              f"{is_restricted_allowed(args.user, args.app_key)}")

    # 追加デバッグ（同等の情報をコンソールに出す）
    debug_dump_admins()
