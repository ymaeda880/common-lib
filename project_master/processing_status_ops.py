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
# - RAG取り込み状態はこのファイルでは管理しない
# - RAG取込済み判定の正本は Databases/vectorstore/.../processed_files.json とする
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

TEXT_CHECK_KEY_PREFIX = "text_check_"

TEXT_CHECK_LEVEL_OK = "ok"
TEXT_CHECK_LEVEL_WARNING = "warning"
TEXT_CHECK_LEVEL_ERROR = "error"

PDF_KIND_TEXT = "text"
PDF_KIND_IMAGE = "image"

# ------------------------------------------------------------
# テキストチェック手動確認
#
# 自動判定結果は変更せず，
# RAG作成に支障がないと人が判断した事実を別に保持する
# ------------------------------------------------------------
TEXT_CHECK_MANUAL_OK_KEY = "text_check_manual_ok"
TEXT_CHECK_MANUAL_OK_AT_KEY = "text_check_manual_ok_at"
TEXT_CHECK_MANUAL_OK_BY_KEY = "text_check_manual_ok_by"
TEXT_CHECK_MANUAL_OK_REASON_KEY = "text_check_manual_ok_reason"
TEXT_CHECK_MANUAL_OK_SOURCE_KEY = "text_check_manual_ok_source"
TEXT_CHECK_MANUAL_OK_SOURCE_SHA256_KEY = (
    "text_check_manual_ok_source_sha256"
)

# ------------------------------------------------------------
# 報告書の手動スキップ
#
# 自動テキストチェック結果や手動OKは変更せず，
# 後続処理から除外する管理者判断を別に保持する
# ------------------------------------------------------------
TEXT_CHECK_MANUAL_SKIP_KEY = "text_check_manual_skip"
TEXT_CHECK_MANUAL_SKIP_AT_KEY = "text_check_manual_skip_at"
TEXT_CHECK_MANUAL_SKIP_BY_KEY = "text_check_manual_skip_by"
TEXT_CHECK_MANUAL_SKIP_REASON_KEY = "text_check_manual_skip_reason"

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
    # 失敗情報
    # ------------------------------------------------------------
    error_message: Optional[str]


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


def _normalize_page_numbers(
    value: Any,
) -> list[int]:
    # ------------------------------------------------------------
    # 問題ページ番号一覧を正規化する
    #
    # 機能：
    # - intへ変換できない値を除外する
    # - 0以下を除外する
    # - 重複を除外する
    # - 昇順に並べる
    # ------------------------------------------------------------
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        raw_values = [value]

    page_numbers: set[int] = set()

    for raw_value in raw_values:
        try:
            page_no = int(raw_value)
        except (TypeError, ValueError):
            continue

        if page_no >= 1:
            page_numbers.add(page_no)

    return sorted(page_numbers)


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


def _normalize_sha256(
    value: Any,
) -> Optional[str]:
    # ------------------------------------------------------------
    # SHA-256文字列を正規化する
    #
    # 機能：
    # - 前後空白を除去する
    # - 小文字へ統一する
    # - 64文字の16進文字列だけを受け付ける
    # ------------------------------------------------------------
    normalized = _normalize_optional_str(
        value
    )

    if normalized is None:
        return None

    normalized = normalized.lower()

    if len(normalized) != 64:
        return None

    if any(
        char not in "0123456789abcdef"
        for char in normalized
    ):
        return None

    return normalized



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
    # - 旧形式の rag_* キーは無視する
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


def read_text_check_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> Dict[str, Any]:
    # ------------------------------------------------------------
    # processing_status.jsonから
    # text_check_*項目だけを読み込む
    #
    # 方針：
    # - processing_status.jsonがなければ空dict
    # - 既存のProcessingStatusRecordは変更しない
    # - テキストチェック画面だけが使用する
    # ------------------------------------------------------------
    path = get_processing_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    if not path.exists():
        return {}

    payload = _read_json(path)

    return {
        str(key): value
        for key, value in payload.items()
        if str(key).startswith(TEXT_CHECK_KEY_PREFIX)
    }

def read_text_check_manual_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> Dict[str, Any]:
    # ------------------------------------------------------------
    # 手動確認・手動スキップに関する状態だけを読み込む
    #
    # 方針：
    # - processing_status.jsonがなければ空dict
    # - 自動テキストチェック結果は返さない
    # ------------------------------------------------------------
    text_check_status = read_text_check_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    manual_keys = {
        TEXT_CHECK_MANUAL_OK_KEY,
        TEXT_CHECK_MANUAL_OK_AT_KEY,
        TEXT_CHECK_MANUAL_OK_BY_KEY,
        TEXT_CHECK_MANUAL_OK_REASON_KEY,
        TEXT_CHECK_MANUAL_OK_SOURCE_KEY,
        TEXT_CHECK_MANUAL_OK_SOURCE_SHA256_KEY,
        TEXT_CHECK_MANUAL_SKIP_KEY,
        TEXT_CHECK_MANUAL_SKIP_AT_KEY,
        TEXT_CHECK_MANUAL_SKIP_BY_KEY,
        TEXT_CHECK_MANUAL_SKIP_REASON_KEY,
    }

    return {
        key: text_check_status[key]
        for key in manual_keys
        if key in text_check_status
    }



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
    # - OCR / text / cleaning はリセットする
    # - RAG状態はこのファイルでは管理しない
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


