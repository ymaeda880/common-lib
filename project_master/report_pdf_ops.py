# -*- coding: utf-8 -*-
# common_lib/project_master/report_pdf_ops.py
# ============================================================
# Project Master: 報告書PDFオペレーション（正本API）
# - 報告書PDFは <year>/<no>/pdf 配下に 1本のみ
# - 保存（置換）/ 削除 / ロック（未登録は不可）を正本で統制する
#
# 重要ルール：
# - pdf_lock_flag=1 のとき、PDFの保存/削除は不可
# - 報告書PDFが存在しないプロジェクトはロック不可
#
# B案：
# - 保存ファイル名は固定しない（アップロード元のファイル名で保存）
# - 保存前に pdf/ 内の既存PDFは全削除して「常に1本」制約
#
# 追加仕様（今回）：
# - upsert（登録/変更）時に、pdf/pdf_status.json を作成し、
#   registered_at / registered_by を書き込む
# - upsert 時には page数抽出・pdf_kind判定・text抽出は行わない
#
# 正本方針（重要）：
# - 派生物（ocr/ text）は「PDFが変わったら古くなる」ため厳格に全消しする
# - 派生物ディレクトリ（ocr/text）は「存在が前提」。無ければ不整合として例外で止める
# - PDF種別・ページ数・OCR・text抽出・clean・RAG 状態は
#   text/processing_status.json 側で管理する
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import datetime as dt
import hashlib
import shutil
from pathlib import Path
from typing import Optional

# ============================================================
# imports（3rd party）
# ============================================================
import streamlit as st

# ============================================================
# imports（common_lib/project_master）
# ============================================================
from common_lib.project_master.projects_repo import (
    get_project,
    update_project,
)
from common_lib.project_master.paths import (
    normalize_year_4digits,
    normalize_pno_3digits,
    get_project_pdf_dir,
    get_project_ocr_dir,
    get_project_text_dir,
)
from common_lib.project_master.pdf_status_ops import (
    write_pdf_status,
)

# ============================================================
# helpers（hash）
# ============================================================
def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


# ============================================================
# helpers（fs）
# ============================================================
def _list_pdfs(pdf_dir: Path) -> list[Path]:
    if not pdf_dir.exists():
        return []
    out: list[Path] = []
    for p in pdf_dir.iterdir():
        if p.is_file() and p.suffix.lower() == ".pdf":
            out.append(p)
    return sorted(out)


def _remove_all_pdfs(pdf_dir: Path) -> None:
    for p in _list_pdfs(pdf_dir):
        p.unlink()


def _atomic_write_bytes(dst: Path, data: bytes) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dst)


def _safe_pdf_filename(original_filename: str) -> str:
    # ------------------------------------------------------------
    # ファイル名のみを採用（パストラバーサル防止）
    # - 空の場合のみフォールバック
    # ------------------------------------------------------------
    name = Path(str(original_filename or "")).name.strip()
    if not name:
        return "report.pdf"
    if not name.lower().endswith(".pdf"):
        name = name + ".pdf"
    return name


def _require_existing_dir(*, dir_path: Path, name: str) -> None:
    # ------------------------------------------------------------
    # ディレクトリ存在前提ガード
    # ------------------------------------------------------------
    if not dir_path.exists():
        raise RuntimeError(f"{name} が存在しません（不整合）。 path={dir_path}")
    if not dir_path.is_dir():
        raise RuntimeError(f"{name} がディレクトリではありません（不整合）。 path={dir_path}")


# ============================================================
# helpers（guards）
# ============================================================
def _require_project(projects_root: Path, *, year: int, pno3: str, role: str):
    p = get_project(projects_root, project_year=year, project_no=pno3, role=role)
    if p is None:
        raise RuntimeError("projects に対象プロジェクトが未登録です（先にプロジェクトを作成してください）。")
    return p


def _is_locked(project) -> bool:
    return int(project.pdf_lock_flag or 0) == 1


def _has_report_pdf(pdf_dir: Path) -> bool:
    return len(_list_pdfs(pdf_dir)) > 0


