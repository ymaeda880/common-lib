# common_lib/busy/schema.py
# =============================================================================
# ai_runs.db スキーマ正本（共通ライブラリ / busy）
# - schema（DDL）の正本をここに集約（他ファイルにDDLを散らさない）
# - run（1回のAI呼び出し）を ai_runs に1行で永続保存
# - busyイベント（start/end/progress等）を ai_busy_events に永続保存
# - 時刻は JST の ISO 文字列（sessions系と同じ思想）
# - migration は「ALTER TABLE 追記」方式でこのファイルに積む
# =============================================================================

# -*- coding: utf-8 -*-
from __future__ import annotations

SCHEMA_SQL = r"""
-- ============================================================
-- ai_runs.db schema（正本）
-- 方針：
-- - busy は「状態」ではなく「永続ログ」
-- - 1回のAI呼び出し（run）を ai_runs に1行で記録
-- - busy_events は任意の補助イベント（start/end/progress等）を永続で積む
-- - 時刻は JST の ISO 文字列（sessions系と同じ思想）
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- runs（正本）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_runs (
  run_id        TEXT PRIMARY KEY,          -- UUID
  parent_run_id TEXT,                      -- バッチ全体run等を束ねたい時用（任意）
  user_sub      TEXT NOT NULL,
  app_name      TEXT NOT NULL,
  page_name     TEXT NOT NULL,
  task_type     TEXT NOT NULL,             -- text / image / transcribe / ...
  provider      TEXT NOT NULL,             -- openai / gemini / ...
  model         TEXT NOT NULL,

  status        TEXT NOT NULL,             -- started / running / success / error
  started_at    TEXT NOT NULL,             -- JST ISO
  finished_at   TEXT,                      -- JST ISO（未完了ならNULL）
  elapsed_ms    INTEGER,                   -- 任意

  input_tokens  INTEGER,
  output_tokens INTEGER,
  total_tokens  INTEGER,

  cost_usd      REAL,
  usd_jpy       REAL,
  cost_jpy      REAL,

  error_type    TEXT,
  error_message TEXT,

  meta_json     TEXT                        -- JSON文字列（任意）
);

CREATE INDEX IF NOT EXISTS idx_ai_runs_started_at ON ai_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_ai_runs_user_sub ON ai_runs(user_sub, started_at);
CREATE INDEX IF NOT EXISTS idx_ai_runs_app_page ON ai_runs(app_name, page_name, started_at);
CREATE INDEX IF NOT EXISTS idx_ai_runs_status ON ai_runs(status, started_at);
CREATE INDEX IF NOT EXISTS idx_ai_runs_parent ON ai_runs(parent_run_id, started_at);

-- ------------------------------------------------------------
-- busy / events（永続）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_busy_events (
  event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id     TEXT NOT NULL,
  ts         TEXT NOT NULL,                -- JST ISO
  event_type TEXT NOT NULL,                -- busy_start / busy_end / progress / ...
  phase      TEXT,                         -- api_call / write_output / ...
  message    TEXT,
  meta_json  TEXT,
  FOREIGN KEY(run_id) REFERENCES ai_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_busy_events_run ON ai_busy_events(run_id, ts);
CREATE INDEX IF NOT EXISTS idx_ai_busy_events_ts ON ai_busy_events(ts);
CREATE INDEX IF NOT EXISTS idx_ai_busy_events_type ON ai_busy_events(event_type, ts);

-- ------------------------------------------------------------
-- migration 方針（ALTER TABLE）はここに追記して積む
-- ------------------------------------------------------------
"""
