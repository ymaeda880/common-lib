# -*- coding: utf-8 -*-
# common_lib/project_master/processing_status_ops.py
# ============================================================
# Project Master: 処理状態オペレーション（processing_status.json 正本API）
#
# ■ 目的
# - <year>/<pno>/text/processing_status.json を正本として読み書きする
# - 報告書PDFに対する処理状態を一元管理する
#   - source pdf 情報
#   - pdf 情報（kind / page_count）
#   - OCR
#   - text抽出
#   - cleaning
#   - RAG取り込み
#
# ■ 配置
# - <year>/<pno>/text/processing_status.json
#
# ■ 方針
# - json 無しは正常系（未処理）
# - 壊れた json は異常系として例外
# - 更新は常に atomic write
# - 各処理は「いつ」「誰が」を明示記録する
# - source_pdf_sha256 により、処理対象PDFの同一性を追跡する
# - PDF登録直後は processing_status.json を作らない
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import datetime as dt
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Optional

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
PROCESSING_STATUS_FILENAME = "processing_status.json"

PDF_KIND_TEXT = "text"
PDF_KIND_IMAGE = "image"

RAG_STATUS_NOT_INGESTED = "not_ingested"
RAG_STATUS_INGESTED = "ingested"
RAG_STATUS_FAILED = "failed"


# ============================================================
# dataclasses
# ============================================================
@dataclass(frozen=True)
class ProcessingStatusRecord:
    # ------------------------------------------------------------
    # source pdf 情報
    # ------------------------------------------------------------
    exists: bool
    path: Path

    source_pdf_filename: Optional[str]
    source_pdf_sha256: Optional[str]

    # ------------------------------------------------------------
    # pdf 基本情報
    # ------------------------------------------------------------
    pdf_kind: Optional[str]
    page_count: Optional[int]
    pdf_info_created_at: Optional[str]
    pdf_info_created_by: Optional[str]

    # ------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------
    ocr_done: bool
    ocr_at: Optional[str]
    ocr_by: Optional[str]

    # ------------------------------------------------------------
    # text抽出
    # ------------------------------------------------------------
    text_extracted: bool
    text_extracted_at: Optional[str]
    text_extracted_by: Optional[str]

    # ------------------------------------------------------------
    # cleaning
    # ------------------------------------------------------------
    cleaned: bool
    cleaned_at: Optional[str]
    cleaned_by: Optional[str]

    # ------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------
    rag_ingested: bool
    rag_ingested_at: Optional[str]
    rag_ingested_by: Optional[str]
    rag_status: Optional[str]

    # ------------------------------------------------------------
    # 失敗情報
    # ------------------------------------------------------------
    error_message: Optional[str]


@dataclass(frozen=True)
class ProcessingStatusStateInfo:
    # ------------------------------------------------------------
    # state.py / UI向け軽量情報
    # ------------------------------------------------------------
    rag_status: Optional[str]
    rag_ingested_at: Optional[str]
    rag_ingested_by: Optional[str]
    can_edit_text: bool


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


def _normalize_optional_int(value: Any) -> Optional[int]:
    # ------------------------------------------------------------
    # int 化。空や不正値は None
    # ------------------------------------------------------------
    if value is None:
        return None

    try:
        s = str(value).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _normalize_bool(value: Any) -> bool:
    # ------------------------------------------------------------
    # bool 正規化
    # ------------------------------------------------------------
    if isinstance(value, bool):
        return value

    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off", ""}:
        return False

    try:
        return int(s) != 0
    except Exception:
        return False


def _normalize_pdf_kind(value: Any) -> Optional[str]:
    # ------------------------------------------------------------
    # pdf kind を正規化
    # - 想定外の値も文字列として保持
    # ------------------------------------------------------------
    s = _normalize_optional_str(value)
    if s is None:
        return None

    s = s.lower()
    if s in {PDF_KIND_TEXT, PDF_KIND_IMAGE}:
        return s
    return s


def _normalize_rag_status(value: Any) -> Optional[str]:
    # ------------------------------------------------------------
    # rag status を正規化
    # ------------------------------------------------------------
    s = _normalize_optional_str(value)
    if s is None:
        return None
    return s.lower()


