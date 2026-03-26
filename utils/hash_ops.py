# common_lib/utils/hash_ops.py
# ============================================================
# hash utility（710から切り出し）
# ============================================================

from __future__ import annotations
import hashlib


def sha256_of_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()