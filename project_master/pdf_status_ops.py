# common_lib/project_master/pdf_status_ops.py
# ============================================================
# Project Master: 報告書PDFステータス（pdf_status.json）正本オペレーション
#
# ■ 目的
# - <year>/<pno>/pdf/pdf_status.json を正本として読み書きする
# - pdf_status.json には「PDF登録の事実」のみを記録する
#   - registered_at
#   - registered_by
# - 一覧表示用に、projects DB から「報告書PDFがあるプロジェクト」を取得する
#
# ■ 前提
# - pdf/ は存在が前提（create_project が作成する）
# - PDF種別・ページ数・OCR・text抽出・clean・RAG の状態は
#   text/processing_status.json 側で管理する
#
# ■ json 仕様
# {
#   "registered_at": "ISO",
#   "registered_by": "sub"
# }
#
# ■ 方針
# - 暗黙の回避はしない（不整合は明示エラー）
# - DB は projects テーブルを直接参照（一覧用途）
# - pdf_status.json の有無は「PDF登録メタがあるか」の意味だけを持つ
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import datetime as dt
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================
# imports（common_lib：paths / schema）
# ============================================================
from common_lib.project_master.paths import (
    get_project_master_db_path,
    get_project_pdf_dir,
    normalize_pno_3digits,
    normalize_year_4digits,
)
from common_lib.project_master.schema import table_exists


# ============================================================
# constants
# ============================================================
PDF_STATUS_FILENAME = "pdf_status.json"


# ============================================================
# public models（一覧用）
# ============================================================
@dataclass(frozen=True)
class ReportPdfListItem:
    # ------------------------------------------------------------
    # 一覧表示に必要な最小情報（DB + FS + pdf_status.json）
    # - RAG状態やPDF解析状態は含めない
    # ------------------------------------------------------------
    project_year: int
    project_no: str  # 3桁
    project_name: str
    client_name: str
    main_department: str

    pdf_filename: str
    pdf_size_bytes: int
    pdf_saved_at: str
    pdf_saved_by: str

    pdf_lock_flag: int

    pdf_status_path: Path
    pdf_status_exists: bool


# ============================================================
# helpers（db）
# ============================================================
def _connect(db_path: Path) -> sqlite3.Connection:
    # ------------------------------------------------------------
    # sqlite connect（row_factory で dict 化）
    # ------------------------------------------------------------
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _require_projects_table(db_path: Path) -> None:
    # ------------------------------------------------------------
    # projects テーブルの存在確認（明示エラー）
    # ------------------------------------------------------------
    if not table_exists(db_path, table_name="projects"):
        raise RuntimeError(
            "project_master.db / projects テーブルが未初期化です。"
            " common_lib.project_master.schema.init_project_master_db(...) を明示的に実行してください。"
        )


# ============================================================
# helpers（paths）
# ============================================================
def get_pdf_status_path(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # <year>/<pno>/pdf/pdf_status.json のパスを返す（存在確認はしない）
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)
    p = normalize_pno_3digits(project_no)

    pdf_dir = get_project_pdf_dir(
        projects_root,
        project_year=y,
        project_no=p,
        role=role,
    )
    return pdf_dir / PDF_STATUS_FILENAME


# ============================================================
# helpers（json）
# ============================================================
def _read_json(path: Path) -> Dict[str, Any]:
    # ------------------------------------------------------------
    # json 読み込み（明示エラー）
    # ------------------------------------------------------------
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(v, dict):
            raise RuntimeError(f"pdf_status.json が dict ではありません。 got={type(v).__name__}")
        return v
    except Exception as e:
        raise RuntimeError(f"pdf_status.json の読み込みに失敗しました。 path={path}") from e


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    # ------------------------------------------------------------
    # json 書き込み（atomic）
    # - pdf_dir は存在前提：無ければ明示エラー
    # ------------------------------------------------------------
    pdf_dir = path.parent
    if not pdf_dir.exists():
        raise RuntimeError(f"pdf_dir が存在しません（不整合）。 path={pdf_dir}")
    if not pdf_dir.is_dir():
        raise RuntimeError(f"pdf_dir がディレクトリではありません（不整合）。 path={pdf_dir}")

    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        raise RuntimeError(f"pdf_status.json の書き込みに失敗しました。 path={path}") from e
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


