# common_lib/project_master/report_text_ops.py
# ============================================================
# Project Master: 報告書テキストオペレーション（正本API）
#
# ■ 目的
# - 報告書PDFに対応する text/ ディレクトリを解決する
# - text_raw.txt / text_clean.txt の Path 取得・存在確認・読込を行う
# - テキスト表示用の行単位ページングを提供する
#
# ■ 前提ディレクトリ構成
# - <year>/<pno>/pdf/<pdf_file>
# - <year>/<pno>/text/text_raw.txt
# - <year>/<pno>/text/text_clean.txt
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from pathlib import Path

# ============================================================
# project_master imports
# ============================================================
from common_lib.project_master import get_report_pdf_path


# ============================================================
# constants
# ============================================================
TEXT_RAW_FILENAME = "report_raw.txt"
TEXT_CLEAN_FILENAME = "report_clean.txt"


# ============================================================
# text dir / path
# ============================================================
def get_report_text_dir(
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> Path | None:
    # ------------------------------------------------------------
    # 報告書textディレクトリを返す
    # ------------------------------------------------------------
    pdf_path = get_report_pdf_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if pdf_path is None:
        return None
    return pdf_path.parent.parent / "text"


def get_text_raw_path(
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> Path | None:
    # ------------------------------------------------------------
    # raw text path
    # ------------------------------------------------------------
    text_dir = get_report_text_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if text_dir is None:
        return None
    return text_dir / TEXT_RAW_FILENAME


def get_text_clean_path(
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> Path | None:
    # ------------------------------------------------------------
    # clean text path
    # ------------------------------------------------------------
    text_dir = get_report_text_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if text_dir is None:
        return None
    return text_dir / TEXT_CLEAN_FILENAME


# ============================================================
# exists
# ============================================================
def exists_text_raw(
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> bool:
    # ------------------------------------------------------------
    # raw text exists
    # ------------------------------------------------------------
    path = get_text_raw_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    return bool(path and path.exists())


def exists_text_clean(
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> bool:
    # ------------------------------------------------------------
    # clean text exists
    # ------------------------------------------------------------
    path = get_text_clean_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    return bool(path and path.exists())


# ============================================================
# read
# ============================================================
def read_text_raw(
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
    encoding: str = "utf-8",
) -> str:
    # ------------------------------------------------------------
    # raw text 読込
    # ------------------------------------------------------------
    path = get_text_raw_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if path is None or (not path.exists()):
        raise FileNotFoundError("text_raw.txt が存在しません。")
    return path.read_text(encoding=encoding)


def read_text_clean(
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
    encoding: str = "utf-8",
) -> str:
    # ------------------------------------------------------------
    # clean text 読込
    # ------------------------------------------------------------
    path = get_text_clean_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if path is None or (not path.exists()):
        raise FileNotFoundError("text_clean.txt が存在しません。")
    return path.read_text(encoding=encoding)


# ============================================================
# bytes
# ============================================================
def read_text_raw_bytes(
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> bytes:
    # ------------------------------------------------------------
    # raw text bytes
    # ------------------------------------------------------------
    path = get_text_raw_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if path is None or (not path.exists()):
        raise FileNotFoundError("text_raw.txt が存在しません。")
    return path.read_bytes()


def read_text_clean_bytes(
    projects_root: Path,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> bytes:
    # ------------------------------------------------------------
    # clean text bytes
    # ------------------------------------------------------------
    path = get_text_clean_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if path is None or (not path.exists()):
        raise FileNotFoundError("text_clean.txt が存在しません。")
    return path.read_bytes()


# ============================================================
# pagination
# ============================================================
def split_text_into_pages(
    text: str,
    lines_per_page: int = 40,
) -> list[str]:
    # ------------------------------------------------------------
    # 行単位でテキストをページ分割
    # ------------------------------------------------------------
    lines = text.splitlines()
    if not lines:
        return [""]
    pages: list[str] = []
    for i in range(0, len(lines), lines_per_page):
        pages.append("\n".join(lines[i:i + lines_per_page]))
    return pages


def get_text_page_count(
    text: str,
    lines_per_page: int = 40,
) -> int:
    # ------------------------------------------------------------
    # 総ページ数
    # ------------------------------------------------------------
    return len(split_text_into_pages(text, lines_per_page=lines_per_page))


def get_text_page_content(
    text: str,
    page_no_1based: int,
    lines_per_page: int = 40,
) -> str:
    # ------------------------------------------------------------
    # 指定ページ本文（1始まり）
    # ------------------------------------------------------------
    pages = split_text_into_pages(text, lines_per_page=lines_per_page)
    if page_no_1based < 1:
        page_no_1based = 1
    if page_no_1based > len(pages):
        page_no_1based = len(pages)
    return pages[page_no_1based - 1]