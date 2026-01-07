# -*- coding: utf-8 -*-
# common_lib/inbox_ingest/quota.py

from __future__ import annotations

import os
from pathlib import Path

# デフォルト上限（将来：設定ファイル／ユーザー別に拡張）
QUOTA_BYTES_DEFAULT = 5 * 1024 * 1024 * 1024  # 5GB


def folder_size_bytes(p: Path) -> int:
    """
    ディレクトリ配下の総サイズ（bytes）
    - 存在しない場合は 0
    - race condition（途中削除など）は黙って無視
    """
    total = 0
    p = Path(p)
    if not p.exists():
        return 0

    for root, _, files in os.walk(p):
        for fn in files:
            fp = Path(root) / fn
            try:
                total += fp.stat().st_size
            except FileNotFoundError:
                # 走査中に消えた等は無視
                pass
    return total


def quota_bytes_for_user(sub: str) -> int:
    """
    ユーザーの Inbox 容量上限（bytes）

    現状：
    - 全ユーザー共通（QUOTA_BYTES_DEFAULT）

    将来：
    - user_sub に応じた分岐
    - settings.toml / DB / 環境変数 などに拡張可能
    """
    return QUOTA_BYTES_DEFAULT
