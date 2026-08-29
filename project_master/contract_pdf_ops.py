# -*- coding: utf-8 -*-
# common_lib/project_master/contract_pdf_ops.py
# ============================================================
# Project Master: 契約書PDFオペレーション（正本API）
#
# 仕様：
# - 契約書PDFは <year>/<pno>/contract 配下に1本のみ
# - 保存ファイル名は <year><pno3>.pdf
# - 例：1973 / 003 -> 1973003.pdf
# - contractフォルダーは存在前提
# - このモジュールではフォルダーを新規作成しない
# - project_master.db未登録プロジェクトは処理しない
# - 報告書PDF用DB項目・OCR・text・lockには触れない
# ============================================================

from __future__ import annotations

from pathlib import Path

from common_lib.project_master.projects_repo import get_project
from common_lib.project_master.paths import (
    get_project_contract_dir,
    normalize_pno_3digits,
    normalize_year_4digits,
)
from common_lib.project_master.contract_status_ops import (
    delete_contract_status,
    write_contract_status,
)


def build_contract_pdf_filename(
    *,
    project_year: int | str,
    project_no: int | str,
) -> str:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)
    return f"{y}{pno3}.pdf"


def get_contract_pdf_path(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Path:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)
    contract_dir = get_project_contract_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    return contract_dir / build_contract_pdf_filename(
        project_year=y,
        project_no=pno3,
    )


def list_contract_pdfs(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> list[Path]:
    contract_dir = get_project_contract_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    if not contract_dir.exists():
        return []
    if not contract_dir.is_dir():
        raise RuntimeError(
            "contractがフォルダーではありません。"
            f" path={contract_dir}"
        )

    return sorted(
        [
            path
            for path in contract_dir.iterdir()
            if path.is_file() and path.suffix.casefold() == ".pdf"
        ],
        key=lambda path: (path.name.casefold(), path.name),
    )


def _require_registered_project(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str,
) -> None:
    project = get_project(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )
    if project is None:
        raise RuntimeError(
            "project_master.dbに対象プロジェクトが登録されていません。"
            f" year={project_year} pno={project_no}"
        )


def _require_contract_dir(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    role: str,
) -> Path:
    contract_dir = get_project_contract_dir(
        projects_root,
        project_year=project_year,
        project_no=project_no,
        role=role,
    )

    if not contract_dir.exists():
        raise RuntimeError(
            "contractフォルダーが存在しません。自動作成は行いません。"
            f" path={contract_dir}"
        )
    if not contract_dir.is_dir():
        raise RuntimeError(
            "contractがフォルダーではありません。"
            f" path={contract_dir}"
        )
    return contract_dir


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    except Exception as e:
        raise RuntimeError(
            "契約書PDFの保存に失敗しました。"
            f" path={path}"
        ) from e
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def upsert_contract_pdf(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    pdf_bytes: bytes,
    saved_by: str,
    overwrite_existing: bool = False,
    role: str = "main",
) -> Path:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    _require_registered_project(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    _require_contract_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )

    if not isinstance(pdf_bytes, (bytes, bytearray)) or len(pdf_bytes) <= 0:
        raise RuntimeError("pdf_bytes が空です。")

    expected_path = get_contract_pdf_path(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    existing_pdfs = list_contract_pdfs(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    unexpected_pdfs = [
        path for path in existing_pdfs if path.name != expected_path.name
    ]

    # 別名PDF・複数PDFは警告対象であり，正本API側でも安全のため止める。
    if unexpected_pdfs or len(existing_pdfs) > 1:
        names = ", ".join(path.name for path in existing_pdfs)
        raise RuntimeError(
            "contractフォルダー内に別名PDFまたは複数PDFがあります。"
            "自動削除・整理は行いません。"
            f" files={names}"
        )

    if expected_path.exists() and not overwrite_existing:
        raise FileExistsError(
            "契約書PDFはすでに登録されています。"
            f" path={expected_path}"
        )

    replacing = expected_path.exists()

    # 置換時は status をいったん削除してから，PDF・status を再作成する。
    if replacing:
        delete_contract_status(
            projects_root,
            project_year=y,
            project_no=pno3,
            role=role,
        )

    _atomic_write_bytes(expected_path, bytes(pdf_bytes))

    try:
        write_contract_status(
            projects_root,
            project_year=y,
            project_no=pno3,
            registered_by=str(saved_by),
            role=role,
        )
    except Exception:
        # status作成に失敗した今回のPDFは残さない。
        try:
            if expected_path.exists():
                expected_path.unlink()
        except Exception:
            pass
        raise

    return expected_path


def delete_contract_pdf(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    delete_status: bool = True,
    role: str = "main",
) -> bool:
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    _require_registered_project(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    _require_contract_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )

    target = get_contract_pdf_path(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )

    deleted = False
    if target.exists():
        if not target.is_file():
            raise RuntimeError(
                "契約書PDFパスがファイルではありません。"
                f" path={target}"
            )
        try:
            target.unlink()
            deleted = True
        except Exception as e:
            raise RuntimeError(
                "契約書PDFの削除に失敗しました。"
                f" path={target}"
            ) from e

    if delete_status:
        delete_contract_status(
            projects_root,
            project_year=y,
            project_no=pno3,
            role=role,
        )

    return deleted
