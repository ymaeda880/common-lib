# common_lib/project_master/schema.py
# ============================================================
# Project Master : DBスキーマ定義モジュール
#
# ■ 目的
# project_master.db のスキーマ定義および初期化を担う。
# projects テーブル（開発中の正本DDL）を定義する。
#
# ■ 設計方針
# 1. 暗黙生成は禁止
#    - DBは自動作成しない
#    - init_project_master_db() が明示的に呼ばれた場合のみ作成する
#
# 2. スキーマ定義は本ファイルを正本とする
#    - CREATE TABLE はここに集約
#    - 他モジュールにDDLを書かない
#
# 3. 現フェーズの範囲
#    - projects テーブルのみ作成
#    - 詳細テーブル（report / attachments / audit 等）は別フェーズで追加予定
#
# ■ projectsテーブルの責務
#
# (1) 基本情報
#     - project_year
#     - project_no
#     - project_name
#     - client_name
#     - main_department
#     - contract_amount  : 契約金額（円単位・INTEGER管理）
#
# (2) 登録・更新情報
#     - input_user_id  : 初回登録者（CRUDで上書きしない）
#     - input_date     : 登録日時
#     - update_user_id : 最終更新者
#     - update_date    : 最終更新日時
#
# (3) PDF確定ロック（入力者判断）
#     - pdf_lock_flag  : PDF確定ロック（0/1）
#     - pdf_locked_at  : ロック日時
#     - pdf_locked_by  : ロック実行者（ユーザーID）
#
# PRIMARY KEY:
#     (project_year, project_no)
#
# ■ インデックス方針
#     client_name
#     main_department
#     project_name
#     pdf_lock_flag
#
# 検索UIで使用頻度の高いカラムに付与する。
#
# ■ 初期化関数の動作
#     - DBディレクトリが無ければ作成
#     - トランザクション内でDDL実行
#     - 失敗時はROLLBACK
#     - 成功時のみCOMMIT
#     - journal_mode=WAL を有効化
#
# ■ 注意
#     本モジュールは「スキーマ専用」。
#     CRUDロジックは別モジュールで実装すること。
# ============================================================


# ------------------------------------------------------------
# PDF確定ロック（pdf_lock_*）の設計ポリシー
# ------------------------------------------------------------
#
# ■ 目的
# - PDFが確定した段階で、入力者（担当者）が「確定ロック」をかけられるようにする
# - ロック後の変更禁止（どの項目を禁止するか）は CRUD正本で統制する
#
# ■ 運用ルール（推奨）
# - pdf_lock_flag=1 のとき、pdf_locked_at / pdf_locked_by は NULL にしない
# - ロック解除を許すかどうかは運用で決める（解除ログが必要なら別テーブルで管理）
#
# ------------------------------------------------------------


# ------------------------------------------------------------
# 契約金額（contract_amount）の設計ポリシー
# ------------------------------------------------------------
#
# - 円単位 INTEGER で管理する（小数誤差回避）
# - NOT NULL
# - 未入力状態は 0 で管理
# - 会計・集計用途を想定し、数値計算可能な形で保持する
#
# ------------------------------------------------------------


from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import sqlite3
from pathlib import Path

# ============================================================
# imports（common_lib/project_master）
# ============================================================
from common_lib.project_master.paths import get_project_master_db_path


# ============================================================
# DDL（projects）
# ============================================================
DDL_PROJECTS = """
CREATE TABLE IF NOT EXISTS projects (
    project_year        INTEGER NOT NULL,
    project_no          TEXT    NOT NULL,

    project_name        TEXT    NOT NULL DEFAULT '',
    client_name         TEXT    NOT NULL DEFAULT '',
    main_department     TEXT    NOT NULL DEFAULT '',

    contract_amount     INTEGER NOT NULL DEFAULT 0,

    input_user_id       TEXT    NOT NULL,
    input_date          TEXT    NOT NULL,

    update_user_id      TEXT    NOT NULL,
    update_date         TEXT    NOT NULL,

    pdf_lock_flag       INTEGER NOT NULL DEFAULT 0,
    pdf_locked_at       TEXT    NULL,
    pdf_locked_by       TEXT    NULL,

    -- --------------------------------------------------------
    -- 報告書PDFメタ（A案：projectsに保持）
    -- - 1プロジェクトにつきPDFは1本（運用/CRUD正本で保証）
    -- - 未登録は NULL を許容
    -- --------------------------------------------------------
    report_pdf_original_filename   TEXT    NULL,
    report_pdf_stored_filename     TEXT    NULL,
    report_pdf_hash_sha256         TEXT    NULL,
    report_pdf_size_bytes          INTEGER NULL,
    report_pdf_saved_at            TEXT    NULL,
    report_pdf_saved_by            TEXT    NULL,

    PRIMARY KEY (project_year, project_no)
);
"""

DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_projects_client_name
ON projects(client_name);

CREATE INDEX IF NOT EXISTS idx_projects_main_department
ON projects(main_department);

CREATE INDEX IF NOT EXISTS idx_projects_project_name
ON projects(project_name);

CREATE INDEX IF NOT EXISTS idx_projects_pdf_lock_flag
ON projects(pdf_lock_flag);
"""


# ============================================================
# helpers（db）
# ============================================================
def _connect(db_path: Path) -> sqlite3.Connection:
    # ------------------------------------------------------------
    # sqlite connect（外部利用禁止）
    # ------------------------------------------------------------
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def table_exists(db_path: Path, *, table_name: str) -> bool:
    # ------------------------------------------------------------
    # テーブル存在確認
    # ------------------------------------------------------------
    if not db_path.exists():
        return False

    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        row = cur.fetchone()
        return row is not None
    finally:
        conn.close()


# ============================================================
# public（init）
# ============================================================
def init_project_master_db(projects_root: Path, *, role: str = "main") -> Path:
    # ------------------------------------------------------------
    # project_master.db を初期化（明示的に呼ぶ）
    #
    # 方針：
    # - 暗黙に作らない（呼んだ時だけ作る）
    # - DBディレクトリが無い場合は作る
    # - projects（現フェーズ）を作成
    # ------------------------------------------------------------
    db_path = get_project_master_db_path(projects_root, role=role)
    db_dir = db_path.parent
    db_dir.mkdir(parents=True, exist_ok=True)

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN;")
        conn.execute(DDL_PROJECTS)

        for stmt in DDL_INDEXES.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s + ";")

        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()

    return db_path