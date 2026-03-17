# common_lib/project_master/projects_repo.py
# ============================================================
# Project Master: projects リポジトリ（CRUD）
# - get / insert / update
# - DBパスは paths.py の正本から取得（Archive/project/project_master.db）
# - テーブル未初期化は明示エラー（init を促す）
#
# 前提：
# - project_master.db は schema.py（DDL_PROJECTS）で作り直し済み
# - projects テーブルに report_pdf_*（6カラム）が存在する
#
# 改修（B案：挙動は変えない）
# - SELECT / INSERT / UPDATE の列定義を「定数」にまとめ、修正漏れを防止する
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import sqlite3
from pathlib import Path
from typing import Optional

# ============================================================
# imports（common_lib/project_master）
# ============================================================
from common_lib.project_master.models import Project
from common_lib.project_master.paths import (
    get_project_master_db_path,
    normalize_pno_3digits,
    normalize_year_4digits,
)
from common_lib.project_master.schema import table_exists

# ============================================================
# constants（projects columns）
# ============================================================
# ------------------------------------------------------------
# projects テーブルの列（主キー）
# ------------------------------------------------------------
_PROJECTS_PK_COLS = (
    "project_year",
    "project_no",
)

# ------------------------------------------------------------
# projects テーブルの列（通常データ：主キー以外）
# - SELECT/INSERT/UPDATE の共通列として使う
# - 将来カラム追加時はここを直せばよい
# ------------------------------------------------------------
_PROJECTS_DATA_COLS = (
    "project_name",
    "client_name",
    "main_department",
    "contract_amount",
    "input_user_id",
    "input_date",
    "update_user_id",
    "update_date",
    "pdf_lock_flag",
    "pdf_locked_at",
    "pdf_locked_by",
    "report_pdf_original_filename",
    "report_pdf_stored_filename",
    "report_pdf_hash_sha256",
    "report_pdf_size_bytes",
    "report_pdf_saved_at",
    "report_pdf_saved_by",
)

# ------------------------------------------------------------
# SELECT の列（主キー + データ列）
# ------------------------------------------------------------
_PROJECTS_SELECT_COLS = _PROJECTS_PK_COLS + _PROJECTS_DATA_COLS

# ------------------------------------------------------------
# INSERT の列（主キー + データ列）
# ------------------------------------------------------------
_PROJECTS_INSERT_COLS = _PROJECTS_PK_COLS + _PROJECTS_DATA_COLS

# ------------------------------------------------------------
# UPDATE の SET 対象列（主キーは更新しない）
# - input_user_id / input_date も「初回登録情報として維持」したいなら
#   本来は UPDATE から外す選択もあり得るが、
#   現行挙動（payload をそのまま反映）を変えないため、列は残す。
# ------------------------------------------------------------
_PROJECTS_UPDATE_SET_COLS = _PROJECTS_DATA_COLS

# ============================================================
# helpers（SQL fragments）
# ============================================================
def _sql_cols(cols: tuple[str, ...]) -> str:
    # ------------------------------------------------------------
    # "a, b, c" 形式
    # ------------------------------------------------------------
    return ", ".join(cols)


def _sql_named_params(cols: tuple[str, ...]) -> str:
    # ------------------------------------------------------------
    # ":a, :b, :c" 形式
    # ------------------------------------------------------------
    return ", ".join(f":{c}" for c in cols)


def _sql_update_set_clause(cols: tuple[str, ...]) -> str:
    # ------------------------------------------------------------
    # "a = :a, b = :b, ..." 形式
    # ------------------------------------------------------------
    return ", ".join(f"{c} = :{c}" for c in cols)


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
# public（get）
# ============================================================
def get_project(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    role: str = "main",
) -> Optional[Project]:
    # ------------------------------------------------------------
    # projects から1件取得
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)
    p = normalize_pno_3digits(project_no)

    db_path = get_project_master_db_path(projects_root, role=role)
    _require_projects_table(db_path)

    select_cols_sql = _sql_cols(_PROJECTS_SELECT_COLS)

    conn = _connect(db_path)
    try:
        cur = conn.execute(
            f"""
            SELECT
              {select_cols_sql}
            FROM projects
            WHERE project_year=? AND project_no=?
            """,
            (y, p),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return Project.from_row(dict(row))
    finally:
        conn.close()


# ============================================================
# public（insert）
# ============================================================
def insert_project(
    projects_root: Path,
    *,
    project: Project,
    role: str = "main",
) -> None:
    # ------------------------------------------------------------
    # projects に新規追加
    # ------------------------------------------------------------
    y = normalize_year_4digits(project.project_year)
    p = normalize_pno_3digits(project.project_no)

    db_path = get_project_master_db_path(projects_root, role=role)
    _require_projects_table(db_path)

    payload = project.to_row_dict()
    payload["project_year"] = y
    payload["project_no"] = p

    insert_cols_sql = _sql_cols(_PROJECTS_INSERT_COLS)
    insert_vals_sql = _sql_named_params(_PROJECTS_INSERT_COLS)

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN;")
        conn.execute(
            f"""
            INSERT INTO projects (
              {insert_cols_sql}
            ) VALUES (
              {insert_vals_sql}
            )
            """,
            payload,
        )
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()


# ============================================================
# public（update）
# ============================================================
def update_project(
    projects_root: Path,
    *,
    project: Project,
    role: str = "main",
) -> None:
    # ------------------------------------------------------------
    # projects を更新（主キーは変更しない）
    # - project_year / project_no はキーのため更新しない
    # - input_user_id / input_date は「初回登録情報」として維持する想定
    # - update_user_id / update_date は最終更新情報として更新する
    #
    # 注意：
    # - 現行挙動を変えないため、SET列は _PROJECTS_DATA_COLS をそのまま使う
    #   （＝ input_user_id / input_date も payload の値で上書きされ得る）
    # ------------------------------------------------------------
    y = normalize_year_4digits(project.project_year)
    p = normalize_pno_3digits(project.project_no)

    db_path = get_project_master_db_path(projects_root, role=role)
    _require_projects_table(db_path)

    payload = project.to_row_dict()
    payload["project_year"] = y
    payload["project_no"] = p

    set_clause_sql = _sql_update_set_clause(_PROJECTS_UPDATE_SET_COLS)

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN;")

        conn.execute(
            f"""
            UPDATE projects SET
              {set_clause_sql}
            WHERE project_year = :project_year AND project_no = :project_no
            """,
            payload,
        )

        # ------------------------------------------------------------
        # 更新対象が無い場合はエラー（暗黙に insert しない）
        # ------------------------------------------------------------
        cur = conn.execute("SELECT changes() AS n")
        n = int(dict(cur.fetchone())["n"])  # type: ignore[index]
        if n == 0:
            raise RuntimeError("update対象の projects 行が存在しません（未登録の可能性）。")

        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()