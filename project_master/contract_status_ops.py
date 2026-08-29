# -*- coding: utf-8 -*-
# common_lib/project_master/contract_status_ops.py
# ============================================================
# Project Master: 契約書PDFステータス（contract_status.json）
#
# 目的：
# - <year>/<pno>/contract/contract_status.json を正本として読み書きする
# - contract_status.json には「契約書PDF登録の事実」のみを記録する
#
# json仕様：
# {
#   "registered_at": "ISO",
#   "registered_by": "sub"
# }
#
# 方針：
# - contract/ は存在が前提
# - contract/ はこのモジュールでは作成しない
# - JSONはatomic writeする
# ============================================================

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Optional

from common_lib.project_master.paths import (
    get_project_contract_dir,
    normalize_pno_3digits,
    normalize_year_4digits,
)


CONTRACT_STATUS_FILENAME = "contract_status.json"


def get_contract_status_path(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    contract_dir = get_project_contract_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    return contract_dir / CONTRACT_STATUS_FILENAME


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(
            "contract_status.json の読み込みに失敗しました。"
            f" path={path}"
        ) from e

    if not isinstance(value, dict):
        raise RuntimeError(
            "contract_status.json が dict ではありません。"
            f" got={type(value).__name__}"
        )

    return value


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    contract_dir = path.parent

    if not contract_dir.exists():
        raise RuntimeError(
            "contractフォルダーが存在しません（不整合）。"
            f" path={contract_dir}"
        )
    if not contract_dir.is_dir():
        raise RuntimeError(
            "contractがディレクトリではありません（不整合）。"
            f" path={contract_dir}"
        )

    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception as e:
        raise RuntimeError(
            "contract_status.json の書き込みに失敗しました。"
            f" path={path}"
        ) from e
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def read_contract_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Optional[Dict[str, Any]]:
    path = get_contract_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if not path.exists():
        return None
    return _read_json(path)


def write_contract_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    registered_by: str,
    role: str = "main",
) -> Path:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    now_iso = dt.datetime.now().replace(microsecond=0).isoformat()
    payload: Dict[str, Any] = {
        "registered_at": now_iso,
        "registered_by": str(registered_by),
    }

    path = get_contract_status_path(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    _write_json_atomic(path, payload)
    return path


def delete_contract_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> bool:
    path = get_contract_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    if not path.exists():
        return False
    if not path.is_file():
        raise RuntimeError(
            "contract_status.json がファイルではありません。"
            f" path={path}"
        )

    try:
        path.unlink()
    except Exception as e:
        raise RuntimeError(
            "contract_status.json の削除に失敗しました。"
            f" path={path}"
        ) from e

    return True