# ============================================================
# helpers（pdf_status: write on upsert）
# ============================================================
def _write_pdf_status_on_upsert(
    projects_root: Path,
    *,
    project_year: int,
    project_no_3digits: str,
    registered_by: str,
) -> None:
    # ------------------------------------------------------------
    # upsert直後に pdf/pdf_status.json を更新する
    # - 登録情報のみを記録する
    # ------------------------------------------------------------
    write_pdf_status(
        projects_root,
        project_year=project_year,
        project_no=project_no_3digits,
        registered_by=str(registered_by),
    )


# ============================================================
# helpers（OCR cleanup）
# ============================================================
def _clear_ocr_dir_contents_strict(*, ocr_dir: Path) -> None:
    _require_existing_dir(dir_path=ocr_dir, name="ocr_dir")

    for p in ocr_dir.iterdir():
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        except Exception as e:
            raise RuntimeError(
                "ocr_dir 配下の削除に失敗しました（事故防止のため握りません）。"
                f" ocr_dir={ocr_dir} failed_entry={p}"
            ) from e


# ============================================================
# helpers（text cleanup）
# ============================================================
def _clear_text_dir_contents_strict(*, text_dir: Path) -> None:
    _require_existing_dir(dir_path=text_dir, name="text_dir")

    for p in text_dir.iterdir():
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        except Exception as e:
            raise RuntimeError(
                "text_dir 配下の削除に失敗しました（事故防止のため握りません）。"
                f" text_dir={text_dir} failed_entry={p}"
            ) from e


# ============================================================
# public（read）
# ============================================================
def get_report_pdf_path(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Optional[Path]:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    pdf_dir = get_project_pdf_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    pdfs = _list_pdfs(pdf_dir)
    if not pdfs:
        return None
    return pdfs[0]


# ============================================================
# public（save / delete）
# ============================================================
def upsert_report_pdf(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    pdf_bytes: bytes,
    original_filename: str,
    saved_by: str,
    role: str = "main",
) -> Path:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    project = _require_project(projects_root, year=y, pno3=pno3, role=role)
    if _is_locked(project):
        raise RuntimeError("PDFロック中のため、報告書PDFの保存（置換）はできません。")

    if not isinstance(pdf_bytes, (bytes, bytearray)) or (len(pdf_bytes) <= 0):
        raise RuntimeError("pdf_bytes が空です。")

    pdf_dir = get_project_pdf_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    pdf_dir.mkdir(parents=True, exist_ok=True)

    _remove_all_pdfs(pdf_dir)

    stored_filename = _safe_pdf_filename(original_filename)
    dst = pdf_dir / stored_filename
    _atomic_write_bytes(dst, bytes(pdf_bytes))

    ocr_dir = get_project_ocr_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    _clear_ocr_dir_contents_strict(ocr_dir=ocr_dir)

    text_dir = get_project_text_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    _clear_text_dir_contents_strict(text_dir=text_dir)

    try:
        _write_pdf_status_on_upsert(
            projects_root,
            project_year=y,
            project_no_3digits=pno3,
            registered_by=str(saved_by),
        )
    except Exception:
        try:
            if dst.exists():
                dst.unlink()
        except Exception:
            pass
        raise

    now_iso = dt.datetime.now().replace(microsecond=0).isoformat()
    project.report_pdf_original_filename = str(original_filename or "")
    project.report_pdf_stored_filename = str(stored_filename)
    project.report_pdf_hash_sha256 = _sha256_bytes(bytes(pdf_bytes))
    project.report_pdf_size_bytes = int(len(pdf_bytes))
    project.report_pdf_saved_at = now_iso
    project.report_pdf_saved_by = str(saved_by)

    project.update_user_id = str(saved_by)
    project.update_date = dt.date.today().isoformat()

    update_project(projects_root, project=project, role=role)
    return dst


def delete_report_pdf(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    deleted_by: str,
    role: str = "main",
) -> dict[str, object]:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    project = _require_project(projects_root, year=y, pno3=pno3, role=role)
    if _is_locked(project):
        raise RuntimeError("PDFロック中のため、報告書PDFの削除はできません。")

    pdf_dir = get_project_pdf_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )

    result: dict[str, object] = {
        "pdf_dir": str(pdf_dir),
        "pdf_deleted_count": 0,
        "pdf_status_found": False,
        "pdf_status_deleted": False,
        "ocr_cleared": False,
        "text_cleared": False,
    }

    if pdf_dir.exists():
        pdfs_before = _list_pdfs(pdf_dir)
        _remove_all_pdfs(pdf_dir)
    else:
        pdfs_before = []
    result["pdf_deleted_count"] = int(len(pdfs_before))

    status_path = pdf_dir / "pdf_status.json"
    try:
        if status_path.exists() and status_path.is_file():
            result["pdf_status_found"] = True
            status_path.unlink()
            result["pdf_status_deleted"] = True
        else:
            result["pdf_status_found"] = False
            result["pdf_status_deleted"] = False
    except Exception as e:
        raise RuntimeError(f"pdf_status.json の削除に失敗しました。 path={status_path}") from e

    ocr_dir = get_project_ocr_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    _clear_ocr_dir_contents_strict(ocr_dir=ocr_dir)
    result["ocr_cleared"] = True

    text_dir = get_project_text_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    _clear_text_dir_contents_strict(text_dir=text_dir)
    result["text_cleared"] = True

    project.report_pdf_original_filename = None
    project.report_pdf_stored_filename = None
    project.report_pdf_hash_sha256 = None
    project.report_pdf_size_bytes = None
    project.report_pdf_saved_at = None
    project.report_pdf_saved_by = None

    project.update_user_id = str(deleted_by)
    project.update_date = dt.date.today().isoformat()

    update_project(projects_root, project=project, role=role)

    return result