# ============================================================
# public（read / write）
# ============================================================
def read_pdf_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Optional[Dict[str, Any]]:
    # ------------------------------------------------------------
    # pdf_status.json を読む（無ければ None）
    # ------------------------------------------------------------
    path = get_pdf_status_path(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if not path.exists():
        return None
    return _read_json(path)


def write_pdf_status(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    registered_by: str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # pdf_status.json を保存する（上書き）
    # - 登録情報のみを記録する
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)
    p = normalize_pno_3digits(project_no)

    now_iso = dt.datetime.now().replace(microsecond=0).isoformat()

    payload: Dict[str, Any] = {
        "registered_at": now_iso,
        "registered_by": str(registered_by),
    }

    path = get_pdf_status_path(
        projects_root,
        project_year=y,
        project_no=p,
        role=role,
    )
    _write_json_atomic(path, payload)
    return path


# ============================================================
# public（一覧：年度候補）
# ============================================================
def list_years_with_report_pdf(
    projects_root: Path,
    *,
    role: str = "main",
) -> List[int]:
    # ------------------------------------------------------------
    # 報告書PDFが存在する年度（project_year）の一覧を返す（昇順）
    # - projects.report_pdf_stored_filename がある行を対象
    # ------------------------------------------------------------
    db_path = get_project_master_db_path(projects_root, role=role)
    _require_projects_table(db_path)

    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT DISTINCT project_year AS y
            FROM projects
            WHERE report_pdf_stored_filename IS NOT NULL
              AND TRIM(COALESCE(report_pdf_stored_filename, '')) <> ''
            ORDER BY y ASC
            """
        )
        years = [int(dict(r)["y"]) for r in cur.fetchall()]
        return years
    finally:
        conn.close()


# ============================================================
# public（一覧：年度内のPDF一覧）
# ============================================================
def list_report_pdfs_by_year(
    projects_root: Path,
    *,
    project_year: int | str,
    role: str = "main",
) -> List[ReportPdfListItem]:
    # ------------------------------------------------------------
    # 指定年度の「報告書PDFがあるプロジェクト」を一覧として返す
    # - pdf_status.json の有無は登録メタの有無として返す
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)

    db_path = get_project_master_db_path(projects_root, role=role)
    _require_projects_table(db_path)

    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT
              project_year,
              project_no,
              COALESCE(project_name, '') AS project_name,
              COALESCE(client_name, '') AS client_name,
              COALESCE(main_department, '') AS main_department,

              COALESCE(report_pdf_stored_filename, '') AS report_pdf_stored_filename,
              COALESCE(report_pdf_size_bytes, 0) AS report_pdf_size_bytes,
              COALESCE(report_pdf_saved_at, '') AS report_pdf_saved_at,
              COALESCE(report_pdf_saved_by, '') AS report_pdf_saved_by,

              COALESCE(pdf_lock_flag, 0) AS pdf_lock_flag
            FROM projects
            WHERE project_year = ?
              AND report_pdf_stored_filename IS NOT NULL
              AND TRIM(COALESCE(report_pdf_stored_filename, '')) <> ''
            ORDER BY project_no ASC
            """,
            (y,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    out: List[ReportPdfListItem] = []
    for r in rows:
        pno3 = normalize_pno_3digits(str(r.get("project_no", "")))

        # ------------------------------------------------------------
        # pdf_dir と pdfファイル名（DBを正本とする）
        # ------------------------------------------------------------
        pdf_dir = get_project_pdf_dir(
            projects_root,
            project_year=y,
            project_no=pno3,
            role=role,
        )
        pdf_filename = str(r.get("report_pdf_stored_filename", "") or "").strip()
        if not pdf_filename:
            continue

        pdf_path = pdf_dir / pdf_filename
        size_bytes = int(r.get("report_pdf_size_bytes", 0) or 0)

        # FSに実体があれば size を補正（DBより信用できる）
        try:
            if pdf_path.exists() and pdf_path.is_file():
                size_bytes = int(pdf_path.stat().st_size)
        except Exception:
            pass

        status_path = get_pdf_status_path(
            projects_root,
            project_year=y,
            project_no=pno3,
            role=role,
        )

        status_exists = bool(status_path.exists())

        out.append(
            ReportPdfListItem(
                project_year=y,
                project_no=pno3,
                project_name=str(r.get("project_name", "") or ""),
                client_name=str(r.get("client_name", "") or ""),
                main_department=str(r.get("main_department", "") or ""),
                pdf_filename=pdf_filename,
                pdf_size_bytes=size_bytes,
                pdf_saved_at=str(r.get("report_pdf_saved_at", "") or ""),
                pdf_saved_by=str(r.get("report_pdf_saved_by", "") or ""),
                pdf_lock_flag=int(r.get("pdf_lock_flag", 0) or 0),
                pdf_status_path=status_path,
                pdf_status_exists=status_exists,
            )
        )

    return out