# -*- coding: utf-8 -*-
# common_lib/project_master/report_display_status_ops.py
# ============================================================
# Project Master: 報告書表示状態集約オペレーション（正本API）
#
# ■ 目的
# - 一覧表示・プレビュー表示に必要な報告書状態を集約して返す
# - page側に業務判定ロジックを散らさない
#
# ■ 集約対象
# - PDF・OCR・テキスト生成状態
# - raw / cleanテキストの存在状態
# - raw / cleanページJSONの存在状態
# - テキストチェック結果
# - 手動確認結果
# - 一覧表示用の最終判定
#
# ■ OK条件（報告書準備状態）
# - text PDF  + raw text あり + lock済み
# - image PDF + clean textあり + lock済み
#
# ■ テキストチェック最終判定
# - unchecked：テキストチェック未実施
# - ok：文字品質・図面等ともに問題なし
# - needs_review：文字品質または図面等に確認対象あり
# - manual_ok：現在のページJSONに対する手動確認済み
#
# ■ 重要方針
# - processing_status.jsonの読み書きは
#   processing_status_ops.pyを正本とする
# - 手動確認は対象ページJSONのSHA-256一致まで確認する
# - RAG取り込み状態は本モジュールでは扱わない
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any


# ============================================================
# project_master imports
# ============================================================
from common_lib.project_master.processing_status_ops import (
    TEXT_CHECK_ALLOW_SPECIAL_PAGES_KEY,
    TEXT_CHECK_LEVEL_ERROR,
    TEXT_CHECK_LEVEL_OK,
    TEXT_CHECK_LEVEL_WARNING,
    is_text_check_manual_ok_valid,
    is_text_check_manual_skip,
    read_processing_status,
    read_text_check_status,
)

from common_lib.project_master.report_text_ops import (
    exists_text_raw,
    exists_text_clean,
    get_text_raw_pages_json_path,
    get_text_clean_pages_json_path,
)


# ============================================================
# constants（テキストチェック最終判定）
# ============================================================
TEXT_CHECK_DISPLAY_UNCHECKED = "unchecked"
TEXT_CHECK_DISPLAY_OK = "ok"
TEXT_CHECK_DISPLAY_SPECIAL_OK = "special_ok"
TEXT_CHECK_DISPLAY_NEEDS_REVIEW = "needs_review"
TEXT_CHECK_DISPLAY_MANUAL_OK = "manual_ok"
TEXT_CHECK_DISPLAY_MANUAL_SKIP = "manual_skip"


# ============================================================
# dataclass（報告書準備状態）
# ============================================================
@dataclass(frozen=True)
class ReportDisplayStatus:
    # ------------------------------------------------------------
    # basic
    # ------------------------------------------------------------
    project_year: int
    project_no: str
    pdf_filename: str

    # ------------------------------------------------------------
    # status
    # ------------------------------------------------------------
    pdf_kind: str
    page_count: int | None
    page_count_display: str
    ocr_done: bool

    lock_flag: int

    raw_exists: bool
    clean_exists: bool

    # ------------------------------------------------------------
    # business status
    # ------------------------------------------------------------
    ok_ready: bool


# ============================================================
# dataclass（テキストチェック表示状態）
# ============================================================
@dataclass(frozen=True)
class ReportTextCheckDisplayStatus:
    # ------------------------------------------------------------
    # basic
    # ------------------------------------------------------------
    project_year: int
    project_no: str
    pdf_filename: str

    # ------------------------------------------------------------
    # ページJSON状態
    # ------------------------------------------------------------
    raw_pages_json_exists: bool
    clean_pages_json_exists: bool

    source_file: str
    source_sha256: str

    # ------------------------------------------------------------
    # 自動テキストチェック
    # ------------------------------------------------------------
    text_check_done: bool
    text_check_level: str
    problem_page_count: int
    allow_special_pages: bool

    # ------------------------------------------------------------
    # 図面等
    #
    # text_check_result.jsonから取得した値を呼出側から渡す
    # ------------------------------------------------------------
    special_page_count: int

    # ------------------------------------------------------------
    # 手動確認
    # ------------------------------------------------------------
    manual_ok_valid: bool

    # ------------------------------------------------------------
    # 手動スキップ
    # ------------------------------------------------------------
    manual_skip: bool
    manual_skip_at: str
    manual_skip_by: str
    manual_skip_reason: str

    # ------------------------------------------------------------
    # 最終表示状態
    # ------------------------------------------------------------
    final_status: str
    final_icon: str
    final_label: str

    has_problem: bool