def _now_iso() -> str:
    # ------------------------------------------------------------
    # 現在日時（秒まで）
    # ------------------------------------------------------------
    return dt.datetime.now().replace(microsecond=0).isoformat()


# ============================================================
# helpers（paths）
# ============================================================
def get_processing_status_path(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> Path:
    # ------------------------------------------------------------
    # <year>/<pno>/text/processing_status.json の正本パス
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)
    p = normalize_pno_3digits(project_no)

    text_dir = get_project_text_dir(
        projects_root,
        project_year=y,
        project_no=p,
    )
    return text_dir / PROCESSING_STATUS_FILENAME


# ============================================================
# helpers（json io）
# ============================================================
def _read_json(path: Path) -> Dict[str, Any]:
    # ------------------------------------------------------------
    # json 読み込み（dict 前提）
    # ------------------------------------------------------------
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(
            f"processing_status.json の読み込みに失敗しました。 path={path}"
        ) from e

    if not isinstance(obj, dict):
        raise RuntimeError(
            f"processing_status.json が dict ではありません。 "
            f"path={path} got={type(obj).__name__}"
        )

    return obj


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    # ------------------------------------------------------------
    # atomic write
    # ------------------------------------------------------------
    text_dir = path.parent
    if not text_dir.exists():
        raise RuntimeError(f"text_dir が存在しません（不整合）。 path={text_dir}")
    if not text_dir.is_dir():
        raise RuntimeError(f"text_dir がディレクトリではありません（不整合）。 path={text_dir}")

    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception as e:
        raise RuntimeError(
            f"processing_status.json の書き込みに失敗しました。 path={path}"
        ) from e
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


# ============================================================
# helpers（payload <-> record）
# ============================================================
def _empty_payload() -> Dict[str, Any]:
    # ------------------------------------------------------------
    # 新規初期 payload
    # ------------------------------------------------------------
    return {
        "source_pdf_filename": None,
        "source_pdf_sha256": None,
        "pdf_kind": None,
        "page_count": None,
        "pdf_info_created_at": None,
        "pdf_info_created_by": None,
        "ocr_done": False,
        "ocr_at": None,
        "ocr_by": None,
        "text_extracted": False,
        "text_extracted_at": None,
        "text_extracted_by": None,
        "cleaned": False,
        "cleaned_at": None,
        "cleaned_by": None,
        "rag_ingested": False,
        "rag_ingested_at": None,
        "rag_ingested_by": None,
        "rag_status": None,
        "error_message": None,
    }


def _empty_record(*, path: Path) -> ProcessingStatusRecord:
    # ------------------------------------------------------------
    # 未作成時の record
    # ------------------------------------------------------------
    return _payload_to_record(
        exists=False,
        path=path,
        payload=_empty_payload(),
    )


def _payload_to_record(
    *,
    exists: bool,
    path: Path,
    payload: Dict[str, Any],
) -> ProcessingStatusRecord:
    # ------------------------------------------------------------
    # dict -> dataclass
    # ------------------------------------------------------------
    return ProcessingStatusRecord(
        exists=bool(exists),
        path=path,
        source_pdf_filename=_normalize_optional_str(payload.get("source_pdf_filename")),
        source_pdf_sha256=_normalize_optional_str(payload.get("source_pdf_sha256")),
        pdf_kind=_normalize_pdf_kind(payload.get("pdf_kind")),
        page_count=_normalize_optional_int(payload.get("page_count")),
        pdf_info_created_at=_normalize_optional_str(payload.get("pdf_info_created_at")),
        pdf_info_created_by=_normalize_optional_str(payload.get("pdf_info_created_by")),
        ocr_done=_normalize_bool(payload.get("ocr_done")),
        ocr_at=_normalize_optional_str(payload.get("ocr_at")),
        ocr_by=_normalize_optional_str(payload.get("ocr_by")),
        text_extracted=_normalize_bool(payload.get("text_extracted")),
        text_extracted_at=_normalize_optional_str(payload.get("text_extracted_at")),
        text_extracted_by=_normalize_optional_str(payload.get("text_extracted_by")),
        cleaned=_normalize_bool(payload.get("cleaned")),
        cleaned_at=_normalize_optional_str(payload.get("cleaned_at")),
        cleaned_by=_normalize_optional_str(payload.get("cleaned_by")),
        rag_ingested=_normalize_bool(payload.get("rag_ingested")),
        rag_ingested_at=_normalize_optional_str(payload.get("rag_ingested_at")),
        rag_ingested_by=_normalize_optional_str(payload.get("rag_ingested_by")),
        rag_status=_normalize_rag_status(payload.get("rag_status")),
        error_message=_normalize_optional_str(payload.get("error_message")),
    )


