# ============================================================
# common_lib/logs/jsonl_logger.py
# ------------------------------------------------------------
# 汎用 JSONL ロガー（COMMON_LIB）
#
# 特徴
# ----
# - 各アプリ（Streamlit ページなど）で共通利用可能
# - JSONL（1行1JSON）形式でログを追記
# - 書き込み失敗時もアプリを止めない（安全設計）
# - 出力キー順を固定：
#     ts → user → action → ... → app_name → page_name
#
# ログ出力先
# ----------
# - デフォルト（後方互換）:
#     {app_dir}/logs/{app_name}.log.jsonl
#
# - 月次ローテーション（opt-in）:
#     {app_dir}/logs/{app_name}_YYYY-MM.log.jsonl
#
# ※ 月次ローテーションは rotate="monthly" を明示指定した場合のみ有効
# ============================================================

from __future__ import annotations
from pathlib import Path
import json
import hashlib
import datetime as dt
from collections import OrderedDict
from typing import Any, Dict, Optional

# ------------------------------------------------------------
# JST（共通で固定）
# ------------------------------------------------------------
JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")


# ============================================================
# Utility
# ============================================================

def sha256_short(text: str, n: int = 16) -> str:
    """
    テキストを短縮ハッシュ化するユーティリティ関数。

    Parameters
    ----------
    text : str
        ハッシュ化したい文字列。
    n : int, optional
        返すハッシュの長さ（デフォルト: 16文字）。

    Returns
    -------
    str
        SHA-256 の16進ハッシュ文字列の先頭 n 文字。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


# ============================================================
# JsonlLogger
# ============================================================

class JsonlLogger:
    """
    各アプリで共通利用できる JSONL 形式のロガー。

    各ログ行は独立した JSON オブジェクトとして追記される。
    ログは append-only であり、履歴の改変を行わない。

    Parameters
    ----------
    app_dir : Path
        アプリディレクトリのパス
        （例: Path(__file__).resolve().parents[1]）
    app_name : str, optional
        アプリ名（省略時は app_dir.name）
    page_name : str, optional
        ページ名（Streamlit ページ名など）
    ensure_dir : bool, optional
        True の場合、ログディレクトリを自動作成（デフォルト: True）
    rotate : {"none", "monthly"}, optional
        ログローテーション方式（デフォルト: "none"）
        - "none"    : 従来通り単一ファイル（後方互換）
        - "monthly" : 月次ファイル {app_name}_YYYY-MM.log.jsonl
    """

    def __init__(
        self,
        app_dir: Path,
        app_name: Optional[str] = None,
        page_name: Optional[str] = None,
        ensure_dir: bool = True,
        rotate: str = "none",
    ) -> None:
        # ---- 基本情報 ----
        self.app_dir = Path(app_dir)
        self.app_name = app_name or self.app_dir.name
        self.page_name = page_name
        self.rotate = rotate

        # ---- ログディレクトリ ----
        self.log_dir = self.app_dir / "logs"
        if ensure_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        # ---- 後方互換用の固定ログファイル ----
        # rotate="none" の場合はこのパスがそのまま使われる
        self.log_file = self.log_dir / f"{self.app_name}.log.jsonl"

    # ------------------------------------------------------------
    @staticmethod
    def now_iso_jst() -> str:
        """
        現在時刻（JST）を ISO8601 形式で返す。
        """
        return dt.datetime.now(JST).isoformat()

    # ------------------------------------------------------------
    def _current_log_file(self) -> Path:
        """
        現在書き込み対象となるログファイルパスを返す。

        rotate="monthly" の場合のみ、年月付きファイル名に切り替える。
        """
        if self.rotate == "monthly":
            ym = dt.datetime.now(JST).strftime("%Y-%m")
            return self.log_dir / f"{self.app_name}_{ym}.log.jsonl"

        # ---- 後方互換（従来方式）----
        return self.log_file

    # ------------------------------------------------------------
    def append(self, record: Dict[str, Any]) -> None:
        """
        JSONL 形式で 1 行ずつログを追記する。

        Parameters
        ----------
        record : dict
            追記するログデータ。
            - "ts", "app_name", "page_name" は自動付与
            - "user", "action" があれば先頭に配置

        Notes
        -----
        - 書き込み失敗時は例外を握りつぶす
          （ログの失敗でアプリを止めないため）
        """
        base = OrderedDict()

        # ---- 固定順序ヘッダ ----
        base["ts"] = self.now_iso_jst()

        if "user" in record:
            base["user"] = record.pop("user")
        if "action" in record:
            base["action"] = record.pop("action")

        # ---- 任意フィールド ----
        for k, v in record.items():
            base[k] = v

        # ---- アプリ情報（末尾）----
        base["app_name"] = self.app_name
        if self.page_name:
            base["page_name"] = self.page_name

        line = json.dumps(base, ensure_ascii=False)

        try:
            log_file = self._current_log_file()
            with log_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            # ログ出力失敗でアプリを止めない
            pass

    # ------------------------------------------------------------
    # 簡易レベル別ラッパ
    # ------------------------------------------------------------
    def info(self, msg: str, **kwargs):
        """INFO レベルの簡易ログ"""
        self.append({"level": "INFO", "msg": msg, **kwargs})

    def warn(self, msg: str, **kwargs):
        """WARN レベルの簡易ログ"""
        self.append({"level": "WARN", "msg": msg, **kwargs})

    def error(self, msg: str, **kwargs):
        """ERROR レベルの簡易ログ"""
        self.append({"level": "ERROR", "msg": msg, **kwargs})