# ============================================================
# internal helpers（共通）
# ============================================================
def _normalize_bool(
    value: Any,
) -> bool:
    # ------------------------------------------------------------
    # bool値を安全に正規化する
    # ------------------------------------------------------------
    if isinstance(
        value,
        bool,
    ):
        return value

    return str(
        value
        or ""
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _normalize_non_negative_int(
    value: Any,
) -> int:
    # ------------------------------------------------------------
    # 0以上の整数へ正規化する
    # ------------------------------------------------------------
    try:
        return max(
            int(
                value
                or 0
            ),
            0,
        )

    except (
        TypeError,
        ValueError,
    ):
        return 0


def _sha256_of_file(
    path: Path | None,
) -> str:
    # ------------------------------------------------------------
    # ファイルのSHA-256を返す
    #
    # 一覧表示時に巨大なPDFは読まず，
    # 小さいページJSONだけを対象とする
    # ------------------------------------------------------------
    if path is None:
        return ""

    if not path.exists():
        return ""

    if not path.is_file():
        return ""

    try:
        digest = hashlib.sha256()

        with path.open(
            "rb"
        ) as file_obj:
            for chunk in iter(
                lambda: file_obj.read(
                    1024 * 1024
                ),
                b"",
            ):
                digest.update(
                    chunk
                )

        return digest.hexdigest()

    except Exception:
        return ""


def _select_text_check_source(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str,
) -> tuple[
    bool,
    bool,
    str,
    str,
]:
    # ------------------------------------------------------------
    # テキストチェック対象となるページJSONを決定する
    #
    # 優先順位：
    # 1. report_clean_pages.json
    # 2. report_raw_pages.json
    # ------------------------------------------------------------
    raw_path = get_text_raw_pages_json_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    clean_path = get_text_clean_pages_json_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    raw_exists = bool(
        raw_path
        and raw_path.exists()
        and raw_path.is_file()
    )

    clean_exists = bool(
        clean_path
        and clean_path.exists()
        and clean_path.is_file()
    )

    if clean_exists:
        return (
            raw_exists,
            clean_exists,
            clean_path.name,
            _sha256_of_file(
                clean_path
            ),
        )

    if raw_exists:
        return (
            raw_exists,
            clean_exists,
            raw_path.name,
            _sha256_of_file(
                raw_path
            ),
        )

    return (
        raw_exists,
        clean_exists,
        "",
        "",
    )


# ============================================================
# internal helpers（報告書準備状態）
# ============================================================
def _pdf_kind_label_from_record(
    rec: Any,
) -> str:
    # ------------------------------------------------------------
    # pdf_kind 表示用
    # ------------------------------------------------------------
    value = str(
        getattr(
            rec,
            "pdf_kind",
            "",
        )
        or ""
    ).strip().lower()

    if value in {
        "text",
        "image",
    }:
        return value

    return "未判定"


def _page_count_value_from_record(
    rec: Any,
) -> int | None:
    # ------------------------------------------------------------
    # page_count 値
    # ------------------------------------------------------------
    page_count = getattr(
        rec,
        "page_count",
        None,
    )

    try:
        page_count_int = int(
            page_count
        )

        if page_count_int > 0:
            return page_count_int

    except (
        TypeError,
        ValueError,
    ):
        pass

    return None


def _page_count_display_from_record(
    rec: Any,
) -> str:
    # ------------------------------------------------------------
    # page_count 表示用
    # ------------------------------------------------------------
    page_count = (
        _page_count_value_from_record(
            rec
        )
    )

    if page_count is None:
        return "未計算"

    return f"{page_count}p"


def _is_ocr_done_from_record(
    rec: Any,
) -> bool:
    # ------------------------------------------------------------
    # OCR済み判定
    # ------------------------------------------------------------
    return bool(
        getattr(
            rec,
            "ocr_done",
            False,
        )
    )


def _is_ok_ready(
    *,
    pdf_kind: str,
    lock_flag: int,
    raw_exists: bool,
    clean_exists: bool,
) -> bool:
    # ------------------------------------------------------------
    # OK条件（正本）
    # ------------------------------------------------------------
    return bool(
        lock_flag == 1
        and (
            (
                pdf_kind == "text"
                and raw_exists
            )
            or (
                pdf_kind == "image"
                and clean_exists
            )
        )
    )


# ============================================================
# internal helpers（テキストチェック最終判定）
# ============================================================
def _build_text_check_final_status(
    *,
    text_check_done: bool,
    text_check_level: str,
    problem_page_count: int,
    special_page_count: int,
    allow_special_pages: bool,
    manual_ok_valid: bool,
    manual_skip: bool,
) -> tuple[
    str,
    str,
    str,
    bool,
]:
    # ------------------------------------------------------------
    # 一覧表示用の最終判定を返す
    #
    # 優先順位：
    # 1. 手動スキップ
    # 2. 未チェック
    # 3. 手動確認済み
    # 4. 文字品質の要確認
    # 5. 図面等あり・自動取込許可
    # 6. 図面等あり・自動取込不許可
    # 7. 正常
    # ------------------------------------------------------------
    if manual_skip:
        return (
            TEXT_CHECK_DISPLAY_MANUAL_SKIP,
            "⛔",
            "手動スキップ",
            False,
        )

    if not text_check_done:
        return (
            TEXT_CHECK_DISPLAY_UNCHECKED,
            "⬜",
            "未チェック",
            False,
        )

    if manual_ok_valid:
        return (
            TEXT_CHECK_DISPLAY_MANUAL_OK,
            "🟡",
            "手動確認済み",
            False,
        )

    text_has_problem = bool(
        text_check_level in {
            TEXT_CHECK_LEVEL_WARNING,
            TEXT_CHECK_LEVEL_ERROR,
        }
        or problem_page_count > 0
    )

    if text_has_problem:
        return (
            TEXT_CHECK_DISPLAY_NEEDS_REVIEW,
            "❌",
            "要確認",
            True,
        )

    if special_page_count > 0 and allow_special_pages:
        return (
            TEXT_CHECK_DISPLAY_SPECIAL_OK,
            "🟢",
            "図面等あり（取込OK）",
            False,
        )

    if special_page_count > 0:
        return (
            TEXT_CHECK_DISPLAY_NEEDS_REVIEW,
            "❌",
            "要確認",
            True,
        )

    return (
        TEXT_CHECK_DISPLAY_OK,
        "✅",
        "正常",
        False,
    )

# ============================================================
# public api（報告書準備状態）
# ============================================================
def build_report_display_status(
    projects_root: Path,
    item: Any,
    role: str = "main",
) -> ReportDisplayStatus:
    # ------------------------------------------------------------
    # 1件分の報告書表示状態を集約して返す
    # ------------------------------------------------------------
    project_year = int(
        getattr(
            item,
            "project_year",
        )
    )

    project_no = str(
        getattr(
            item,
            "project_no",
        )
    )

    pdf_filename = str(
        getattr(
            item,
            "pdf_filename",
            "",
        )
        or ""
    )

    lock_flag = int(
        getattr(
            item,
            "pdf_lock_flag",
            0,
        )
        or 0
    )

    rec = read_processing_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    pdf_kind = _pdf_kind_label_from_record(
        rec
    )

    page_count = _page_count_value_from_record(
        rec
    )

    page_count_display = (
        _page_count_display_from_record(
            rec
        )
    )

    ocr_done = _is_ocr_done_from_record(
        rec
    )

    raw_exists = exists_text_raw(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    clean_exists = exists_text_clean(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    ok_ready = _is_ok_ready(
        pdf_kind=pdf_kind,
        lock_flag=lock_flag,
        raw_exists=raw_exists,
        clean_exists=clean_exists,
    )

    return ReportDisplayStatus(
        project_year=project_year,
        project_no=project_no,
        pdf_filename=pdf_filename,
        pdf_kind=pdf_kind,
        page_count=page_count,
        page_count_display=page_count_display,
        ocr_done=ocr_done,
        lock_flag=lock_flag,
        raw_exists=raw_exists,
        clean_exists=clean_exists,
        ok_ready=ok_ready,
    )


# ============================================================
# public api（テキストチェック表示状態）
# ============================================================
def build_report_text_check_display_status(
    projects_root: Path,
    item: Any,
    *,
    special_page_count: int = 0,
    role: str = "main",
) -> ReportTextCheckDisplayStatus:
    # ------------------------------------------------------------
    # テキストチェック一覧に必要な状態を集約して返す
    #
    # processing_status.jsonの解釈と，
    # 手動確認の有効性判定を本関数へ集約する
    # ------------------------------------------------------------
    project_year = int(
        getattr(
            item,
            "project_year",
        )
    )

    project_no = str(
        getattr(
            item,
            "project_no",
        )
    )

    pdf_filename = str(
        getattr(
            item,
            "pdf_filename",
            "",
        )
        or ""
    )

    status = read_text_check_status(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    manual_skip = False

    try:
        manual_skip = is_text_check_manual_skip(
            projects_root,
            project_year=project_year,
            project_no=project_no,
        )
    except Exception:
        manual_skip = False

    manual_skip_at = str(
        status.get(
            "text_check_manual_skip_at",
            "",
        )
        or ""
    ).strip()

    manual_skip_by = str(
        status.get(
            "text_check_manual_skip_by",
            "",
        )
        or ""
    ).strip()

    manual_skip_reason = str(
        status.get(
            "text_check_manual_skip_reason",
            "",
        )
        or ""
    ).strip()


    text_check_done = _normalize_bool(
        status.get(
            "text_check_done",
            False,
        )
    )

    text_check_level = str(
        status.get(
            "text_check_level",
            "",
        )
        or ""
    ).strip().lower()

    problem_page_count = (
        _normalize_non_negative_int(
            status.get(
                "text_check_problem_page_count",
                0,
            )
        )
    )


    allow_special_pages = _normalize_bool(
        status.get(
            TEXT_CHECK_ALLOW_SPECIAL_PAGES_KEY,
            False,
        )
    )


    special_page_count = (
        _normalize_non_negative_int(
            special_page_count
        )
    )

    (
        raw_pages_json_exists,
        clean_pages_json_exists,
        source_file,
        source_sha256,
    ) = _select_text_check_source(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    manual_ok_valid = False

    if (
        text_check_done
        and source_file
        and source_sha256
    ):
        try:
            manual_ok_valid = (
                is_text_check_manual_ok_valid(
                    projects_root,
                    project_year=project_year,
                    project_no=project_no,
                    source_file=source_file,
                    source_sha256=source_sha256,
                )
            )

        except Exception:
            manual_ok_valid = False

    (
        final_status,
        final_icon,
        final_label,
        has_problem,
    ) = _build_text_check_final_status(
        text_check_done=text_check_done,
        text_check_level=text_check_level,
        problem_page_count=problem_page_count,
        special_page_count=special_page_count,
        allow_special_pages=allow_special_pages,
        manual_ok_valid=manual_ok_valid,
        manual_skip=manual_skip,
    )

    return ReportTextCheckDisplayStatus(
        project_year=project_year,
        project_no=project_no,
        pdf_filename=pdf_filename,
        raw_pages_json_exists=(
            raw_pages_json_exists
        ),
        clean_pages_json_exists=(
            clean_pages_json_exists
        ),
        source_file=source_file,
        source_sha256=source_sha256,
        text_check_done=text_check_done,
        text_check_level=text_check_level,
   
        problem_page_count=(
            problem_page_count
        ),
        allow_special_pages=(
            allow_special_pages
        ),
        special_page_count=(
            special_page_count
        ),
        manual_ok_valid=(
            manual_ok_valid
        ),
        
        manual_skip=manual_skip,
        manual_skip_at=manual_skip_at,
        manual_skip_by=manual_skip_by,
        manual_skip_reason=manual_skip_reason,

        final_status=final_status,
        final_icon=final_icon,
        final_label=final_label,
        has_problem=has_problem,
    )