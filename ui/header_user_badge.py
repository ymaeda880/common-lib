from __future__ import annotations
import base64, json

try:
    import extra_streamlit_components as stx
except Exception:
    stx = None  # fallbackでも落ちないように

# -----------------------------
# Cookie設定とJWT検証の読み込み
# -----------------------------
try:
    from common_lib.auth.config import COOKIE_NAME as COOKIE_NAME
    from common_lib.auth.jwt_utils import verify_jwt
except Exception:
    COOKIE_NAME = "prec_sso"
    verify_jwt = None


def get_current_user_from_cookie() -> str | None:
    """prec_sso クッキーから JWT の sub または user を返す（失敗時 None）"""
    if not stx:
        return None
    cm = stx.CookieManager()
    token = cm.get(COOKIE_NAME)
    if not token:
        return None

    user = None
    # 署名検証あり
    if verify_jwt:
        try:
            payload = verify_jwt(token)
            if isinstance(payload, dict):
                user = payload.get("sub") or payload.get("user")
        except Exception:
            user = None
    # フォールバック no-verify
    if not user:
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "===").decode())
            user = payload.get("sub") or payload.get("user")
        except Exception:
            pass
    return user
