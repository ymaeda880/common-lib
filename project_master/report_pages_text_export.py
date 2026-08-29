# -*- coding: utf-8 -*-
# common_lib/project_master/report_pages_text_export.py
# ============================================================
# report_pages.json 指定ページテキスト出力
#
# 機能：
# - report_pages.json から指定ページの text を取得する
# - ページ番号付きの区切り形式でTXT文字列を生成する
#
# 方針：
# - 正本は text/report_pages.json
# - OCR専用にはせず，任意のページ番号一覧を対象にする
# - Streamlitには依存しない
# - report_pages.json 自体は変更しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from pathlib import Path

from common_lib.project_master.report_pages_v2_ops import (
    read_report_pages,
)


# ============================================================
# public
# ============================================================
def build_selected_pages_text(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    page_numbers: list[int],
) -> str:
    # ------------------------------------------------------------
    # 指定ページだけをページ区切り付きTXTへ変換する
    # ------------------------------------------------------------
    payload = read_report_pages(
        projects_root,
        project_year=project_year,
        project_no=project_no,
    )

    target_pages = sorted({
        int(page_no)
        for page_no in page_numbers
        if int(page_no) > 0
    })

    if not target_pages:
        return ""

    page_text_map = {
        int(row.get("page_no", 0) or 0): str(row.get("text", "") or "")
        for row in payload.get("pages", [])
        if isinstance(row, dict)
    }

    blocks: list[str] = []

    for page_no in target_pages:
        page_text = page_text_map.get(page_no)

        if page_text is None:
            continue

        blocks.append(
            "\n".join([
                "=" * 60,
                f"PDF Page {page_no}",
                "=" * 60,
                "",
                page_text,
            ])
        )

    if not blocks:
        return ""

    return "\n\n\n".join(blocks).rstrip() + "\n"