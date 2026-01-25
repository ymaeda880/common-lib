# -*- coding: utf-8 -*-
"""
common_lib/logs/jsonl_reader.py

✅ JSONL ログの堅牢ロード（壊れた行があっても落ちない）
- 1行ずつ JSON として読む
- パースできない行はスキップ
- ファイル単位の例外も握りつぶして続行
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class ReadStats:
    files: int
    lines_total: int
    rows_ok: int
    rows_bad_json: int
    files_failed: int


def read_jsonl_files(
    paths: Iterable[Path],
    *,
    return_stats: bool = False,
) -> pd.DataFrame | Tuple[pd.DataFrame, ReadStats]:
    targets = [Path(p) for p in (paths or []) if p and Path(p).exists()]
    if not targets:
        df = pd.DataFrame()
        if return_stats:
            return df, ReadStats(files=0, lines_total=0, rows_ok=0, rows_bad_json=0, files_failed=0)
        return df

    rows: List[Dict[str, Any]] = []

    lines_total = 0
    rows_ok = 0
    rows_bad_json = 0
    files_failed = 0

    for path in targets:
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    lines_total += 1
                    s = (line or "").strip()
                    if not s:
                        continue
                    try:
                        obj = json.loads(s)
                        if isinstance(obj, dict):
                            rows.append(obj)
                            rows_ok += 1
                        else:
                            # dict 以外は採用しない
                            rows_bad_json += 1
                    except Exception:
                        rows_bad_json += 1
                        continue
        except Exception:
            files_failed += 1
            continue

    df = pd.DataFrame(rows)
    if return_stats:
        return df, ReadStats(
            files=len(targets),
            lines_total=lines_total,
            rows_ok=rows_ok,
            rows_bad_json=rows_bad_json,
            files_failed=files_failed,
        )
    return df
