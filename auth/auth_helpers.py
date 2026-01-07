# ============================================================
# common_lib/auth/auth_helpers.py （PREC SSO 固定版）
# ------------------------------------------------------------
# 方針（重要）
# - PREC AI System 全体で CookieManager key を 1つに固定（CM_KEY）
# - ログイン判定の真実は Cookie(JWT)
#   -> Cookieが無い/無効なら session_state["current_user"] は必ず消す
# - portal だけが login/logout（cookie set/delete）を行う
#   -> 他アプリは require_login() を使うだけ
# - 互換性：cookie_manager_key / cm_key の両方を受け付ける
# ============================================================

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Set
from functools import lru_cache
import os
import json
import datetime as dt

# toml
try:
    import toml  # type: ignore
except Exception:  # pragma: no cover
    toml = None  # type: ignore

# extra_streamlit_components
try:
    import extra_streamlit_components as stx  # type: ignore
except Exception:  # pragma: no cover
    stx = None  # type: ignore

# JWT（存在しない環境でも落とさない）
try:
    from common_lib.auth.config import COOKIE_NAME  # type: ignore
    from common_lib.auth.jwt_utils import verify_jwt  # type: ignore
except Exception:  # pragma: no cover
    COOKIE_NAME = "prec_sso"  # フォールバック（あなたの実運用名に合わせる）
    def verify_jwt(token: Optional[str]) -> Optional[dict]:  # type: ignore
        return None


# ============================================================
# ★ システム共通：CookieManager key を 1つに固定
# ============================================================
CM_KEY = "cm_prec_sso"  # ← PREC AI System 全アプリで同じにする


# ============================================================
# 設定ファイル解決（管理者などのACL用）
# ============================================================
ENV_KEY = "ADMIN_SETTINGS_FILE"
PROJECT_FIXED_REL_PATH = Path("auth_portal_project/auth_portal_app/.streamlit/settings.toml")
UPWARD_REL_PATH = Path("auth_portal_app/.streamlit/settings.toml")


@lru_cache(maxsize=1)
def _resolve_settings_path() -> Optional[Path]:
    env = os.environ.get(ENV_KEY)
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p

    here = Path(__file__).resolve()

    # .../projects/common_lib/auth/auth_helpers.py -> parents[2] == .../projects
    try:
        projects_root = here.parents[2]
        cand = (projects_root / PROJECT_FIXED_REL_PATH).resolve()
        if cand.exists():
            return cand
    except Exception:
        pass

    for base in [here, *here.parents]:
        cand = (base / UPWARD_REL_PATH).resolve()
        if cand.exists():
            return cand

    return None


@lru_cache(maxsize=1)
def _load_settings() -> Dict[str, Any]:
    p = _resolve_settings_path()
    if not p or toml is None:
        return {}
    try:
        return toml.load(p) or {}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def get_admin_users() -> Set[str]:
    data = _load_settings()
    try:
        users = set(data.get("admin_users", {}).get("users", []))
    except Exception:
        users = set()
    return {str(u).strip() for u in users if str(u).strip()}


@lru_cache(maxsize=128)
def get_restricted_users(app_key: str) -> Set[str]:
    data = _load_settings()
    tbl = data.get("restricted_users", {})
    if not isinstance(tbl, dict):
        return set()
    users = tbl.get(app_key, [])
    if not isinstance(users, list):
        return set()
    return {str(u).strip() for u in users if str(u).strip()}


# ============================================================
# Cookie helpers
# ============================================================
def _get_cm(cm_key: str) -> "stx.CookieManager":
    if stx is None:
        raise RuntimeError("extra_streamlit_components is not available")
    return stx.CookieManager(key=str(cm_key or CM_KEY))


def _clear_cookie_everywhere(cm: "stx.CookieManager", name: str) -> None:
    epoch = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
    # path="/" を優先（これが重要）
    try:
        cm.set(name, "", expires_at=epoch, path="/")
    except Exception:
        pass
    # 念のため path 未指定も潰す
    try:
        cm.set(name, "", expires_at=epoch)
    except Exception:
        pass
    try:
        cm.delete(name)
    except Exception:
        pass


def _resolve_cm_key(cookie_manager_key: Optional[str] = None, cm_key: Optional[str] = None) -> str:
    # 互換：どちらか入っていればそれを使い、無ければ固定 CM_KEY
    return str((cookie_manager_key or cm_key or CM_KEY))


