# -*- coding: utf-8 -*-
# common_lib/project_master/paths.py
# ============================================================
# Project Master: パス解決（正本）
#
# ■ 目的
# - Archive の root を role（main/backup/backup2）で解決する（正本）
# - Project Master の root / DB / 各ディレクトリの絶対パスを生成する（正本）
# - project_year（4桁）/ project_no（3桁）を正規化・検証し、混在事故を根絶する
#
# ■ ディレクトリ構造（正本）
#
# Archive/
# └── project/
#     ├── project_master.db
#     └── <year>/
#         └── <pno>/
#             ├── pdf/
#             │   └── pdf_status.json      ← PDF判定/status（正本：pdf配下）
#             ├── ocr/                     ← OCR生成物
#             ├── text/                    ← PDFから抽出したテキスト（正本）
#             ├── others/
#             └── contract/
#
# ※ 方針
# - pdf/history は作らない（不要）
# - others は拡張子別ディレクトリを作らない（others 直下に置く）
# - contract は契約関連書類（見積/契約/発注等）を格納する専用ディレクトリ
# - pdf_status.json は ocr 配下に置かない（pdf 配下へ集約）
#
# ■ 設計方針
# 1. 正規化・検証は必ずここを通す
#    - project_year は 4桁（1000〜9999）を保証
#    - project_no は 3桁ゼロ埋め（001形式）に統一
#
# 2. role の扱い
#    - main は secrets.toml の mode に従う（internal/external）
#    - backup/backup2 は external 強制（resolve 側の設計に従う）
#
# 3. 本モジュールは「パス生成専用」
#    - ファイルの作成/削除/移動ロジックは別モジュールで担う
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from dataclasses import dataclass
from pathlib import Path

# ============================================================
# imports（common_lib）
# ============================================================
from common_lib.storage.external_ssd_root import resolve_storage_subdir_root

# ============================================================
# constants
# ============================================================
# ------------------------------------------------------------
# Archive 配下の Project Master ルート（相対）
# - 旧：Archive/report
# - 新：Archive/project
# ------------------------------------------------------------
PROJECT_MASTER_REL_ROOT = Path("project")

# ------------------------------------------------------------
# role の許容値（運用上の想定）
# ------------------------------------------------------------
_ALLOWED_ROLES = {"main", "backup", "backup2"}

# ------------------------------------------------------------
# pdf_status.json のファイル名（正本）
# ------------------------------------------------------------
PDF_STATUS_JSON_NAME = "pdf_status.json"

# ============================================================
# data model（paths）
# ============================================================
@dataclass(frozen=True)
class ProjectMasterPaths:
    """
    Project Master の基本パスセット

    - archive_root: resolve_storage_subdir_root により解決された Archive の root
    - project_root: Archive/project の root
    - db_path:      Archive/project/project_master.db
    """
    archive_root: Path
    project_root: Path
    db_path: Path


# ============================================================
# helpers（validate / normalize）
# ============================================================
def _validate_role(role: str) -> str:
    # ------------------------------------------------------------
    # role の検証
    # ------------------------------------------------------------
    if role not in _ALLOWED_ROLES:
        raise ValueError(f"Invalid role: {role!r}. Allowed: {sorted(_ALLOWED_ROLES)}")
    return role


def normalize_year_4digits(project_year: int | str) -> int:
    # ------------------------------------------------------------
    # project_year を int に正規化し、4桁（1000〜9999）を保証
    # ------------------------------------------------------------
    try:
        y = int(str(project_year).strip())
    except Exception as e:
        raise ValueError(f"Invalid project_year: {project_year!r}") from e

    if y < 1000 or y > 9999:
        raise ValueError(f"project_year must be 4 digits: {y}")
    return y


