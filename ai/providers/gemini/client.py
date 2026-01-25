# -*- coding: utf-8 -*-
# common_lib/ai/providers/gemini/client.py

from __future__ import annotations

from pathlib import Path

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


def _find_projects_root(start: Path) -> Path:
    p = start.resolve()
    for parent in [p, *p.parents]:
        if parent.name == "projects":
            return parent
    raise RuntimeError(f"projects_root が特定できません: start={start}")


def _auth_portal_secrets_path() -> Path:
    here = Path(__file__).resolve()
    projects_root = _find_projects_root(here)
    return (
        projects_root
        / "auth_portal_project"
        / "auth_portal_app"
        / ".streamlit"
        / "secrets.toml"
    )


def _read_secrets_toml(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"secrets.toml が見つかりません: {path}")
    if tomllib is None:
        raise RuntimeError("tomllib が利用できません（Python 3.11+ を想定）")

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("secrets.toml の読み込みに失敗しました（dictではありません）")
    return data


# def configure_gemini() -> str:
#     secrets = _read_secrets_toml(_auth_portal_secrets_path())
#     key = secrets.get("GEMINI_API_KEY")
#     if not key:
#         raise RuntimeError("GEMINI_API_KEY が auth_portal_app の secrets.toml に定義されていません")

#     import google.generativeai as genai  # type: ignore
#     genai.configure(api_key=str(key).strip())
#     return str(key).strip()

# ============================================================
# Gemini client（google-genai）
# - auth_portal_app/.streamlit/secrets.toml の GEMINI_API_KEY のみ使用
# - deprecated google.generativeai は使わない
# ============================================================

# ============================================================
# google-genai（新SDK）: Client を返す（env依存にしない）
# ============================================================
def get_gemini_api_key() -> str:
    secrets = _read_secrets_toml(_auth_portal_secrets_path())
    key = secrets.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY が auth_portal_app の secrets.toml に定義されていません")
    return str(key).strip()


def get_genai_client():
    """
    google-genai の Client を必ず「APIキー明示」で作る。
    - 環境変数 GOOGLE_API_KEY には依存しない（方針）
    """
    key = get_gemini_api_key()

    # google-genai
    from google import genai  # type: ignore

    return genai.Client(api_key=key)


# ============================================================
# Gemini Client（google-genai）
# - configure_gemini() は「Client」を返す（文字列は返さない）
# ============================================================
_CLIENT = None  # module cache


def configure_gemini():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    secrets = _read_secrets_toml(_auth_portal_secrets_path())
    key = secrets.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY が auth_portal_app の secrets.toml に定義されていません")

    from google import genai  # type: ignore
    _CLIENT = genai.Client(api_key=str(key).strip())
    return _CLIENT



