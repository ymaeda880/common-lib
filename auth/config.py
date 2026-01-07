# common_lib/auth/config.py
# ============================================================
# JWT 設定値（auth共通）
# - auth_portal_app/.streamlit/secrets.toml を単一の真実のソースにする
# - そこに AUTH_SECRET か JWT_SECRET があればそれを使う
# - 無ければ環境変数 JWT_SECRET
# - それでも無ければ dev フォールバック（※本番では必ず secrets を入れる）
# ============================================================

from __future__ import annotations

import os
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore

# ========= JWT / Cookie 設定 =========
JWT_ALGO = "HS256"
JWT_TTL_SECONDS = 8 * 3600
JWT_ISS = "prec"
JWT_AUD = "prec-clients"
COOKIE_NAME = "prec_sso"

# ポータルアプリのベースURL（共通化）
PORTAL_URL = "/auth_portal"


def _projects_root() -> Path:
    # .../projects/common_lib/auth/config.py -> parents[3] == .../projects
    return Path(__file__).resolve().parents[2]


def _load_auth_secret_from_portal_toml() -> str | None:
    """
    auth_portal_app/.streamlit/secrets.toml から秘密鍵を読む。
    secrets.toml の書き方は以下どれでもOK:
      AUTH_SECRET = "..."
      JWT_SECRET  = "..."
      [auth]
      AUTH_SECRET = "..."
    """
    if tomllib is None:
        return None

    p = (
        _projects_root()
        / "auth_portal_project"
        / "auth_portal_app"
        / ".streamlit"
        / "secrets.toml"
    )

    if not p.exists():
        return None

    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

    # 直下
    v = data.get("AUTH_SECRET") or data.get("JWT_SECRET")
    if isinstance(v, str) and v.strip():
        return v.strip()

    # [auth] テーブルも許容
    auth_tbl = data.get("auth")
    if isinstance(auth_tbl, dict):
        v2 = auth_tbl.get("AUTH_SECRET") or auth_tbl.get("JWT_SECRET")
        if isinstance(v2, str) and v2.strip():
            return v2.strip()

    return None


# ★ 最重要：全アプリで同じ秘密鍵になる決定ロジック
JWT_SECRET = (
    _load_auth_secret_from_portal_toml()
    or os.getenv("JWT_SECRET")
    or "dev-secret-change-me"
)

# ここで None/非文字列にならないよう最後に防御（今回の TypeError 対策）
if not isinstance(JWT_SECRET, str) or not JWT_SECRET.strip():
    JWT_SECRET = "dev-secret-change-me"
