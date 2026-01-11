# common_lib/sessions/config.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionConfig:
    """
    セッション管理の固定パラメータ。

    - heartbeat_sec : クライアントからの生存更新の想定間隔（目安）
    - ttl_sec       : active 判定の有効期限（last_seen がこれ以内なら active）
    - sample_sec    : 時系列サンプルの粒度（今回は 60秒＝1分で確定）
    """
    heartbeat_sec: int = 30
    ttl_sec: int = 120
    sample_sec: int = 60