def normalize_pno_3digits(project_no: int | str) -> str:
    # ------------------------------------------------------------
    # project_no を 3桁ゼロ埋め文字列に正規化（001形式）
    # - 混在事故（1 / 01 / 001）を根絶するため、必ずここを通す
    # ------------------------------------------------------------
    s = str(project_no).strip()

    try:
        n = int(s)
    except Exception as e:
        raise ValueError(f"Invalid project_no: {project_no!r}") from e

    if n < 0:
        raise ValueError(f"project_no must be >= 0: {n}")

    if n > 999:
        raise ValueError(f"project_no must be <= 999 for 3 digits: {n}")

    return f"{n:03d}"


# ============================================================
# core（resolve roots）
# ============================================================
def get_archive_root(projects_root: Path, *, role: str = "main") -> Path:
    # ------------------------------------------------------------
    # Archive の root を role で解決（正本）
    # - main は secrets.toml の mode に従う（internal/external）
    # - backup/backup2 は external 強制（resolve 側の設計に従う）
    # ------------------------------------------------------------
    _validate_role(role)

    archive_root = resolve_storage_subdir_root(
        projects_root,
        subdir="Archive",
        role=role,  # type: ignore[arg-type]
    )
    return Path(archive_root)


def get_project_master_root(projects_root: Path, *, role: str = "main") -> Path:
    # ------------------------------------------------------------
    # Project Master の root（Archive/project）を返す
    # ------------------------------------------------------------
    archive_root = get_archive_root(projects_root, role=role)
    return archive_root / PROJECT_MASTER_REL_ROOT


def get_project_master_db_path(projects_root: Path, *, role: str = "main") -> Path:
    # ------------------------------------------------------------
    # project_master.db の絶対パス（正本）
    # ------------------------------------------------------------
    project_root = get_project_master_root(projects_root, role=role)
    return project_root / "project_master.db"


def get_project_master_paths(projects_root: Path, *, role: str = "main") -> ProjectMasterPaths:
    # ------------------------------------------------------------
    # まとめて返す（UI/Repo 側が迷わない）
    # ------------------------------------------------------------
    archive_root = get_archive_root(projects_root, role=role)
    project_root = archive_root / PROJECT_MASTER_REL_ROOT
    db_path = project_root / "project_master.db"
    return ProjectMasterPaths(
        archive_root=archive_root,
        project_root=project_root,
        db_path=db_path,
    )


# ============================================================
# project scoped dirs（project_year / project_no）
# ============================================================
def get_project_root_dir(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # Archive/project/<year>/<pno> の絶対パス
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)
    p = normalize_pno_3digits(project_no)

    project_root = get_project_master_root(projects_root, role=role)
    return project_root / str(y) / p


def get_project_pdf_dir(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # Archive/project/<year>/<pno>/pdf
    # ------------------------------------------------------------
    project_root = get_project_root_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    return project_root / "pdf"


def get_project_others_dir(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # Archive/project/<year>/<pno>/others
    # - 拡張子別ディレクトリは作らない（others 直下運用）
    # ------------------------------------------------------------
    project_root = get_project_root_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    return project_root / "others"


def get_project_contract_dir(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # Archive/project/<year>/<pno>/contract
    # - 契約関連書類（見積/契約/発注等）用
    # ------------------------------------------------------------
    project_root = get_project_root_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    return project_root / "contract"


# ============================================================
# public: OCR dir
# ============================================================
def get_project_ocr_dir(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # Archive/project/<year>/<pno>/ocr（role対応は root_dir に従う）
    # ------------------------------------------------------------
    root = get_project_root_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    return root / "ocr"


# ============================================================
# public: Text dir（PDF抽出テキスト）
# ============================================================
def get_project_text_dir(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # Archive/project/<year>/<pno>/text（PDF抽出テキストの格納先）
    # ------------------------------------------------------------
    root = get_project_root_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    return root / "text"


# ============================================================
# public: pdf_status.json path（正本：pdf配下）
# ============================================================
def get_project_pdf_status_json_path(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    # ------------------------------------------------------------
    # Archive/project/<year>/<pno>/pdf/pdf_status.json
    # - 判定結果/ページ数/type等の状態ファイルは pdf 配下に集約する（正本）
    # ------------------------------------------------------------
    pdf_dir = get_project_pdf_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    return pdf_dir / PDF_STATUS_JSON_NAME

