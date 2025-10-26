# ============================================================
# common_lib/auth/auth_helpers.py
# ------------------------------------------------------------
# ✅ Streamlit共通: ログイン状態取得 + 権限チェック（admin / restricted）
# - ログイン: session_state → Cookie(JWT) の順に判定
# - 権限設定の探索:
#     1) 環境変数 ADMIN_SETTINGS_FILE または APP_SETTINGS_FILE
#     2) ライブラリ位置から上方探索: .streamlit/settings.toml / setting.toml
#     3) AUTH_PORTAL_APP / auth_portal_app 配下の .streamlit/ 設定
#   ※ settings / setting、大小どちらにも対応
# - 比較は大文字小文字を無視して安全に
# ------------------------------------------------------------

from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Set
from functools import lru_cache
import os
import json

import streamlit as st

# toml ライブラリ（なければ空設定で動く）
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
# 設定ファイルの探索（settings / setting, 大小どちらにも対応）
# ============================================================

_ENV_KEYS = ("ADMIN_SETTINGS_FILE", "APP_SETTINGS_FILE")
_PORTAL_DIR_CANDIDATES = ("AUTH_PORTAL_APP", "auth_portal_app")
_FILE_NAME_CANDIDATES = ("settings.toml", "setting.toml")

@lru_cache(maxsize=1)
def _resolve_settings_path() -> Optional[Path]:
    # 0) 環境変数が最優先
    for key in _ENV_KEYS:
        env = os.environ.get(key)
        if env:
            p = Path(env).expanduser().resolve()
            if p.exists():
                return p

    here = Path(__file__).resolve()

    candidates: list[Path] = []

    # 1) ライブラリ位置から上方に向かって .streamlit/{settings,setting}.toml
    for base in [here, *here.parents]:
        for fn in _FILE_NAME_CANDIDATES:
            candidates.append((base / ".streamlit" / fn).resolve())

    # 2) AUTH_PORTAL_APP / auth_portal_app 配下の .streamlit/{settings,setting}.toml
    for base in [here, *here.parents]:
        for portal in _PORTAL_DIR_CANDIDATES:
            for fn in _FILE_NAME_CANDIDATES:
                candidates.append((base / portal / ".streamlit" / fn).resolve())

    # 3) 重複除去しながら最初に存在するものを返す
    seen: Set[Path] = set()
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        if p.exists():
            return p
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
    を読み込んでセットで返す（前後空白除去、空は除く）。
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
    のような形式から app_key ごとの許可ユーザー集合を返す。
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
        # 追加情報（デバッグ用）：見えている設定ファイルと管理者リスト
        p = _resolve_settings_path()
        admins = sorted(get_admin_users())
        st.error("権限エラー：このページは管理者のみ利用できます。")
        with st.expander("デバッグ情報（非公開推奨）", expanded=False):
            st.code(json.dumps({
                "settings_path": str(p) if p else None,
                "current_user": user,
                "admin_users": admins,
            }, ensure_ascii=False, indent=2))
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
        p = _resolve_settings_path()
        allowed = sorted(get_restricted_users(app_key))
        st.error(f"権限エラー：この機能（{app_key}）は許可ユーザーのみ利用できます。")
        with st.expander("デバッグ情報（非公開推奨）", expanded=False):
            st.code(json.dumps({
                "settings_path": str(p) if p else None,
                "current_user": user,
                "allowed_users_for_app": {app_key: allowed},
            }, ensure_ascii=False, indent=2))
        return None
    return user


# ============================================================
# UI バッジ（任意）
# ============================================================

def render_login_badge(st) -> Optional[str]:
    """
    右上などに置く簡易バッジ。
    戻り値: ユーザー名 or None
    """
    user, _ = get_current_user_from_session_or_cookie(st)
    if user:
        st.success(f"ログイン中: **{user}**")
    else:
        st.warning("未ログイン（Cookie 未検出）")
    return user



# --- キャッシュを手動でクリア（設定反映用） ---
def clear_auth_caches() -> None:
    try:
        _resolve_settings_path.cache_clear()   # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        _load_settings.cache_clear()           # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        get_admin_users.cache_clear()          # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        get_restricted_users.cache_clear()     # type: ignore[attr-defined]
    except Exception:
        pass
