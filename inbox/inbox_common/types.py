# -*- coding: utf-8 -*-
# common_lib/inbox_ingest/types.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any


# =========================
# 例外（UI側で捕まえる）
# =========================

class InboxIngestError(Exception):
    """ingest 系の基底例外"""


class InboxNotAvailable(InboxIngestError):
    """Inbox ルートが存在しない / 接続されていない"""


class QuotaExceeded(InboxIngestError):
    """容量超過"""

    def __init__(self, current: int, incoming: int, quota: int):
        self.current = current
        self.incoming = incoming
        self.quota = quota
        super().__init__(
            f"Quota exceeded: current={current}, incoming={incoming}, quota={quota}"
        )


class IngestFailed(InboxIngestError):
    """保存やDB登録の失敗"""


# =========================
# 入力 / 出力
# =========================

@dataclass(frozen=True)
class IngestRequest:
    user_sub: str
    filename: str
    data: bytes
    tags_json: str = "[]"
    origin: Optional[Dict[str, Any]] = None  # 他アプリ由来情報（任意）


@dataclass(frozen=True)
class IngestResult:
    item_id: str
    kind: str
    stored_rel: str
    size_bytes: int
    thumb_status: str