def _record_to_payload(rec: ProcessingStatusRecord) -> Dict[str, Any]:
    # ------------------------------------------------------------
    # dataclass -> dict
    # ------------------------------------------------------------
    return {
        "source_pdf_filename": rec.source_pdf_filename,
        "source_pdf_sha256": rec.source_pdf_sha256,
        "pdf_kind": rec.pdf_kind,
        "page_count": rec.page_count,
        "pdf_info_created_at": rec.pdf_info_created_at,
        "pdf_info_created_by": rec.pdf_info_created_by,
        "ocr_done": bool(rec.ocr_done),
        "ocr_at": rec.ocr_at,
        "ocr_by": rec.ocr_by,
        "text_extracted": bool(rec.text_extracted),
        "text_extracted_at": rec.text_extracted_at,
        "text_extracted_by": rec.text_extracted_by,
        "cleaned": bool(rec.cleaned),
        "cleaned_at": rec.cleaned_at,
        "cleaned_by": rec.cleaned_by,
        "rag_ingested": bool(rec.rag_ingested),
        "rag_ingested_at": rec.rag_ingested_at,
        "rag_ingested_by": rec.rag_ingested_by,
        "rag_status": rec.rag_status,
        "error_message": rec.error_message,
    }


# ============================================================
# helpers（record update）
# ============================================================
def _persist_record(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    record: ProcessingStatusRecord,
) -> Path:
    # ------------------------------------------------------------
    # record を保存
    # ------------------------------------------------------------
    path = get_processing_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )
    payload = _record_to_payload(record)
    _write_json_atomic(path, payload)
    return path


def _update_processing_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    **changes: Any,
) -> Path:
    # ------------------------------------------------------------
    # 差分更新の共通関数
    # - 既存recordを読む
    # - 指定された項目だけ置き換える
    # - exists は保存後 True 扱いにする
    # ------------------------------------------------------------
    rec = read_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    new_rec = replace(
        rec,
        exists=True,
        **changes,
    )

    return _persist_record(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        record=new_rec,
    )


# ============================================================
# public（read）
# ============================================================
def read_processing_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> ProcessingStatusRecord:
    # ------------------------------------------------------------
    # processing_status.json を読む
    # - 無ければ未処理として返す
    # - 壊れていれば例外
    # ------------------------------------------------------------
    path = get_processing_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    if not path.exists():
        return _empty_record(path=path)

    payload = _read_json(path)
    return _payload_to_record(
        exists=True,
        path=path,
        payload=payload,
    )


# ============================================================
# public（write / replace）
# ============================================================
def write_processing_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    record: ProcessingStatusRecord,
) -> Path:
    # ------------------------------------------------------------
    # record 全体を書き込む
    # ------------------------------------------------------------
    return _persist_record(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        record=record,
    )


def reset_processing_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> Path:
    # ------------------------------------------------------------
    # 初期状態で作り直す
    # ------------------------------------------------------------
    rec = _empty_record(
        path=get_processing_status_path(
            projects_root,
            project_year=project_year,
            project_no=project_no,
        )
    )

    return _persist_record(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        record=replace(rec, exists=True),
    )


def delete_processing_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> bool:
    # ------------------------------------------------------------
    # 削除（存在しなければ False）
    # ------------------------------------------------------------
    path = get_processing_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )
    if not path.exists():
        return False

    path.unlink()
    return True


