# -*- coding: utf-8 -*-
# common_lib/project_master/page_processing_history.py
# ============================================================
# PDFページ処理履歴 共通取得
#
# 機能：
# - report_pages.json / contract_pages.json のページ状態を取得する
# - OCRハルシネーション履歴を取得する
# - 異常文字置換履歴を取得する
# - 異常文字OCR・本文削除履歴を取得する
# ============================================================

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ============================================================
# helpers
# ============================================================
def _read_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("records", "entries", "history", "logs", "events"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]

    return [payload] if payload else []


def _page_no(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _record_time(row: dict[str, Any]) -> str:
    for key in (
        "processed_at",
        "done_at",
        "detected_at",
        "created_at",
        "timestamp",
        "ocr_at",
    ):
        value = str(row.get(key, "") or "").strip()
        if value:
            return value

    return ""


def _record_user(row: dict[str, Any]) -> str:
    for key in (
        "processed_by",
        "done_by",
        "detected_by",
        "ocr_by",
    ):
        value = str(row.get(key, "") or "").strip()
        if value:
            return value

    return ""


def _get_page_row(
    pages_payload: Any,
    *,
    page_no: int,
) -> dict[str, Any]:
    if not isinstance(pages_payload, dict):
        return {}

    pages = pages_payload.get("pages", [])
    if not isinstance(pages, list):
        return {}

    for row in pages:
        if not isinstance(row, dict):
            continue

        if _page_no(row.get("page_no")) == int(page_no):
            return row

    return {}


# ============================================================
# hallucination
# ============================================================
def _load_hallucination_history(
    log_path: Path,
    *,
    page_no: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for row in _records(_read_json(log_path)):
        if _page_no(row.get("page_no")) != int(page_no):
            continue

        result.append({
            "time": _record_time(row),
            "user": _record_user(row),
            "action": str(row.get("action", "") or ""),
            "review_status": str(row.get("review_status", "") or ""),
            "method": str(row.get("method", "") or ""),
            "model": str(row.get("model", "") or ""),
            "reason": str(row.get("reason", "") or ""),
            "content_dark_pixels": int(row.get("content_dark_pixels", 0) or 0),
            "ocr_char_count": int(row.get("ocr_char_count", 0) or 0),
        })

    return result


# ============================================================
# abnormal char replacement
# ============================================================
def _load_abnormal_char_history(
    log_path: Path,
    *,
    page_no: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for record in _records(_read_json(log_path)):
        pages = record.get("pages", [])

        if isinstance(pages, list):
            for page in pages:
                if not isinstance(page, dict):
                    continue

                if _page_no(page.get("page_no")) != int(page_no):
                    continue

                result.append({
                    "time": _record_time(record),
                    "user": _record_user(record),
                    "replacement_count": int(
                        page.get("replacement_count", 0) or 0
                    ),
                    "replacements": list(
                        page.get("replacements", []) or []
                    ),
                })

            continue

        # 旧契約書ログ用
        replacement_pages = record.get("replacement_pages", [])
        if (
            isinstance(replacement_pages, list)
            and int(page_no) in {
                _page_no(value) for value in replacement_pages
            }
        ):
            result.append({
                "time": _record_time(record),
                "user": _record_user(record),
                "replacement_count": 0,
                "replacements": [],
            })

    return result


# ============================================================
# abnormal text OCR
# ============================================================
def _load_abnormal_text_history(
    log_path: Path,
    *,
    page_no: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for row in _records(_read_json(log_path)):
        if _page_no(row.get("page_no")) != int(page_no):
            continue

        result.append({
            "time": _record_time(row),
            "user": _record_user(row),
            "action": str(row.get("action", "") or ""),
            "model": str(row.get("model", "") or ""),
        })

    return result


# ============================================================
# public API
# ============================================================
def load_page_processing_history(
    pages_path: Path,
    *,
    target_kind: str,
    page_no: int,
) -> dict[str, Any]:
    pages_path = Path(pages_path)
    target_kind = str(target_kind or "").strip().lower()

    if target_kind not in {"report", "contract"}:
        raise ValueError(
            "target_kind は report または contract を指定してください．"
        )

    parent = pages_path.parent
    page_row = _get_page_row(
        _read_json(pages_path),
        page_no=int(page_no),
    )

    abnormal_text_filename = (
        "abnormal_text_processing_history.json"
        if target_kind == "report"
        else "contract_abnormal_text_processing_history.json"
    )

    abnormal_char_filename = (
        "abnormal_char_replacement.json"
        if target_kind == "report"
        else "contract_abnormal_char_replacement.json"
    )

    return {
        "target_kind": target_kind,
        "page_no": int(page_no),
        "page_kind": str(page_row.get("page_kind", "") or ""),
        "blank_page": bool(page_row.get("blank_page", False)),
        "ocr_done": bool(page_row.get("ocr_done", False)),
        "ocr_method": str(page_row.get("ocr_method", "") or ""),
        "ocr_at": str(page_row.get("ocr_at", "") or ""),
        "ocr_by": str(page_row.get("ocr_by", "") or ""),
        "hallucination": _load_hallucination_history(
            parent / "ocr_hallucination_log.json",
            page_no=int(page_no),
        ),
        "abnormal_char_replacement": _load_abnormal_char_history(
            parent / abnormal_char_filename,
            page_no=int(page_no),
        ),
        "abnormal_text_processing": _load_abnormal_text_history(
            parent / abnormal_text_filename,
            page_no=int(page_no),
        ),
    }