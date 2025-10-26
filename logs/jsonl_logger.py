# ============================================================
# common_lib/logs/jsonl_logger.py
# ------------------------------------------------------------
# 汎用 JSONL ロガー
# - 各アプリ（Streamlit ページなど）で簡単に利用可能
# - 出力先: {app_dir}/logs/{app_name}.log.jsonl
# - 各行を独立した JSON オブジェクトとして追記
# - 出力順序: ts → user → action → ... → app_name → page_name
# ============================================================

from __future__ import annotations
from pathlib import Path
import json
import hashlib
import datetime as dt
from collections import OrderedDict
from typing import Any, Dict, Optional

# ---- JST ----
JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")


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

    Examples
    --------
    >>> from common_lib.logs.jsonl_logger import sha256_short
    >>> sha256_short("教室の風景")
    '01b8d0a4dff65944'
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


class JsonlLogger:
    """
    各アプリで共通利用できる JSONL 形式のロガー。

    各ログ行は独立した JSON オブジェクトとして書き込まれます。
    出力ファイルはアプリ名に基づき logs/{app_name}.log.jsonl に自動保存されます。

    出力キーの順序は固定：
    ts → user → action → ... → app_name → page_name

    Parameters
    ----------
    app_dir : Path
        アプリディレクトリのパス（例: Path(__file__).resolve().parents[1]）。
    app_name : str, optional
        アプリ名（省略時は app_dir.name を使用）。
    page_name : str, optional
        ページ名（Streamlit ページなどで使用）。
    ensure_dir : bool, optional
        True の場合、ログディレクトリが存在しなければ自動作成（デフォルト: True）。

    Attributes
    ----------
    log_file : Path
        出力される JSONL ログファイルのパス。
    log_dir : Path
        ログディレクトリのパス。

    Examples
    --------
    >>> from pathlib import Path
    >>> from common_lib.logs.jsonl_logger import JsonlLogger, sha256_short
    >>>
    >>> # アプリディレクトリを指定して初期化
    >>> APP_DIR = Path(__file__).resolve().parents[1]
    >>> logger = JsonlLogger(APP_DIR, page_name=Path(__file__).stem)
    >>>
    >>> # 画像生成時のログ
    >>> logger.append({
    ...     "user": "maeda",
    ...     "action": "generate",
    ...     "model": "gpt-image-1",
    ...     "size": "1024x1024",
    ...     "prompt_hash": sha256_short("教室の風景"),
    ...     "prompt": "教室の風景",
    ... })
    >>>
    >>> # 修正時のログ
    >>> logger.append({
    ...     "user": "maeda",
    ...     "action": "edit",
    ...     "source": "inline",
    ...     "model": "gpt-image-1",
    ...     "size": "1024x1024",
    ...     "prompt_hash": sha256_short("学生を入れて"),
    ...     "prompt": "学生を入れて",
    ... })
    >>>
    >>> # 出力例（logs/image_maker_app.log.jsonl）
    >>> # {"ts": "2025-10-25T09:40:12.123456+09:00", "user": "maeda", "action": "generate", "model": "gpt-image-1", "size": "1024x1024", "prompt_hash": "01b8d0a4dff65944", "prompt": "教室の風景", "app_name": "image_maker_app", "page_name": "22_（新版）画像生成"}
    """

    def __init__(
        self,
        app_dir: Path,
        app_name: Optional[str] = None,
        page_name: Optional[str] = None,
        ensure_dir: bool = True,
    ) -> None:
        self.app_dir = Path(app_dir)
        self.app_name = app_name or self.app_dir.name
        self.page_name = page_name
        self.log_dir = self.app_dir / "logs"
        if ensure_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{self.app_name}.log.jsonl"

    # ------------------------------------------------------------
    @staticmethod
    def now_iso_jst() -> str:
        """現在時刻（JST）を ISO8601 形式で返す。"""
        return dt.datetime.now(JST).isoformat()

    # ------------------------------------------------------------
    def append(self, record: Dict[str, Any]) -> None:
        """
        JSONL形式で1行ずつ追記する。

        Parameters
        ----------
        record : dict
            追記するデータ（user, action, model, size, prompt など）。
            "ts", "app_name", "page_name" は自動的に付加される。

        Notes
        -----
        - 既存ファイルが存在する場合は追記モードで開く。
        - 書き込みエラーは無視（アプリを止めないため）。
        """
        base = OrderedDict()
        base["ts"] = self.now_iso_jst()
        if "user" in record:
            base["user"] = record.pop("user")
        if "action" in record:
            base["action"] = record.pop("action")

        # 残りのキー（任意）
        for k, v in record.items():
            base[k] = v

        # 最後にアプリ情報
        base["app_name"] = self.app_name
        if self.page_name:
            base["page_name"] = self.page_name

        line = json.dumps(base, ensure_ascii=False)
        try:
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass  # エラーは握りつぶす

    # ------------------------------------------------------------
    def info(self, msg: str, **kwargs):
        """INFOレベルの簡易ログ出力"""
        self.append({"level": "INFO", "msg": msg, **kwargs})

    def warn(self, msg: str, **kwargs):
        """WARNレベルの簡易ログ出力"""
        self.append({"level": "WARN", "msg": msg, **kwargs})

    def error(self, msg: str, **kwargs):
        """ERRORレベルの簡易ログ出力"""
        self.append({"level": "ERROR", "msg": msg, **kwargs})
