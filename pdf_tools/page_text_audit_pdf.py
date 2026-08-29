# -*- coding: utf-8 -*-
# common_lib/pdf_tools/page_text_audit_pdf.py
# ============================================================
# PDFテキスト確認資料 生成
#
# 機能：
# - 元PDFページを画質を落とさずそのまま複製する
# - 各PDFページの直後に抽出テキスト・処理履歴を出力する
# - 抽出テキストが長い場合は確認情報ページを自動的に分割する
# ============================================================

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import textwrap
from typing import Any, Callable

import fitz

from common_lib.project_master.page_processing_history import (
    load_page_processing_history,
)


# ============================================================
# constants
# ============================================================
A4_RECT = fitz.paper_rect("a4")
MARGIN_X = 36
MARGIN_TOP = 42
MARGIN_BOTTOM = 36

FONT_NAME = "japan"
TITLE_SIZE = 16
SUBTITLE_SIZE = 11
BODY_SIZE = 8.5
LINE_HEIGHT = 12

BODY_CHARS_PER_LINE = 62
BODY_LINES_PER_PAGE = 58


# ============================================================
# JSON
# ============================================================
def _load_pages(
    pages_path: Path,
) -> dict[int, dict[str, Any]]:
    payload = json.loads(
        Path(pages_path).read_text(encoding="utf-8")
    )

    pages = payload.get("pages", [])
    if not isinstance(pages, list):
        raise ValueError(
            f"{pages_path.name} の pages がlistではありません．"
        )

    result: dict[int, dict[str, Any]] = {}

    for index, row in enumerate(pages, start=1):
        if not isinstance(row, dict):
            continue

        try:
            page_no = int(row.get("page_no", index) or index)
        except (TypeError, ValueError):
            page_no = index

        result[page_no] = row

    return result