def mark_text_check_done(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
    source_file: str,
    check_level: str,
    problem_pages: list[int] | tuple[int, ...] = (),
    result_file: str | None = None,
    check_error_message: str | None = None,
) -> Path:
    # ------------------------------------------------------------
    # テキスト品質チェック結果を記録する
    #
    # 正常時：
    # - チェック済み情報だけを最小限保存する
    #
    # 問題あり：
    # - 問題ページ数
    # - 問題ページ番号
    # - 詳細結果ファイル
    #   を追加保存する
    #
    # 再チェック時：
    # - 過去のtext_check_*項目をいったん削除する
    # - 古い問題ページ情報を残さない
    # ------------------------------------------------------------
    path = get_processing_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    # ------------------------------------------------------------
    # 既存データを読み込む
    # ------------------------------------------------------------
    if path.exists():
        payload = _read_json(path)
    else:
        payload = _empty_payload()

    # ------------------------------------------------------------
    # 過去の自動テキストチェック項目を削除
    #
    # warning/errorからokになった場合に，
    # 古い問題ページ等を残さないため削除する。
    #
    # text_check_manual_* は手動確認結果なので，
    # 通常の再チェックでは削除せず保持する。
    # ------------------------------------------------------------
    old_text_check_keys = [
        key
        for key in payload
        if (
            str(key).startswith(
                TEXT_CHECK_KEY_PREFIX
            )
            and not str(key).startswith(
                "text_check_manual_"
            )
        )
    ]

    for key in old_text_check_keys:
        payload.pop(
            key,
            None,
        )

    # ------------------------------------------------------------
    # 判定レベルを正規化
    # ------------------------------------------------------------
    normalized_level = (
        _normalize_optional_str(check_level)
        or TEXT_CHECK_LEVEL_ERROR
    ).lower()

    if normalized_level not in {
        TEXT_CHECK_LEVEL_OK,
        TEXT_CHECK_LEVEL_WARNING,
        TEXT_CHECK_LEVEL_ERROR,
    }:
        raise ValueError(
            f"不正なtext check levelです: {check_level}"
        )

    normalized_problem_pages = _normalize_page_numbers(
        problem_pages
    )

    # ------------------------------------------------------------
    # 正常・異常に共通する最小項目
    # ------------------------------------------------------------
    payload.update(
        {
            "text_check_done": True,
            "text_check_at": _now_iso(),
            "text_check_by": _normalize_optional_str(
                done_by
            ),
            "text_check_source": _normalize_optional_str(
                source_file
            ),
            "text_check_level": normalized_level,
        }
    )

    # ------------------------------------------------------------
    # 問題がある場合だけ詳細項目を追加
    # ------------------------------------------------------------
    if normalized_level != TEXT_CHECK_LEVEL_OK:
        payload["text_check_problem_page_count"] = len(
            normalized_problem_pages
        )

        payload["text_check_problem_pages"] = (
            normalized_problem_pages
        )

        normalized_result_file = _normalize_optional_str(
            result_file
        )

        if normalized_result_file is not None:
            payload["text_check_result_file"] = (
                normalized_result_file
            )

        normalized_error_message = _normalize_optional_str(
            check_error_message
        )

        if normalized_error_message is not None:
            payload["text_check_error_message"] = (
                normalized_error_message
            )

    # ------------------------------------------------------------
    # atomic write
    # ------------------------------------------------------------
    _write_json_atomic(
        path,
        payload,
    )

    return path


