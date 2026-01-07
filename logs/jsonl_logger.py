# -*- coding: utf-8 -*-
"""
common_lib/logs/jsonl_logger.py

✅ 共通 JSONL ロガー（Storages 保存対応）
- 保存先：Storages/logs/<app_name>/
- ファイル名：
  - rotate="none"    : <log_name>.jsonl
  - rotate="monthly" : <log_name>_YYYY-MM.jsonl   （JST 基準）
- 1 行 = 1 JSON（append-only）
- ts（JST ISO8601）、app_name、page_name を自動付与
- user/action があれば先頭に寄せる
- ログ書き込み失敗でアプリを止めない（握りつぶし）

※ログ本文にプロンプト等を入れるかは呼び出し側で制御すること。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

# Storage root resolver（外部SSD切替を吸収）
from common_lib.storage.external_ssd_root import resolve_storage_subdir_root


# JST（固定）
JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")


def sha256_short(s: str, length: int = 12) -> str:
    """
    文字列の SHA256 を短縮して返す（ログ用途：同一性の追跡）
    """
    if s is None:
        s = ""
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return h[: max(1, int(length))]


class JsonlLogger:
    """
    各アプリで共通利用できる JSONL 形式のロガー（Storages 保存対応）。

    Parameters
    ----------
    projects_root : Path
        projects ルート（例：Path(__file__).resolve().parents[3]）
        ※Storages の解決に使用
    app_name : str
        アプリ名（例："auth_portal_app"）
        ※Storages/logs/<app_name>/ を作る
    page_name : str, optional
        ページ名（Streamlit ページ名など）
    log_name : str, optional
        ログファイルのベース名（拡張子なし）
        例：
          - "login_log"
          - "auth_portal_app"（従来互換っぽく app名にするのも可）
        省略時は app_name
    ensure_dir : bool, optional
        True の場合、ログディレクトリを自動作成（デフォルト: True）
    rotate : {"none", "monthly"}, optional
        ログローテーション方式（デフォルト: "none"）
    """

    def __init__(
        self,
        projects_root: Path,
        app_name: str,
        page_name: Optional[str] = None,
        log_name: Optional[str] = None,
        ensure_dir: bool = True,
        rotate: str = "none",
    ) -> None:
        self.projects_root = Path(projects_root)
        self.app_name = (app_name or "").strip() or "unknown_app"
        self.page_name = page_name
        self.log_name = (log_name or "").strip() or self.app_name
        self.rotate = rotate

        # ---- Storages root ----
        storage_root = resolve_storage_subdir_root(
            self.projects_root,
            subdir="Storages",
        )

        # ---- 保存先：Storages/logs/<app_name>/ ----
        self.log_dir = Path(storage_root) / "logs" / self.app_name
        if ensure_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        # ---- rotate="none" 用の固定パス ----
        self.log_file = self.log_dir / f"{self.log_name}.jsonl"

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

        rotate="monthly" の場合のみ、年月付きファイル名に切り替える（JST基準）。
        """
        if self.rotate == "monthly":
            ym = dt.datetime.now(JST).strftime("%Y-%m")
            return self.log_dir / f"{self.log_name}_{ym}.jsonl"

        # ---- 従来方式 ----
        return self.log_file

    # ------------------------------------------------------------
    def append(self, record: Dict[str, Any]) -> None:
        """
        JSONL 形式で 1 行ずつログを追記する。

        Notes
        -----
        - "ts" は自動付与（JST）
        - "user", "action" があれば先頭に配置
        - "app_name", "page_name" は末尾に付与
        - 書き込み失敗時は例外を握りつぶす（ログ失敗でアプリを止めない）
        """
        base = OrderedDict()

        # ---- 固定順序ヘッダ ----
        base["ts"] = self.now_iso_jst()

        # record を破壊しない（呼び出し側が再利用しても安全）
        rec = dict(record or {})

        if "user" in rec:
            base["user"] = rec.pop("user")
        if "action" in rec:
            base["action"] = rec.pop("action")

        # ---- 任意フィールド ----
        for k, v in rec.items():
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
        self.append({"level": "INFO", "msg": msg, **kwargs})

    def warn(self, msg: str, **kwargs):
        self.append({"level": "WARN", "msg": msg, **kwargs})

    def error(self, msg: str, **kwargs):
        self.append({"level": "ERROR", "msg": msg, **kwargs})