# ============================================================
# public（lock）
# ============================================================
def set_pdf_lock(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    locked_by: str,
    role: str = "main",
) -> None:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    project = _require_project(projects_root, year=y, pno3=pno3, role=role)

    pdf_dir = get_project_pdf_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    if not _has_report_pdf(pdf_dir):
        raise RuntimeError("報告書未登録のためロックできません（先にPDFを保存してください）。")

    if _is_locked(project):
        return

    now_iso = dt.datetime.now().replace(microsecond=0).isoformat()
    project.pdf_lock_flag = 1
    project.pdf_locked_at = now_iso
    project.pdf_locked_by = str(locked_by)

    project.update_user_id = str(locked_by)
    project.update_date = dt.date.today().isoformat()

    update_project(projects_root, project=project, role=role)


def clear_pdf_lock(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    unlocked_by: str,
    role: str = "main",
) -> None:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    project = _require_project(projects_root, year=y, pno3=pno3, role=role)

    if not _is_locked(project):
        return

    project.pdf_lock_flag = 0
    project.pdf_locked_at = None
    project.pdf_locked_by = None

    project.update_user_id = str(unlocked_by)
    project.update_date = dt.date.today().isoformat()

    update_project(projects_root, project=project, role=role)


# ============================================================
# public（preview: bytes / sha / page_count / render）
# ============================================================
def get_report_pdf_bytes_and_sha256(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Optional[tuple[str, bytes]]:
    pdf_path = get_report_pdf_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if pdf_path is None or (not pdf_path.exists()):
        return None

    b = pdf_path.read_bytes()
    sha = _sha256_bytes(b)
    return sha, b


@st.cache_data(show_spinner=False)
def get_pdf_page_count_from_bytes(
    pdf_sha256: str,
    pdf_bytes: bytes,
) -> int:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.is_encrypted:
            raise RuntimeError("このPDFは暗号化されています（パスワード付き）。")
        return int(doc.page_count)
    finally:
        doc.close()


@st.cache_data(show_spinner=False)
def render_pdf_page_png_simple_from_bytes(
    pdf_sha256: str,
    pdf_bytes: bytes,
    page_index: int,
) -> bytes:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.is_encrypted:
            raise RuntimeError("このPDFは暗号化されています（パスワード付き）。")

        page_count = int(doc.page_count)
        if page_count <= 0:
            raise RuntimeError("PDFのページ数を取得できませんでした。")

        idx = int(page_index)
        if idx < 0 or idx >= page_count:
            raise RuntimeError(f"page_index out of range: {idx} / {page_count}")

        page = doc.load_page(idx)
        pix = page.get_pixmap(alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()