# ============================================================
# text helpers
# ============================================================
def _display(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "-"


def _wrap_line(
    text: str,
    *,
    width: int = BODY_CHARS_PER_LINE,
) -> list[str]:
    text = str(text or "").replace("\t", "    ")

    if not text:
        return [""]

    return textwrap.wrap(
        text,
        width=max(10, int(width)),
        replace_whitespace=False,
        drop_whitespace=False,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]


def _wrap_text(
    text: str,
) -> list[str]:
    output: list[str] = []

    for line in str(text or "").splitlines():
        output.extend(_wrap_line(line))

    if not output:
        output.append("")

    return output


def _replacement_lines(
    replacements: list[Any],
) -> list[str]:
    lines: list[str] = []

    for replacement in replacements:
        if not isinstance(replacement, dict):
            continue

        target = str(replacement.get("target", "") or "")
        source_counts = replacement.get("source_counts")

        if isinstance(source_counts, dict):
            for source, count in source_counts.items():
                lines.append(
                    f"    「{source}」→「{target}」 "
                    f"{int(count or 0):,}文字"
                )
            continue

        source = str(replacement.get("source", "") or "")
        count = int(replacement.get("count", 0) or 0)

        if source:
            lines.append(
                f"    「{source}」→「{target}」 {count:,}文字"
            )

    return lines


# ============================================================
# history
# ============================================================
def _build_history_lines(
    history: dict[str, Any],
) -> list[str]:
    page_kind = str(history.get("page_kind", "") or "").lower()
    page_kind_label = {
        "text": "text（テキストPDF）",
        "image": "image（画像PDF）",
        "mixed": "mixed（混在）",
    }.get(page_kind, _display(page_kind))

    blank_page = bool(history.get("blank_page", False))
    ocr_done = bool(history.get("ocr_done", False))
    ocr_method = str(history.get("ocr_method", "") or "")

    if blank_page:
        ocr_status = "白紙認定のためスキップ"
    elif ocr_done:
        ocr_status = "実施"
    else:
        ocr_status = "未実施"

    lines = [
        "【ページ情報】",
        f"ページ種別：{page_kind_label}",
        f"白紙認定：{'あり' if blank_page else 'なし'}",
        f"通常OCR：{ocr_status}",
        f"OCR方式：{_display(ocr_method)}",
    ]

    if history.get("ocr_at") or history.get("ocr_by"):
        lines.append(
            "OCR情報："
            f"{_display(history.get('ocr_at'))} ／ "
            f"実行者={_display(history.get('ocr_by'))}"
        )

    hallucination = list(
        history.get("hallucination", []) or []
    )

    lines.extend([
        "",
        "【OCRハルシネーション履歴】",
    ])

    if not hallucination:
        lines.append("なし")
    else:
        for row in hallucination:
            if not isinstance(row, dict):
                continue

            status = (
                row.get("review_status")
                or row.get("action")
                or "suspected"
            )

            lines.append(
                f"{_display(row.get('time'))} ／ "
                f"{status} ／ "
                f"model={_display(row.get('model'))}"
            )

            reason = str(row.get("reason", "") or "").strip()
            if reason:
                lines.extend(
                    f"  {line}"
                    for line in _wrap_line(reason, width=58)
                )

    replacement_history = list(
        history.get("abnormal_char_replacement", []) or []
    )

    lines.extend([
        "",
        "【異常文字置換履歴】",
    ])

    if not replacement_history:
        lines.append("なし")
    else:
        for row in replacement_history:
            if not isinstance(row, dict):
                continue

            lines.append(
                f"{_display(row.get('time'))} ／ "
                f"{int(row.get('replacement_count', 0) or 0):,}文字 ／ "
                f"実行者={_display(row.get('user'))}"
            )

            lines.extend(
                _replacement_lines(
                    list(row.get("replacements", []) or [])
                )
            )

    abnormal_text_history = list(
        history.get("abnormal_text_processing", []) or []
    )

    lines.extend([
        "",
        "【異常文字OCR・本文処理履歴】",
    ])

    if not abnormal_text_history:
        lines.append("なし")
    else:
        for row in abnormal_text_history:
            if not isinstance(row, dict):
                continue

            lines.append(
                f"{_display(row.get('time'))} ／ "
                f"{_display(row.get('action'))} ／ "
                f"model={_display(row.get('model'))} ／ "
                f"実行者={_display(row.get('user'))}"
            )

    return lines


# ============================================================
# PDF text draw
# ============================================================
def _insert_line(
    page: fitz.Page,
    *,
    text: str,
    x: float,
    y: float,
    fontsize: float,
) -> None:
    page.insert_text(
        fitz.Point(float(x), float(y)),
        str(text or ""),
        fontname=FONT_NAME,
        fontsize=float(fontsize),
    )


def _draw_audit_page(
    out_doc: fitz.Document,
    *,
    pdf_page_no: int,
    lines: list[str],
    part_no: int,
    part_count: int,
) -> None:
    page = out_doc.new_page(
        width=A4_RECT.width,
        height=A4_RECT.height,
    )

    y = MARGIN_TOP

    _insert_line(
        page,
        text=f"PDF Page {pdf_page_no} - 抽出テキスト・処理履歴",
        x=MARGIN_X,
        y=y,
        fontsize=TITLE_SIZE,
    )

    y += 22

    _insert_line(
        page,
        text=f"確認情報 {part_no} / {part_count}",
        x=MARGIN_X,
        y=y,
        fontsize=SUBTITLE_SIZE,
    )

    y += 22

    for line in lines:
        if y > A4_RECT.height - MARGIN_BOTTOM:
            break

        _insert_line(
            page,
            text=line,
            x=MARGIN_X,
            y=y,
            fontsize=BODY_SIZE,
        )

        y += LINE_HEIGHT


# ============================================================
# cover
# ============================================================
def _draw_cover(
    out_doc: fitz.Document,
    *,
    target_kind: str,
    project_year: int,
    project_no: str,
    pdf_filename: str,
    total_pages: int,
    histories: dict[int, dict[str, Any]],
) -> None:
    page = out_doc.new_page(
        width=A4_RECT.width,
        height=A4_RECT.height,
    )

    text_pages = sum(
        1
        for history in histories.values()
        if str(history.get("page_kind", "") or "").lower() == "text"
    )

    image_pages = sum(
        1
        for history in histories.values()
        if str(history.get("page_kind", "") or "").lower() == "image"
    )

    blank_pages = sum(
        1
        for history in histories.values()
        if bool(history.get("blank_page", False))
    )

    ocr_pages = sum(
        1
        for history in histories.values()
        if (
            bool(history.get("ocr_done", False))
            and not bool(history.get("blank_page", False))
        )
    )

    hallucination_pages = sum(
        1
        for history in histories.values()
        if history.get("hallucination")
    )

    replacement_pages = sum(
        1
        for history in histories.values()
        if history.get("abnormal_char_replacement")
    )

    abnormal_ocr_pages = sum(
        1
        for history in histories.values()
        if history.get("abnormal_text_processing")
    )

    target_label = (
        "報告書PDF"
        if str(target_kind).lower() == "report"
        else "契約書PDF"
    )

    lines = [
        "PDFテキスト確認資料",
        "",
        f"対象：{target_label}",
        f"年度：{int(project_year)}",
        f"プロジェクト番号：{project_no}",
        f"PDF：{pdf_filename}",
        f"総ページ数：{int(total_pages):,}",
        "",
        "【ページ集計】",
        f"テキストPDFページ：{text_pages:,}",
        f"画像PDFページ：{image_pages:,}",
        f"白紙認定ページ：{blank_pages:,}",
        f"OCR実施ページ：{ocr_pages:,}",
        f"ハルシネーション履歴あり：{hallucination_pages:,}",
        f"異常文字置換履歴あり：{replacement_pages:,}",
        f"異常文字OCR・本文処理履歴あり：{abnormal_ocr_pages:,}",
        "",
        "この資料は，元PDFと抽出テキスト，",
        "OCR・異常文字処理等の履歴をページ単位で",
        "照合するための管理者用確認資料です．",
        "",
        f"出力日時：{datetime.now().astimezone().isoformat(timespec='seconds')}",
    ]

    y = 70

    for index, line in enumerate(lines):
        if index == 0:
            fontsize = 20
        elif line.startswith("【"):
            fontsize = 12
        else:
            fontsize = 10

        _insert_line(
            page,
            text=line,
            x=50,
            y=y,
            fontsize=fontsize,
        )

        y += 25 if index == 0 else 18


# ============================================================
# public API
# ============================================================
def build_page_text_audit_pdf(
    *,
    pdf_path: Path,
    pages_path: Path,
    target_kind: str,
    project_year: int,
    project_no: str,
    pdf_filename: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> bytes:
    pdf_path = Path(pdf_path)
    pages_path = Path(pages_path)
    target_kind = str(target_kind or "").strip().lower()

    if target_kind not in {"report", "contract"}:
        raise ValueError(
            "target_kind は report または contract を指定してください．"
        )

    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(
            f"元PDFが存在しません：{pdf_path}"
        )

    if not pages_path.exists() or not pages_path.is_file():
        raise FileNotFoundError(
            f"ページJSONが存在しません：{pages_path}"
        )

    page_rows = _load_pages(pages_path)

    src_doc = fitz.open(pdf_path)
    out_doc = fitz.open()

    try:
        if src_doc.is_encrypted:
            raise RuntimeError(
                "暗号化されたPDFは確認資料を作成できません．"
            )

        total_pages = int(src_doc.page_count)

        if total_pages <= 0:
            raise RuntimeError(
                "元PDFのページ数を取得できません．"
            )

        histories: dict[int, dict[str, Any]] = {}

        for page_no in range(1, total_pages + 1):
            if progress_callback is not None:
                progress_callback(
                    page_no,
                    total_pages,
                    f"PDF Page {page_no}：処理履歴を読み込み中",
                )

            histories[page_no] = load_page_processing_history(
                pages_path,
                target_kind=target_kind,
                page_no=page_no,
            )

        _draw_cover(
            out_doc,
            target_kind=target_kind,
            project_year=int(project_year),
            project_no=str(project_no),
            pdf_filename=str(pdf_filename),
            total_pages=total_pages,
            histories=histories,
        )

        for page_no in range(1, total_pages + 1):
            if progress_callback is not None:
                progress_callback(
                    page_no,
                    total_pages,
                    f"PDF Page {page_no}：元PDFページを追加中",
                )

            page_index = page_no - 1
            src_page = src_doc.load_page(page_index)

            # --------------------------------------------------------
            # 元PDFページ
            # --------------------------------------------------------
            header_height = 36

            original_page = out_doc.new_page(
                width=src_page.rect.width,
                height=src_page.rect.height + header_height,
            )

            _insert_line(
                original_page,
                text=f"元PDF　PDF Page {page_no}",
                x=20,
                y=24,
                fontsize=11,
            )

            pdf_rect = fitz.Rect(
                0,
                header_height,
                src_page.rect.width,
                src_page.rect.height + header_height,
            )

            original_page.show_pdf_page(
                pdf_rect,
                src_doc,
                page_index,
            )

            # --------------------------------------------------------
            # 確認情報
            # --------------------------------------------------------
            if progress_callback is not None:
                progress_callback(
                    page_no,
                    total_pages,
                    f"PDF Page {page_no}：抽出テキスト・処理履歴を追加中",
                )

            page_row = page_rows.get(page_no, {})
            page_text = str(page_row.get("text", "") or "")

            body_lines = [
                "【抽出テキスト】",
                "",
            ]

            if page_text:
                body_lines.extend(_wrap_text(page_text))
            else:
                body_lines.append("テキストなし")

            body_lines.extend([
                "",
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "ここから処理履歴",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ])

            body_lines.extend(
                _build_history_lines(
                    histories[page_no]
                )
            )

            chunks = [
                body_lines[index:index + BODY_LINES_PER_PAGE]
                for index in range(
                    0,
                    len(body_lines),
                    BODY_LINES_PER_PAGE,
                )
            ]

            if not chunks:
                chunks = [[]]

            for part_no, chunk in enumerate(chunks, start=1):
                _draw_audit_page(
                    out_doc,
                    pdf_page_no=page_no,
                    lines=chunk,
                    part_no=part_no,
                    part_count=len(chunks),
                )

        if progress_callback is not None:
            progress_callback(
                total_pages,
                total_pages,
                "全ページ処理完了：PDFを最終生成・圧縮中",
            )

        return out_doc.tobytes(
            garbage=4,
            deflate=True,
        )

    finally:
        out_doc.close()
        src_doc.close()