def mark_text_check_manual_ok(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
    reason: str,
    source_file: str,
    source_sha256: str,
) -> Path:
    # ------------------------------------------------------------
    # テキストチェック結果を手動OKとして記録する
    #
    # 方針：
    # - 自動判定のtext_check_levelは変更しない
    # - RAG作成に支障がないと判断した事実だけを追加する
    # - 判断対象となったページJSONのSHA-256を保存する
    # - 選択報告書1件だけを対象とする
    # ------------------------------------------------------------
    path = get_processing_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    # ------------------------------------------------------------
    # テキストチェック済みであることを確認
    # ------------------------------------------------------------
    if not path.exists():
        raise RuntimeError(
            "processing_status.jsonが存在しません。"
            "先にテキストチェックを実行してください。"
        )

    payload = _read_json(
        path
    )

    text_check_done = _normalize_bool(
        payload.get(
            "text_check_done"
        )
    )

    if not text_check_done:
        raise RuntimeError(
            "テキストチェックが未実施です。"
            "先にテキストチェックを実行してください。"
        )

    # ------------------------------------------------------------
    # 自動テキストチェック結果を確認
    #
    # warning・errorのどちらであっても，
    # 最終的なRAG作成可否は管理者が手動で判断できる。
    # ------------------------------------------------------------
    check_level = (
        _normalize_optional_str(
            payload.get(
                "text_check_level"
            )
        )
        or ""
    ).lower()

    if check_level not in {
        TEXT_CHECK_LEVEL_OK,
        TEXT_CHECK_LEVEL_WARNING,
        TEXT_CHECK_LEVEL_ERROR,
    }:
        raise RuntimeError(
            "有効なテキストチェック結果がありません。"
            "先にテキストチェックを再実行してください。"
        )

    # ------------------------------------------------------------
    # 操作者を確認
    # ------------------------------------------------------------
    normalized_done_by = _normalize_optional_str(
        done_by
    )

    if normalized_done_by is None:
        raise ValueError(
            "手動確認者が指定されていません。"
        )

    # ------------------------------------------------------------
    # 判断理由を確認
    # ------------------------------------------------------------
    normalized_reason = _normalize_optional_str(
        reason
    )

    if normalized_reason is None:
        raise ValueError(
            "手動OKとする理由を入力してください。"
        )

    # ------------------------------------------------------------
    # 対象テキストJSONを確認
    # ------------------------------------------------------------
    normalized_source_file = _normalize_optional_str(
        source_file
    )

    if normalized_source_file is None:
        raise ValueError(
            "手動確認対象のテキストJSONが指定されていません。"
        )

    checked_source_file = _normalize_optional_str(
        payload.get(
            "text_check_source"
        )
    )

    if checked_source_file is None:
        raise RuntimeError(
            "テキストチェック対象ファイルが記録されていません。"
            "テキストチェックを再実行してください。"
        )

    if normalized_source_file != checked_source_file:
        raise RuntimeError(
            "現在の確認対象と，テキストチェック時の対象が"
            "一致していません。"
            "テキストチェックを再実行してください。"
        )

    # ------------------------------------------------------------
    # SHA-256を確認
    # ------------------------------------------------------------
    normalized_source_sha256 = _normalize_sha256(
        source_sha256
    )

    if normalized_source_sha256 is None:
        raise ValueError(
            "確認対象テキストJSONのSHA-256が不正です。"
        )

    # ------------------------------------------------------------
    # 手動OK情報だけを追加
    #
    # text_check_level等の自動判定情報は変更しない
    # ------------------------------------------------------------
    payload.update(
        {
            TEXT_CHECK_MANUAL_OK_KEY: True,
            TEXT_CHECK_MANUAL_OK_AT_KEY: _now_iso(),
            TEXT_CHECK_MANUAL_OK_BY_KEY: normalized_done_by,
            TEXT_CHECK_MANUAL_OK_REASON_KEY: normalized_reason,
            TEXT_CHECK_MANUAL_OK_SOURCE_KEY: normalized_source_file,
            TEXT_CHECK_MANUAL_OK_SOURCE_SHA256_KEY: (
                normalized_source_sha256
            ),
        }
    )

    _write_json_atomic(
        path,
        payload,
    )

    return path


