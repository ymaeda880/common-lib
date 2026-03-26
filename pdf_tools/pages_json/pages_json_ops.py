# common_lib/pdf_tools/pages_json/pages_json_ops.py
# ============================================================
# ページテキストJSONオペレーション（正本API）
#
# 目的：
# - report_raw_pages.json / report_clean_pages.json の作成・保存・読込を行う
# - RAG 用のページ正本を安定的に扱う
#
# 設計方針：
# - text/ 配下に保存する
# - raw / clean は kind で区別する
# - RAG builder は clean_pages を優先し、無ければ raw_pages を使う
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import json
from pathlib import Path
from typing import Iterable, List, Optional

# ============================================================
# project imports
# ============================================================
from common_lib.project_master.report_text_ops import get_report_text_dir
from .schema import PageTextRecord, ReportPagesJson


# ============================================================
# constants
# ============================================================
PAGES_JSON_VERSION = 1
RAW_PAGES_FILENAME = "report_raw_pages.json"
CLEAN_PAGES_FILENAME = "report_clean_pages.json"
KIND_RAW = "raw"
KIND_CLEAN = "clean"


# ============================================================
# internal helpers
# ============================================================
def _normalize_pages_text_list(
    pages_text_list: Iterable[str],
) -> List[str]:
    # ------------------------------------------------------------
    # ページ本文列の正規化
    # ------------------------------------------------------------
    out: List[str] = []
    for x in pages_text_list:
        out.append(str(x or ""))
    return out


def _build_pages_json_obj(
    *,
    kind: str,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    pdf_filename: str,
    source_pdf_sha256: Optional[str],
    pages_text_list: Iterable[str],
) -> ReportPagesJson:
    # ------------------------------------------------------------
    # dataclass構築
    # ------------------------------------------------------------
    norm_pages = _normalize_pages_text_list(pages_text_list)

    pages = [
        PageTextRecord(
            page_no=i + 1,
            text=text,
        )
        for i, text in enumerate(norm_pages)
    ]

    return ReportPagesJson(
        version=PAGES_JSON_VERSION,
        kind=str(kind),
        collection_id=str(collection_id),
        shard_id=str(shard_id),
        doc_id=str(doc_id),
        pdf_filename=str(pdf_filename or ""),
        source_pdf_sha256=(
            str(source_pdf_sha256)
            if source_pdf_sha256 is not None
            else None
        ),
        pages=pages,
    )


def _get_pages_json_path(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    kind: str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # pages.json の保存先を返す
    # ------------------------------------------------------------
    text_dir = get_report_text_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if text_dir is None:
        raise FileNotFoundError("text ディレクトリを解決できません。")

    if str(kind) == KIND_RAW:
        return text_dir / RAW_PAGES_FILENAME

    if str(kind) == KIND_CLEAN:
        return text_dir / CLEAN_PAGES_FILENAME

    raise ValueError(f"不正な kind です: {kind}")


# ============================================================
# path api
# ============================================================
def get_report_raw_pages_json_path(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # raw pages.json path
    # ------------------------------------------------------------
    return _get_pages_json_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        kind=KIND_RAW,
        role=role,
    )


def get_report_clean_pages_json_path(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # clean pages.json path
    # ------------------------------------------------------------
    return _get_pages_json_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        kind=KIND_CLEAN,
        role=role,
    )


# ============================================================
# exists api
# ============================================================
def exists_report_raw_pages_json(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> bool:
    # ------------------------------------------------------------
    # raw pages.json exists
    # ------------------------------------------------------------
    return get_report_raw_pages_json_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    ).exists()


def exists_report_clean_pages_json(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> bool:
    # ------------------------------------------------------------
    # clean pages.json exists
    # ------------------------------------------------------------
    return get_report_clean_pages_json_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    ).exists()


# ============================================================
# write api
# ============================================================
def write_pages_json(
    path: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    pdf_filename: str,
    source_pdf_sha256: Optional[str],
    pages_text_list: Iterable[str],
    kind: str,
) -> Path:
    # ------------------------------------------------------------
    # pages.json 保存
    # ------------------------------------------------------------
    path.parent.mkdir(parents=True, exist_ok=True)

    obj = _build_pages_json_obj(
        kind=str(kind),
        collection_id=str(collection_id),
        shard_id=str(shard_id),
        doc_id=str(doc_id),
        pdf_filename=str(pdf_filename or ""),
        source_pdf_sha256=source_pdf_sha256,
        pages_text_list=pages_text_list,
    )

    path.write_text(
        json.dumps(obj.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def create_raw_pages_json(
    path: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    pdf_filename: str,
    source_pdf_sha256: Optional[str],
    pages_text_list: Iterable[str],
) -> Path:
    # ------------------------------------------------------------
    # raw pages.json 作成
    # ------------------------------------------------------------
    return write_pages_json(
        path,
        collection_id=str(collection_id),
        shard_id=str(shard_id),
        doc_id=str(doc_id),
        pdf_filename=str(pdf_filename or ""),
        source_pdf_sha256=source_pdf_sha256,
        pages_text_list=pages_text_list,
        kind=KIND_RAW,
    )

def create_clean_pages_json(
    path: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    pdf_filename: str,
    source_pdf_sha256: Optional[str],
    pages_text_list: Iterable[str],
) -> Path:
    # ------------------------------------------------------------
    # clean pages.json 作成
    # ------------------------------------------------------------
    return write_pages_json(
        path,
        collection_id=str(collection_id),
        shard_id=str(shard_id),
        doc_id=str(doc_id),
        pdf_filename=str(pdf_filename or ""),
        source_pdf_sha256=source_pdf_sha256,
        pages_text_list=pages_text_list,
        kind=KIND_CLEAN,
    )

# ============================================================
# read api
# ============================================================
def read_pages_json(path: Path) -> ReportPagesJson:
    # ------------------------------------------------------------
    # path 指定読込
    # ------------------------------------------------------------
    if not path.exists():
        raise FileNotFoundError(f"pages.json が存在しません: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    return ReportPagesJson.from_dict(data)


def read_report_raw_pages_json(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> ReportPagesJson:
    # ------------------------------------------------------------
    # raw pages.json 読込
    # ------------------------------------------------------------
    path = get_report_raw_pages_json_path(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        role=role,
    )
    return read_pages_json(path)


def read_report_clean_pages_json(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> ReportPagesJson:
    # ------------------------------------------------------------
    # clean pages.json 読込
    # ------------------------------------------------------------
    path = get_report_clean_pages_json_path(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        role=role,
    )
    return read_pages_json(path)


# ============================================================
# resolve api
# ============================================================
def resolve_report_pages_json_path(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> Path | None:
    # ------------------------------------------------------------
    # RAG用 pages.json の解決
    # 優先順位：
    # 1. clean pages
    # 2. raw pages
    # ------------------------------------------------------------
    clean_path = get_report_clean_pages_json_path(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        role=role,
    )
    if clean_path.exists():
        return clean_path

    raw_path = get_report_raw_pages_json_path(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        role=role,
    )
    if raw_path.exists():
        return raw_path

    return None


def resolve_report_pages_json(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str = "main",
) -> ReportPagesJson | None:
    # ------------------------------------------------------------
    # RAG用 pages.json の読込
    # ------------------------------------------------------------
    path = resolve_report_pages_json_path(
        projects_root,
        project_year=int(project_year),
        project_no=str(project_no),
        role=role,
    )
    if path is None:
        return None
    return read_pages_json(path)