# ============================================================
# public（upsert helpers）
# ============================================================
def upsert_pdf_info_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    source_pdf_filename: str,
    source_pdf_sha256: str,
    pdf_kind: str,
    page_count: int,
    done_by: str,
) -> Path:
    # ------------------------------------------------------------
    # PDF基本情報を記録
    # - 新しい source pdf を正本として記録
    # - OCR / text / cleaning / RAG はリセットする
    # ------------------------------------------------------------
    now_iso = _now_iso()

    return _update_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        source_pdf_filename=_normalize_optional_str(source_pdf_filename),
        source_pdf_sha256=_normalize_optional_str(source_pdf_sha256),
        pdf_kind=_normalize_pdf_kind(pdf_kind),
        page_count=int(page_count),
        pdf_info_created_at=now_iso,
        pdf_info_created_by=_normalize_optional_str(done_by),
        ocr_done=False,
        ocr_at=None,
        ocr_by=None,
        text_extracted=False,
        text_extracted_at=None,
        text_extracted_by=None,
        cleaned=False,
        cleaned_at=None,
        cleaned_by=None,
        rag_ingested=False,
        rag_ingested_at=None,
        rag_ingested_by=None,
        rag_status=RAG_STATUS_NOT_INGESTED,
        error_message=None,
    )


def mark_ocr_done(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
) -> Path:
    # ------------------------------------------------------------
    # OCR完了
    # ------------------------------------------------------------
    now_iso = _now_iso()

    return _update_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        ocr_done=True,
        ocr_at=now_iso,
        ocr_by=_normalize_optional_str(done_by),
        error_message=None,
    )


def mark_text_extracted(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
) -> Path:
    # ------------------------------------------------------------
    # text抽出完了
    # ------------------------------------------------------------
    now_iso = _now_iso()

    return _update_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        text_extracted=True,
        text_extracted_at=now_iso,
        text_extracted_by=_normalize_optional_str(done_by),
        error_message=None,
    )


def mark_cleaned(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
) -> Path:
    # ------------------------------------------------------------
    # cleaning完了
    # ------------------------------------------------------------
    now_iso = _now_iso()

    return _update_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        cleaned=True,
        cleaned_at=now_iso,
        cleaned_by=_normalize_optional_str(done_by),
        error_message=None,
    )


def mark_rag_ingested(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
) -> Path:
    # ------------------------------------------------------------
    # RAG取り込み完了
    # ------------------------------------------------------------
    now_iso = _now_iso()

    return _update_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        rag_ingested=True,
        rag_ingested_at=now_iso,
        rag_ingested_by=_normalize_optional_str(done_by),
        rag_status=RAG_STATUS_INGESTED,
        error_message=None,
    )


def mark_rag_failed(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    error_message: str,
) -> Path:
    # ------------------------------------------------------------
    # RAG取り込み失敗
    # ------------------------------------------------------------
    return _update_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        rag_ingested=False,
        rag_status=RAG_STATUS_FAILED,
        error_message=_normalize_optional_str(error_message),
    )


# ============================================================
# public（state / ui helpers）
# ============================================================
def get_processing_status_for_state(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> ProcessingStatusStateInfo:
    # ------------------------------------------------------------
    # state.py / UI 向け軽量情報
    # - rag_ingested=True なら text変更不可
    # ------------------------------------------------------------
    rec = read_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    return ProcessingStatusStateInfo(
        rag_status=rec.rag_status,
        rag_ingested_at=rec.rag_ingested_at,
        rag_ingested_by=rec.rag_ingested_by,
        can_edit_text=not bool(rec.rag_ingested),
    )


def is_rag_ingested(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> bool:
    # ------------------------------------------------------------
    # RAG取り込み済みか
    # ------------------------------------------------------------
    rec = read_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )
    return bool(rec.rag_ingested)


def matches_source_pdf(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    source_pdf_sha256: str,
) -> bool:
    # ------------------------------------------------------------
    # source pdf の sha256 一致判定
    # ------------------------------------------------------------
    rec = read_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )
    saved = _normalize_optional_str(rec.source_pdf_sha256)
    given = _normalize_optional_str(source_pdf_sha256)
    if saved is None or given is None:
        return False
    return saved == given