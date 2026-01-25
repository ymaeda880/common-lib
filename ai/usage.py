# common_lib/ai/usage.py
# =============================================================================
# usage tokens 抽出（正本）
# - Result から input/output tokens を安全に取得（推計しない）
# =============================================================================

from __future__ import annotations
from typing import Any, Optional, Tuple


def get_usage_tokens_if_any(res: Any) -> Tuple[Optional[int], Optional[int]]:
    usage = getattr(res, "usage", None)
    if usage is None:
        return (None, None)

    def _get(u: Any, key: str) -> Optional[int]:
        if u is None:
            return None
        if isinstance(u, dict):
            v = u.get(key)
        else:
            v = getattr(u, key, None)
        if v is None:
            return None
        try:
            return int(v)
        except Exception:
            return None

    in_tok = _get(usage, "input_tokens") or _get(usage, "prompt_tokens")
    out_tok = _get(usage, "output_tokens") or _get(usage, "completion_tokens")
    return (in_tok, out_tok)
