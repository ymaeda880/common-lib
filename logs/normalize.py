# -*- coding: utf-8 -*-
"""
common_lib/logs/normalize.py

✅ ts/user/month/date などの正規化を共通化
- ts: pandas datetime 化 + Asia/Tokyo に揃える（naive/aware 混在を吸収）
- date: ts の date
- month: ts の YYYY-MM
- user: 欠損補完
"""

from __future__ import annotations

import pandas as pd


def normalize_ts(
    df: pd.DataFrame,
    *,
    ts_col: str = "ts",
    tz: str = "Asia/Tokyo",
) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    if ts_col not in df.columns:
        df[ts_col] = pd.NaT
        return df

    ts = pd.to_datetime(df[ts_col], errors="coerce")

    # tz-aware / naive 混在の吸収
    try:
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
    except Exception:
        pass

    try:
        ts = ts.dt.tz_convert(tz)
    except Exception:
        # convert できない場合は localize を試す
        try:
            ts = ts.dt.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
        except Exception:
            pass

    df[ts_col] = ts
    return df


def add_date_month(
    df: pd.DataFrame,
    *,
    ts_col: str = "ts",
    date_col: str = "date",
    month_col: str = "month",
) -> pd.DataFrame:
    if df is None or df.empty:
        # 空でも列を揃えたいときのため
        if df is not None:
            if date_col not in df.columns:
                df[date_col] = pd.NaT
            if month_col not in df.columns:
                df[month_col] = None
        return df

    if ts_col not in df.columns:
        df[ts_col] = pd.NaT

    # ts が tz-aware を想定
    df[date_col] = df[ts_col].dt.date
    df[month_col] = df[ts_col].dt.strftime("%Y-%m")
    return df


def ensure_user(
    df: pd.DataFrame,
    *,
    user_col: str = "user",
    default: str = "(anonymous)",
) -> pd.DataFrame:
    if df is None:
        return df
    if user_col not in df.columns:
        df[user_col] = default
        return df
    df[user_col] = df[user_col].fillna(default)
    return df


def normalize_log_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    まとめて正規化：ts → date/month → user
    """
    if df is None:
        return df
    df = normalize_ts(df, ts_col="ts", tz="Asia/Tokyo")
    df = add_date_month(df, ts_col="ts", date_col="date", month_col="month")
    df = ensure_user(df, user_col="user", default="(anonymous)")
    return df
