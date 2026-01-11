# common_lib/sessions/sampler.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import SessionConfig
from .db import ensure_db
from .time_utils import now_jst, floor_to_minute, dt_to_iso, date_str_jst


def _list_active_users_and_sessions(
    con,
    *,
    cfg: SessionConfig,
    now_iso: str,
    app_name: str,
) -> Tuple[List[str], int]:
    """
    現在の active を TTL で判定し、
    - active user_sub の distinct list
    - active session 数
    を返す。

    ※「誰がactiveか」を user_app_daily に反映するため、list が必要。
    """
    # active sessions
    sess_count = con.execute(
        """
        SELECT COUNT(*)
          FROM session_state
         WHERE app_name = ?
           AND logout_at IS NULL
           AND last_seen >= datetime(?, printf('-%d seconds', ?))
        """,
        (app_name, now_iso, cfg.ttl_sec),
    ).fetchone()[0]

    users = con.execute(
        """
        SELECT DISTINCT user_sub
          FROM session_state
         WHERE app_name = ?
           AND logout_at IS NULL
           AND last_seen >= datetime(?, printf('-%d seconds', ?))
        """,
        (app_name, now_iso, cfg.ttl_sec),
    ).fetchall()

    user_list = [r[0] for r in users]
    return user_list, int(sess_count)


def maybe_sample_minute(
    *,
    db_path: Path,
    cfg: SessionConfig,
    app_name: str,
) -> None:
    """
    1分粒度のサンプルを積む（active_samples + user_app_daily）。

    仕様（重要）：
    - bucket は JST で分切り下げ（HH:MM:00）
    - active_samples は (bucket_ts, app_name) を主キーにして upsert
    - peak は同一バケット内で max 更新（peak_users / peak_sessions）
    - user_app_daily の active_minutes は「その分で active と観測されたら +1」
      ※同一分に何度呼ばれても重複加算しない（active_samples の INSERT 成否でガード）
    """
    now = now_jst()
    bucket = floor_to_minute(now)
    bucket_iso = dt_to_iso(bucket)
    now_iso = dt_to_iso(now)
    date_s = date_str_jst(now)

    con = ensure_db(db_path)
    try:
        user_list, active_sessions = _list_active_users_and_sessions(
            con, cfg=cfg, now_iso=now_iso, app_name=app_name
        )
        active_users = len(user_list)

        # ----------------------------------------------------
        # まず INSERT OR IGNORE（初回ならここで1行作られる）
        # ----------------------------------------------------
        con.execute(
            """
            INSERT OR IGNORE INTO active_samples(
              bucket_ts, app_name,
              active_users, active_sessions,
              peak_users, peak_sessions,
              sampled_at
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                bucket_iso,
                app_name,
                active_users,
                active_sessions,
                active_users,
                active_sessions,
                now_iso,
            ),
        )

        # changes() == 1 なら「この分は初回」＝日次集計の minutes を加算して良い
        inserted = con.execute("SELECT changes()").fetchone()[0]
        first_time_this_bucket = bool(inserted == 1)

        # ----------------------------------------------------
        # 既に存在する（あるいは初回でも）場合に、値を更新
        # - active_* は「最後に観測した値」で上書き
        # - peak_* は max で更新
        # ----------------------------------------------------
        con.execute(
            """
            UPDATE active_samples
               SET active_users    = ?,
                   active_sessions = ?,
                   peak_users      = CASE WHEN peak_users < ? THEN ? ELSE peak_users END,
                   peak_sessions   = CASE WHEN peak_sessions < ? THEN ? ELSE peak_sessions END,
                   sampled_at      = ?
             WHERE bucket_ts = ?
               AND app_name  = ?
            """,
            (
                active_users,
                active_sessions,
                active_users,
                active_users,
                active_sessions,
                active_sessions,
                now_iso,
                bucket_iso,
                app_name,
            ),
        )

        # ----------------------------------------------------
        # 日次：この分が初回なら、active ユーザーごとに +1 minute
        # （同じ分に何度呼ばれても二重計上しない）
        # ----------------------------------------------------
        if first_time_this_bucket:
            for user_sub in user_list:
                con.execute(
                    """
                    INSERT INTO user_app_daily(
                      date, user_sub, app_name,
                      active_minutes,
                      peak_users_day, peak_sessions_day,
                      updated_at
                    )
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(date, user_sub, app_name) DO UPDATE SET
                      active_minutes = user_app_daily.active_minutes + 1,
                      -- 日次ピークは「その分の peak（全体）」を参考に更新する（ユーザー別ピークではない）。
                      -- 将来、ユーザー別ピーク定義が必要なら別途テーブルを設計する。
                      peak_users_day = CASE WHEN user_app_daily.peak_users_day < ? THEN ? ELSE user_app_daily.peak_users_day END,
                      peak_sessions_day = CASE WHEN user_app_daily.peak_sessions_day < ? THEN ? ELSE user_app_daily.peak_sessions_day END,
                      updated_at = ?
                    """,
                    (
                        date_s,
                        user_sub,
                        app_name,
                        1,
                        0,
                        0,
                        now_iso,
                        active_users,
                        active_users,
                        active_sessions,
                        active_sessions,
                        now_iso,
                    ),
                )

        con.commit()
    finally:
        con.close()
