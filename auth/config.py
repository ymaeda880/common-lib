# common_lib/auth/config.py
# ============================================================
# JWT 設定値（auth共通）
# ============================================================

from __future__ import annotations
import os

# ========= JWT / Cookie 設定 =========
# 署名鍵（重要：実運用では secrets.toml か環境変数で管理）
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")  # ← 仮の秘密鍵
JWT_ALGO = "HS256"                 # 署名アルゴリズム
JWT_TTL_SECONDS = 8 * 3600         # 有効期限（秒）= 8時間
JWT_ISS = "prec"                   # 発行者 (issuer)
JWT_AUD = "prec-clients"           # 受信対象 (audience)
COOKIE_NAME = "prec_sso"

# ポータルアプリのベースURL（共通化）
PORTAL_URL = "/auth_portal"
