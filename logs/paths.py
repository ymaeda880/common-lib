# -*- coding: utf-8 -*-
"""
common_lib/logs/paths.py

✅ ログ置き場・ファイル命名規約（Discovery / 正本）
- log_dir: Storages/logs/<app_name>/
- monthly: <log_name>_YYYY-MM.jsonl  （JST基準、YYYY-MM はファイル名から抽出可能）
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from common_lib.storage.external_ssd_root import resolve_storage_subdir_root

JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")


@dataclass(frozen=True)
class LogLayout:
    projects_root: Path
    app_name: str
    storage_root: Path
    log_dir: Path


def get_log_layout(projects_root: Path, app_name: str) -> LogLayout:
    pr = Path(projects_root)
    an = (app_name or "").strip() or "unknown_app"

    storage_root = Path(
        resolve_storage_subdir_root(
            pr,
            subdir="Storages",
            role="main",
        )
    ).resolve()

    log_dir = (storage_root / "logs" / an).resolve()
    return LogLayout(projects_root=pr, app_name=an, storage_root=storage_root, log_dir=log_dir)


_MONTHLY_RE_CACHE: Dict[str, re.Pattern] = {}


def _monthly_pattern(log_name: str) -> re.Pattern:
    ln = (log_name or "").strip()
    if not ln:
        ln = "unknown_log"

    pat = _MONTHLY_RE_CACHE.get(ln)
    if pat is None:
        # <log_name>_YYYY-MM.jsonl
        # YYYY-MM は 7文字固定
        pat = re.compile(rf"^{re.escape(ln)}_(\d{{4}}-\d{{2}})\.jsonl$")
        _MONTHLY_RE_CACHE[ln] = pat
    return pat


def month_from_filename(path: Path, log_name: str) -> Optional[str]:
    """
    <log_name>_YYYY-MM.jsonl から YYYY-MM を抽出。
    一致しなければ None。
    """
    p = Path(path)
    pat = _monthly_pattern(log_name)
    m = pat.match(p.name)
    if not m:
        return None
    return m.group(1)


def list_monthly_files(log_dir: Path, log_name: str) -> List[Path]:
    """
    log_dir から <log_name>_YYYY-MM.jsonl を列挙して返す（昇順）。
    """
    d = Path(log_dir)
    if not d.exists():
        return []

    ln = (log_name or "").strip() or "unknown_log"
    files = sorted(d.glob(f"{ln}_*.jsonl"))
    # 形式不一致も混ざる可能性があるので、month抽出できるものだけに絞る
    out: List[Path] = []
    for p in files:
        if month_from_filename(p, ln):
            out.append(p)
    return sorted(out)


def month_to_file_map(log_dir: Path, log_name: str) -> Dict[str, Path]:
    """
    {"YYYY-MM": Path(...)} を返す。
    同じ月が複数あった場合は、最後に見つかったものが勝つ（通常は起きない想定）。
    """
    m: Dict[str, Path] = {}
    for p in list_monthly_files(log_dir, log_name):
        mm = month_from_filename(p, log_name)
        if mm:
            m[mm] = p
    return m


def build_monthly_file(log_dir: Path, log_name: str, month: str) -> Path:
    """
    指定月の monthly ログファイルパスを組み立てる（存在は保証しない）。
    """
    ln = (log_name or "").strip() or "unknown_log"
    return (Path(log_dir) / f"{ln}_{month}.jsonl").resolve()


def current_month_jst() -> str:
    return dt.datetime.now(JST).strftime("%Y-%m")