def clear_text_check_manual_ok(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> Path:
    # ------------------------------------------------------------
    # 手動OK状態を解除する
    #
    # 方針：
    # - 自動テキストチェック結果は残す
    # - text_check_manual_*項目だけを削除する
    # - processing_status.jsonがない場合はエラーとする
    # ------------------------------------------------------------
    path = get_processing_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    if not path.exists():
        raise RuntimeError(
            "processing_status.jsonが存在しません。"
        )

    payload = _read_json(
        path
    )

    manual_keys = (
        TEXT_CHECK_MANUAL_OK_KEY,
        TEXT_CHECK_MANUAL_OK_AT_KEY,
        TEXT_CHECK_MANUAL_OK_BY_KEY,
        TEXT_CHECK_MANUAL_OK_REASON_KEY,
        TEXT_CHECK_MANUAL_OK_SOURCE_KEY,
        TEXT_CHECK_MANUAL_OK_SOURCE_SHA256_KEY,
    )

    for key in manual_keys:
        payload.pop(
            key,
            None,
        )

    _write_json_atomic(
        path,
        payload,
    )

    return path

def is_text_check_manual_ok_valid(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    source_file: str,
    source_sha256: str,
) -> bool:
    # ------------------------------------------------------------
    # 保存済みの手動OKが現在のテキストに対して有効か判定する
    #
    # 有効条件：
    # - text_check_manual_okがTrue
    # - 対象ファイル名が一致
    # - 対象ファイルのSHA-256が一致
    # - 自動チェック対象ファイルとも一致
    # ------------------------------------------------------------
    status = read_text_check_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    if not _normalize_bool(
        status.get(
            TEXT_CHECK_MANUAL_OK_KEY
        )
    ):
        return False

    saved_source_file = _normalize_optional_str(
        status.get(
            TEXT_CHECK_MANUAL_OK_SOURCE_KEY
        )
    )

    current_source_file = _normalize_optional_str(
        source_file
    )

    checked_source_file = _normalize_optional_str(
        status.get(
            "text_check_source"
        )
    )

    if (
        saved_source_file is None
        or current_source_file is None
        or checked_source_file is None
    ):
        return False

    if saved_source_file != current_source_file:
        return False

    if saved_source_file != checked_source_file:
        return False

    saved_sha256 = _normalize_sha256(
        status.get(
            TEXT_CHECK_MANUAL_OK_SOURCE_SHA256_KEY
        )
    )

    current_sha256 = _normalize_sha256(
        source_sha256
    )

    if saved_sha256 is None or current_sha256 is None:
        return False

    return saved_sha256 == current_sha256


# ============================================================
# public（報告書の手動スキップ）
# ============================================================
def mark_text_check_manual_skip(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
    reason: str,
) -> Path:
    # ------------------------------------------------------------
    # 報告書を手動スキップ対象として記録する
    #
    # 方針：
    # - 自動テキストチェック結果は変更しない
    # - 手動OK情報も変更しない
    # - ページJSONのSHA-256とは連動させない
    # - processing_status.jsonがなければ新規作成する
    # ------------------------------------------------------------
    normalized_done_by = _normalize_optional_str(done_by)

    if normalized_done_by is None:
        raise ValueError(
            "手動スキップの設定者が指定されていません。"
        )

    normalized_reason = _normalize_optional_str(reason)

    if normalized_reason is None:
        raise ValueError(
            "手動スキップとする理由を入力してください。"
        )

    path = get_processing_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    if path.exists():
        payload = _read_json(path)
    else:
        payload = _empty_payload()

    payload.update(
        {
            TEXT_CHECK_MANUAL_SKIP_KEY: True,
            TEXT_CHECK_MANUAL_SKIP_AT_KEY: _now_iso(),
            TEXT_CHECK_MANUAL_SKIP_BY_KEY: normalized_done_by,
            TEXT_CHECK_MANUAL_SKIP_REASON_KEY: normalized_reason,
        }
    )

    _write_json_atomic(
        path,
        payload,
    )

    return path


def clear_text_check_manual_skip(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> Path:
    # ------------------------------------------------------------
    # 報告書の手動スキップ状態を解除する
    #
    # 方針：
    # - 自動テキストチェック結果は残す
    # - 手動OK情報も残す
    # - 手動スキップ関係の項目だけを削除する
    # ------------------------------------------------------------
    path = get_processing_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    if not path.exists():
        raise RuntimeError(
            "processing_status.jsonが存在しません。"
        )

    payload = _read_json(path)

    manual_skip_keys = (
        TEXT_CHECK_MANUAL_SKIP_KEY,
        TEXT_CHECK_MANUAL_SKIP_AT_KEY,
        TEXT_CHECK_MANUAL_SKIP_BY_KEY,
        TEXT_CHECK_MANUAL_SKIP_REASON_KEY,
    )

    for key in manual_skip_keys:
        payload.pop(
            key,
            None,
        )

    _write_json_atomic(
        path,
        payload,
    )

    return path


def is_text_check_manual_skip(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> bool:
    # ------------------------------------------------------------
    # 報告書が手動スキップ対象か判定する
    #
    # processing_status.jsonが存在しない場合や，
    # キーが未設定の場合はFalseとする
    # ------------------------------------------------------------
    status = read_text_check_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    return _normalize_bool(
        status.get(
            TEXT_CHECK_MANUAL_SKIP_KEY,
            False,
        )
    )


# ============================================================
# public（compat helpers）
# ============================================================
def get_processing_status_for_state(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> ProcessingStatusRecord:
    # ------------------------------------------------------------
    # 互換用
    # - 旧来の state / UI 呼び出し用に record を返す
    # - RAG状態はこのファイルでは管理しないため参照不可
    # ------------------------------------------------------------
    return read_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )


def is_rag_ingested(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
) -> bool:
    # ------------------------------------------------------------
    # 互換用
    # - processing_status.json では RAG状態を管理しない
    # - 常に False を返す
    #
    # 注意：
    # - 新規コードでは使用禁止
    # - RAG取込済み判定は processed_files.json を正本とすること
    # ------------------------------------------------------------
    _ = read_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )
    return False


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