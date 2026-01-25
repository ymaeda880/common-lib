# -*- coding: utf-8 -*-
# common_lib/ai/providers/openai/client.py

from __future__ import annotations

from pathlib import Path
from typing import Optional

from openai import OpenAI

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


def _find_projects_root(start: Path) -> Path:
    """
    start から親を辿り、ディレクトリ名が 'projects' の場所を projects_root とみなす。
    見つからなければ例外。
    """
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


def _get_openai_api_key() -> str:
    secrets = _read_secrets_toml(_auth_portal_secrets_path())
    key = secrets.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY が auth_portal_app の secrets.toml に定義されていません")
    return str(key).strip()


def get_client() -> OpenAI:
    return OpenAI(api_key=_get_openai_api_key())
