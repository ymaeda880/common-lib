# -*- coding: utf-8 -*-
# common_lib/ai/providers/azure/text_responses_create.py
# ============================================================
# Azure OpenAI Responses API（Text）
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from pathlib import Path
from typing import Any, Dict, Optional
import tomllib

# ============================================================
# imports（3rd party）
# ============================================================
from openai import OpenAI

# ============================================================
# types
# ============================================================
from ...types import TextResult, UsageSummary


# ============================================================
# Azure 固定設定
# ============================================================
AZURE_ENDPOINT = "https://prec-instance-001.openai.azure.com/"
AZURE_BASE_URL = AZURE_ENDPOINT.rstrip("/") + "/openai/v1/"
AZURE_SECRET_KEY_NAME = "AZURE_GPT5MINI_API_KEY"


# ============================================================
# projects root 探索
# ============================================================
def _find_projects_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if p.name == "projects":
            return p

    raise RuntimeError(
        "projects ルートが見つかりません。"
    )


# ============================================================
# auth_portal_app secrets.toml 解決
# ============================================================
def _resolve_auth_portal_secrets_path() -> Path:
    this_file = Path(__file__).resolve()
    projects_root = _find_projects_root(this_file)

    secrets_path = (
        projects_root
        / "auth_portal_project"
        / "auth_portal_app"
        / ".streamlit"
        / "secrets.toml"
    )

    if not secrets_path.exists():
        raise FileNotFoundError(
            f"secrets.toml が見つかりません: {secrets_path}"
        )

    return secrets_path


# ============================================================
# Azure API key 読み込み
# ============================================================
def _load_azure_api_key() -> str:
    secrets_path = _resolve_auth_portal_secrets_path()

    with secrets_path.open("rb") as f:
        secrets = tomllib.load(f)

    api_key = secrets.get(AZURE_SECRET_KEY_NAME)

    if not api_key:
        raise RuntimeError(
            f"{AZURE_SECRET_KEY_NAME} が secrets.toml に設定されていません。"
        )

    return str(api_key)


# ============================================================
# usage 抽出
# ============================================================
def _usage_to_summary(usage: Any) -> UsageSummary:
    if usage is None:
        return UsageSummary()

    if hasattr(usage, "model_dump"):
        raw = usage.model_dump()
    elif isinstance(usage, dict):
        raw = dict(usage)
    else:
        raw = {}

    input_tokens = raw.get("input_tokens")
    output_tokens = raw.get("output_tokens")
    total_tokens = raw.get("total_tokens")

    return UsageSummary(
        input_tokens=input_tokens if isinstance(input_tokens, int) else None,
        output_tokens=output_tokens if isinstance(output_tokens, int) else None,
        total_tokens=total_tokens if isinstance(total_tokens, int) else None,
        raw=raw or None,
    )


# ============================================================
# raw response 辞書化
# ============================================================
def _raw_to_dict(response: Any) -> Dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()

    if isinstance(response, dict):
        return dict(response)

    return {}


# ============================================================
# Azure Responses API 呼び出し
# ============================================================
def call_azure_responses_create(
    *,
    model: str,
    prompt: str,
    system: Optional[str],
    temperature: Optional[float],
    max_output_tokens: Optional[int],
    extra: Optional[Dict[str, Any]],
) -> TextResult:
    api_key = _load_azure_api_key()

    client = OpenAI(
        base_url=AZURE_BASE_URL,
        api_key=api_key,
    )

    kwargs: Dict[str, Any] = {
        "model": model,
        "input": prompt,
    }

    if system:
        kwargs["instructions"] = system

    if temperature is not None:
        kwargs["temperature"] = temperature

    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens

    if extra:
        kwargs.update(extra)

    response = client.responses.create(**kwargs)

    text = str(getattr(response, "output_text", "") or "").strip()
    usage = _usage_to_summary(getattr(response, "usage", None))

    return TextResult(
        provider="azure",
        model=str(model),
        text=text,
        usage=usage,
        cost=None,
        raw=_raw_to_dict(response),
    )