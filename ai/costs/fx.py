# common_lib/ai/costs/fx.py
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class FxRate:
    """
    為替レート（USD -> JPY）
    - costs モジュールの外では使わない前提
    """
    usd_jpy: float
    source: str  # "env" / "secrets" / "default"


def get_default_usd_jpy(*, default: float = 150.0) -> FxRate:
    """
    優先度:
      1) 環境変数 USDJPY
      2) st.secrets["USDJPY"]（Streamlit実行時のみ）
      3) default
    """
    v = os.environ.get("USDJPY")
    if v:
        try:
            return FxRate(usd_jpy=float(v), source="env")
        except ValueError:
            pass

    try:
        import streamlit as st  # type: ignore

        v2 = st.secrets.get("USDJPY", None)
        if v2 is not None:
            return FxRate(usd_jpy=float(v2), source="secrets")
    except Exception:
        pass

    return FxRate(usd_jpy=float(default), source="default")


def usd_to_jpy(usd: float, *, usd_jpy: float) -> float:
    """USD→JPY（小数第2位）"""
    return round(float(usd) * float(usd_jpy), 2)