# ============================================================
# ログイン取得（最重要：session_state 復活を潰す）
# ============================================================
def get_current_user_from_session_or_cookie(
    st,
    cookie_manager_key: Optional[str] = None,
    cm_key: Optional[str] = None,  # 互換別名
) -> Tuple[Optional[str], Optional[dict]]:
    """
    優先順位（固定）:
      1) Cookie(JWT) が有効 → user を返す（session_state に同期）
      2) Cookie が無い/無効 → session_state["current_user"] を必ず消して未ログイン

    ※ これにより「ログアウト後にリロードするとログインに戻る」を根絶する
    """
    _cm_key = _resolve_cm_key(cookie_manager_key=cookie_manager_key, cm_key=cm_key)

    payload: Optional[dict] = None
    token: Optional[str] = None

    try:
        cm = _get_cm(_cm_key)
        token = cm.get(COOKIE_NAME)
        payload = verify_jwt(token) if token else None
    except Exception:
        payload = None

    if payload and payload.get("sub"):
        user = str(payload["sub"]).strip()
        if user:
            st.session_state["current_user"] = user
            return user, payload

    # Cookie が無い/無効 → session を自動クリア
    if st.session_state.get("current_user"):
        st.session_state.pop("current_user", None)

    return None, None


def require_login(
    st,
    cookie_manager_key: Optional[str] = None,
    cm_key: Optional[str] = None,
) -> Optional[str]:
    user, _ = get_current_user_from_session_or_cookie(st, cookie_manager_key=cookie_manager_key, cm_key=cm_key)
    if not user:
        # UIは最低限。遷移はアプリ側で。
        import streamlit as _st
        _st.warning("ログインしていません。ポータルからログインしてください。")
        return None
    return user


def logout(
    st,
    cookie_manager_key: Optional[str] = None,
    cm_key: Optional[str] = None,
) -> None:
    """
    共通ログアウト（portal が呼ぶ）
    - session_state["current_user"] を消す
    - Cookie(COOKIE_NAME) を確実に消す（path='/'）
    """
    st.session_state.pop("current_user", None)

    _cm_key = _resolve_cm_key(cookie_manager_key=cookie_manager_key, cm_key=cm_key)
    try:
        cm = _get_cm(_cm_key)
        _clear_cookie_everywhere(cm, COOKIE_NAME)
    except Exception:
        pass


# ============================================================
# 権限
# ============================================================
def is_admin(user: Optional[str]) -> bool:
    if not user:
        return False
    admins = get_admin_users()
    u = user.strip().lower()
    admins_lower = {a.strip().lower() for a in admins}
    return u in admins_lower


def is_restricted_allowed(user: Optional[str], app_key: str) -> bool:
    if not user:
        return False
    if is_admin(user):
        return True
    allowed = get_restricted_users(app_key)
    u = user.strip().lower()
    allowed_lower = {a.strip().lower() for a in allowed}
    return u in allowed_lower


def require_admin(
    st,
    cookie_manager_key: Optional[str] = None,
    cm_key: Optional[str] = None,
) -> Optional[str]:
    user = require_login(st, cookie_manager_key=cookie_manager_key, cm_key=cm_key)
    if not user:
        return None
    if not is_admin(user):
        import streamlit as _st
        _st.error("権限エラー：このページは管理者のみ利用できます。")
        _debug_print_access_config(prefix="[require_admin]")
        return None
    return user


def require_restricted(
    st,
    app_key: str,
    cookie_manager_key: Optional[str] = None,
    cm_key: Optional[str] = None,
) -> Optional[str]:
    user = require_login(st, cookie_manager_key=cookie_manager_key, cm_key=cm_key)
    if not user:
        return None
    if not is_restricted_allowed(user, app_key):
        import streamlit as _st
        _st.error(f"権限エラー：この機能（{app_key}）は許可ユーザーのみ利用できます。")
        _debug_print_access_config(prefix=f"[require_restricted:{app_key}]")
        return None
    return user


def require_admin_user(
    st,
    cookie_manager_key: Optional[str] = None,
    cm_key: Optional[str] = None,
) -> Optional[str]:
    # UIを出さない版（あなたの運用）
    user, _ = get_current_user_from_session_or_cookie(st, cookie_manager_key=cookie_manager_key, cm_key=cm_key)
    if not user:
        return None
    if not is_admin(user):
        _debug_print_access_config(prefix="[require_admin_user]")
        return None
    return user


# ============================================================
# デバッグ
# ============================================================
def _debug_print_access_config(prefix: str = "[auth_debug]") -> None:
    p = _resolve_settings_path()
    admins = sorted(get_admin_users())
    info = {
        "settings_path": str(p) if p else None,
        "admin_users": admins,
        "cookie_name": COOKIE_NAME,
        "cm_key": CM_KEY,
    }
    print(f"{prefix} {json.dumps(info, ensure_ascii=False)}")


def debug_dump_admins() -> None:
    _debug_print_access_config(prefix="[debug_dump_admins]")


def clear_auth_caches() -> None:
    # ACL読み込み系だけ。Cookie/JWT にはキャッシュを持たない。
    try:
        _resolve_settings_path.cache_clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        _load_settings.cache_clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        get_admin_users.cache_clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        get_restricted_users.cache_clear()  # type: ignore[attr-defined]
    except Exception:
        pass
