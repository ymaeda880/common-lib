# -*- coding: utf-8 -*-
# common_lib/inbox_ingest/types.py

# common_lib/inbox/inbox_common/types.py
# ============================================================
# Inbox 共通型・例外（正本）
# ============================================================
# - Inbox 操作（ingest / query / read）で共通に使う「境界データ型」を定義する
# - Streamlit など UI 依存は絶対に入れない（common_lib の純コア）
# ============================================================

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



# ============================================================
# 📦 Inbox から「読み込んだ結果」を統一形式で返すための型
# ============================================================
@dataclass(frozen=True)
class InboxPickedFile:
    """
    Inbox から読み込んだ 1 ファイルの結果（raw bytes）。

    data_bytes:
        実ファイルの中身（生 bytes）。画像/PDF/text/zip など全て raw bytes のまま返す。

    item_id / kind / original_name / stored_rel / added_at:
        inbox_items.db のメタ情報（ログやトレース、再参照用）。
    """

    # ------------------
    # 実データ（生bytes）
    # ------------------
    data_bytes: bytes

    # ------------------
    # DBメタ（ログ/トレース用）
    # ------------------
    item_id: str
    kind: str
    original_name: str
    stored_rel: str
    added_at: str
