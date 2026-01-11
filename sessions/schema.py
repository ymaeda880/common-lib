# common_lib/sessions/schema.py
from __future__ import annotations

SCHEMA_SQL = """
-- ============================================================
-- sessions.db schema（正本）
-- 方針：
-- - eventログは持たない
-- - 現在状態（session_state）＋ 時系列（active_samples）＋ 日次（user_app_daily）＋ ユーザマスタ（user_directory）
-- - app_name は固定識別子（例：command_station_app）
-- - 時刻はJST（ISO文字列）で保存
-- ============================================================

PRAGMA foreign_keys = ON;

-- 現在状態：TTL判定の正本
CREATE TABLE IF NOT EXISTS session_state (
  session_id   TEXT PRIMARY KEY,
  user_sub     TEXT NOT NULL,
  app_name     TEXT NOT NULL,

  login_at     TEXT NOT NULL,  -- ISO (JST)
  last_seen    TEXT NOT NULL,  -- ISO (JST)
  logout_at    TEXT,           -- ISO (JST), nullable

  -- 参照用（将来のデバッグに役立つが必須ではない）
  user_agent   TEXT,
  client_ip    TEXT
);

CREATE INDEX IF NOT EXISTS idx_session_state_last_seen
  ON session_state(last_seen);

CREATE INDEX IF NOT EXISTS idx_session_state_app_last_seen
  ON session_state(app_name, last_seen);

CREATE INDEX IF NOT EXISTS idx_session_state_user_app
  ON session_state(user_sub, app_name);


-- 時系列サンプル：1分粒度・無期限
-- 主キーは (bucket_ts, app_name)
CREATE TABLE IF NOT EXISTS active_samples (
  bucket_ts       TEXT NOT NULL,  -- ISO (JST), minute-bucket
  app_name        TEXT NOT NULL,

  active_users    INTEGER NOT NULL,
  active_sessions INTEGER NOT NULL,

  peak_users      INTEGER NOT NULL,
  peak_sessions   INTEGER NOT NULL,

  sampled_at      TEXT NOT NULL,  -- ISO (JST), 書き込み時刻
  PRIMARY KEY (bucket_ts, app_name)
);

CREATE INDEX IF NOT EXISTS idx_active_samples_bucket
  ON active_samples(bucket_ts);

CREATE INDEX IF NOT EXISTS idx_active_samples_app_bucket
  ON active_samples(app_name, bucket_ts);


-- 日次集計：ユーザー別×アプリ別の利用量
-- active_minutes は「サンプルによりアクティブと観測された分数」
CREATE TABLE IF NOT EXISTS user_app_daily (
  date             TEXT NOT NULL,  -- YYYY-MM-DD (JST)
  user_sub         TEXT NOT NULL,
  app_name         TEXT NOT NULL,

  active_minutes   INTEGER NOT NULL DEFAULT 0,

  peak_users_day      INTEGER NOT NULL DEFAULT 0,
  peak_sessions_day   INTEGER NOT NULL DEFAULT 0,

  updated_at       TEXT NOT NULL,  -- ISO (JST)
  PRIMARY KEY (date, user_sub, app_name)
);

CREATE INDEX IF NOT EXISTS idx_user_app_daily_date
  ON user_app_daily(date);

CREATE INDEX IF NOT EXISTS idx_user_app_daily_app_date
  ON user_app_daily(app_name, date);

CREATE INDEX IF NOT EXISTS idx_user_app_daily_user_date
  ON user_app_daily(user_sub, date);


-- 将来拡張：ユーザー（部署）マスタ
CREATE TABLE IF NOT EXISTS user_directory (
  user_sub     TEXT PRIMARY KEY,
  display_name TEXT,
  dept_code    TEXT,
  dept_name    TEXT,
  is_active    INTEGER NOT NULL DEFAULT 1,
  updated_at   TEXT NOT NULL
);
"""
