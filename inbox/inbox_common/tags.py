# -*- coding: utf-8 -*-
# common_lib/inbox/inbox_common/tags.py
from __future__ import annotations

import json
from typing import List


# ============================================================
# Tags utilities (UI 非依存)
# ============================================================
def normalize_tags(tag_text: str) -> List[str]:
    """
    入力例：
      - "2025/001"
      - "2025/002/議事録"
      - "a, b, c"（カンマ区切り）
      - "a b c"（空白区切り）
      - "a\\nb\\nc"（改行区切り）

    返り値：
      - 空は []（タグなし）
      - それ以外は ['...','...']（空要素は除去）
    """
    s = (tag_text or "").strip()
    if not s:
        return []

    # 改行はカンマに寄せる
    s = s.replace("\n", ",")

    # カンマが含まれていればカンマ優先、無ければ空白区切り
    if "," in s:
        parts = [p.strip() for p in s.split(",")]
    else:
        parts = [p.strip() for p in s.split()]

    return [p for p in parts if p]


def tags_json_from_input(tag_text: str) -> str:
    """
    normalize_tags を通して tags_json を作る（DB保存用）
    """
    tags = normalize_tags(tag_text)
    return json.dumps(tags, ensure_ascii=False)
