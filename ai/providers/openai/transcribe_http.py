# -*- coding: utf-8 -*-
# common_lib/ai/providers/openai/transcribe_http.py

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter, Retry

from ...types import TranscribeResult
from ...errors import ProviderError, RetryableError, InvalidResponseError

from .client import get_client


def _get_transcribe_url(extra: Optional[Dict[str, Any]]) -> str:
    # 優先度:
    #   1) extra["endpoint"]
    #   2) env: OPENAI_TRANSCRIBE_URL
    #   3) OpenAI既定URL
    if extra and extra.get("endpoint"):
        return str(extra["endpoint"])
    v = os.environ.get("OPENAI_TRANSCRIBE_URL")
    if v:
        return v.strip()
    return "https://api.openai.com/v1/audio/transcriptions"


def _make_session() -> requests.Session:
    sess = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset({"POST"}),
    )
    sess.mount("https://", HTTPAdapter(max_retries=retries))
    return sess


def transcribe_http(
    *,
    model: str,
    audio_bytes: bytes,
    filename: str,          # ★ 追加（必須）
    mime_type: str,
    response_format: str = "json",  # json/text/srt/vtt
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    timeout_sec: int = 600,
    extra: Optional[Dict[str, Any]] = None,
) -> TranscribeResult:
    """
    OpenAI Transcribe（HTTP, requests）を叩く。
    pages/21 の直書きをここに寄せる用途。
    """
    client = get_client()
    # SDK内の key をそのまま使うため、ただしHTTPでは Bearer header を作る必要あり
    api_key = getattr(client, "api_key", None)
    if not api_key:
        raise ProviderError("OpenAI api_key が取得できません", provider="openai")

    url = _get_transcribe_url(extra)

    headers = {"Authorization": f"Bearer {api_key}"}
    files = {
            "file": (filename, audio_bytes, mime_type)
        }

    data: Dict[str, Any] = {"model": model, "response_format": response_format}

    if prompt and str(prompt).strip():
        data["prompt"] = str(prompt).strip()
    if language and str(language).strip():
        data["language"] = str(language).strip()

    sess = _make_session()

    try:
        resp = sess.post(url, headers=headers, files=files, data=data, timeout=int(timeout_sec))
    except requests.Timeout as e:
        raise RetryableError("OpenAI transcribe timeout", provider="openai") from e
    except Exception as e:
        raise ProviderError(f"OpenAI transcribe request failed: {e}", provider="openai") from e

    req_id = resp.headers.get("x-request-id")

    if resp.status_code in (429, 500, 502, 503, 504):
        raise RetryableError(
            f"OpenAI transcribe retryable error: {resp.status_code}",
            provider="openai",
            status_code=resp.status_code,
            request_id=req_id,
            raw=resp.text,
        )

    if not resp.ok:
        raise ProviderError(
            f"OpenAI transcribe error: {resp.status_code}",
            provider="openai",
            status_code=resp.status_code,
            request_id=req_id,
            raw=resp.text,
        )

    if response_format == "json":
        try:
            j = resp.json()
            text = j.get("text", "") if isinstance(j, dict) else ""
        except Exception:
            text = resp.text
    else:
        text = resp.text

    if text is None:
        raise InvalidResponseError("OpenAI transcribe: text が空です")

    return TranscribeResult(
        provider="openai",
        model=model,
        text=str(text) if text is not None else "",
        request_id=req_id,
        meta={"response_format": response_format, "endpoint": url},
        raw=None,
    )
