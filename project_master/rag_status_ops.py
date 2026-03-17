# common_lib/project_master/rag_status_ops.py
# ============================================================
# Project Master: RAG状態オペレーション（rag_status.json 正本API）
#
# ■ 目的
# - <year>/<pno>/text/rag_status.json を正本として扱う
# - RAG取り込み状態の読み取りI/Fを提供する
# - 「json無し = 未取り込み」を正規ルールとして扱う
#
# ■ 設計方針
# - 本モジュールは「読み取りI/F」を主目的とする
# - state.py は json を直接読まず、本モジュール経由で状態を受け取る
# - ファイルが存在しない場合はエラーにせず、未取り込みとして返す
# - JSON構文が壊れている場合は異常として例外を送出する
#
# ■ 配置
# - <year>/<pno>/text/rag_status.json
#
# ■ 現在の想定status
# - ingested
# - failed
# - not_ingested
#
# ※ 運用ルール
# - rag_status.json が存在しなければ「RAG取り込み前」
# - status == "ingested" の場合、text変更は原則不可
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# ============================================================
# imports（common_lib/project_master）
# ============================================================
from common_lib.project_master.paths import (
    get_project_text_dir,
    normalize_pno_3digits,
    normalize_year_4digits,
)

# ============================================================
# constants
# ============================================================
RAG_STATUS_FILENAME = "rag_status.json"

RAG_STATUS_NOT_INGESTED = "not_ingested"
RAG_STATUS_INGESTED = "ingested"
RAG_STATUS_FAILED = "failed"


# ============================================================
# dataclasses
# ============================================================
@dataclass(frozen=True)
class RagStatusRecord:
    # ------------------------------------------------------------
    # rag_status.json 全体の正規化済み表現
    # ------------------------------------------------------------
    exists: bool
    status: Optional[str]
    rag_ingested_at: Optional[str]
    rag_ingested_by: Optional[str]
    error_message: Optional[str]
    source_text_filename: Optional[str]
    source_text_sha256: Optional[str]
    path: Path


@dataclass(frozen=True)
class RagStateInfo:
    # ------------------------------------------------------------
    # state.py へ渡す軽量情報
    # ------------------------------------------------------------
    rag_status: Optional[str]
    rag_ingested_at: Optional[str]
    rag_ingested_by: Optional[str]


# ============================================================
# helpers（normalize）
# ============================================================
def _normalize_optional_str(value: Any) -> Optional[str]:
    # ------------------------------------------------------------
    # None / 空文字 / 空白のみ を None に正規化
    # ------------------------------------------------------------
    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None
    return s


def _normalize_status(value: Any) -> Optional[str]:
    # ------------------------------------------------------------
    # status を小文字・前後空白除去で正規化
    # - None / 空文字 は None
    # - 想定外の値も文字列として返す（呼び出し側で判定）
    # ------------------------------------------------------------
    s = _normalize_optional_str(value)
    if s is None:
        return None
    return s.lower()


# ============================================================
# path
# ============================================================
def get_rag_status_path(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> Path:
    # ------------------------------------------------------------
    # rag_status.json の正本パスを返す
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)
    p = normalize_pno_3digits(project_no)

    text_dir = get_project_text_dir(
        projects_root,
        project_year=y,
        project_no=p,
    )
    return text_dir / RAG_STATUS_FILENAME


# ============================================================
# read
# ============================================================
def read_rag_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> RagStatusRecord:
    # ------------------------------------------------------------
    # rag_status.json を読み取る
    #
    # ルール：
    # - ファイル無しは正常系（未取り込み）
    # - JSON壊れは異常系（例外）
    # ------------------------------------------------------------
    path = get_rag_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    if not path.exists():
        return RagStatusRecord(
            exists=False,
            status=None,
            rag_ingested_at=None,
            rag_ingested_by=None,
            error_message=None,
            source_text_filename=None,
            source_text_sha256=None,
            path=path,
        )

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(
            f"rag_status.json の内容が object ではありません: {path}"
        )

    return RagStatusRecord(
        exists=True,
        status=_normalize_status(data.get("status")),
        rag_ingested_at=_normalize_optional_str(data.get("rag_ingested_at")),
        rag_ingested_by=_normalize_optional_str(data.get("rag_ingested_by")),
        error_message=_normalize_optional_str(data.get("error_message")),
        source_text_filename=_normalize_optional_str(data.get("source_text_filename")),
        source_text_sha256=_normalize_optional_str(data.get("source_text_sha256")),
        path=path,
    )


def get_rag_status_for_state(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> RagStateInfo:
    # ------------------------------------------------------------
    # state.py に渡す軽量情報を返す
    # - json無しなら rag_status=None
    # ------------------------------------------------------------
    rec = read_rag_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    return RagStateInfo(
        rag_status=rec.status,
        rag_ingested_at=rec.rag_ingested_at,
        rag_ingested_by=rec.rag_ingested_by,
    )


def is_rag_ingested(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> bool:
    # ------------------------------------------------------------
    # RAG取り込み済みかを bool で返す
    #
    # 判定：
    # - json無し       -> False
    # - status=ingested -> True
    # - それ以外       -> False
    # ------------------------------------------------------------
    rec = read_rag_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )
    return rec.status == RAG_STATUS_INGESTED