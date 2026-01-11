# common_lib/sessions/__init__.py
"""
共通セッション管理（同時ログイン数・時系列サンプル）基盤

方針：
- 正本DBは command_station 側が決めた sessions.db だけ
- common_lib は「DBパスを受け取って」読み書きする（保存先の暗黙デフォルトを持たない）
- イベントログは持たない（sessions.db のみ）
- 時系列は 1分粒度（active_samples）を無期限で蓄積
- ユーザー別/アプリ別の日次集計（user_app_daily）も保持

主な入口：
- record_login(...)
- record_heartbeat(...)
- record_logout(...)
- maybe_sample_minute(...)   # 1分粒度で active_samples / user_app_daily を更新
- get_active_counts(...)
- get_active_sessions(...)
"""

from .config import SessionConfig
from .queries import get_active_counts, get_active_sessions

# Streamlit integration
from .streamlit_integration import init_session, heartbeat_tick
