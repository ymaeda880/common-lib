# -*- coding: utf-8 -*-
# common_lib/io/readers/json_reader.py
# ============================================================
# .json reader（UI非依存）
# - パースできるなら pretty に整形して渡す
# - パースできない場合は「エラー停止」（正本：厳格）
# ============================================================

from __future__ import annotations

import json
from typing import Tuple

from common_lib.io.decode import decode_bytes_to_text


# ============================================================
# reader
# ============================================================
def read_json_bytes_pretty(data: bytes) -> Tuple[str, str]:
    """
    JSON bytes を「整形済みテキスト」にする。

    方針（正本）：
    - decode（utf-8-sig / replace）
    - json.loads が失敗したら例外（静かに継続しない）
    - json.dumps(indent=2, ensure_ascii=False)

    Returns
    -------
    (pretty_text, decode_strategy)
    """
    text, strategy = decode_bytes_to_text(data)

    obj = json.loads(text)  # 失敗時は例外
    pretty = json.dumps(obj, ensure_ascii=False, indent=2)

    return pretty, strategy
