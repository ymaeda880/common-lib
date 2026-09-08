# common_lib/project_master/export_labels.py
# ============================================================
# Project Master labels（共通ラベル正本）
#
# 機能：
# - Project Master のDBカラム名に対応する共通表示ラベルを管理する
# - 画面表示・Excel出力などで同じラベルを使用する
# - 各page / app側に表示ラベルを重複定義しない
# ============================================================

from __future__ import annotations


# ============================================================
# DBカラム名 → 共通表示ラベル
# ============================================================

PROJECT_COLUMN_LABELS: dict[str, str] = {
    "project_year": "年度",
    "project_no": "番号",
    "project_name": "プロジェクト名",
    "project_short_name": "プロジェクト略称",
    "client_name": "発注者",
    "main_department": "主幹部署",
    "contract_amount": "契約金額",
    "confidential_flag": "社外秘",
    "input_user_id": "入力者ID",
    "input_date": "入力日",
    "update_user_id": "更新者ID",
    "update_date": "更新日",
    "pdf_lock_flag": "PDFロック",
    "pdf_locked_at": "PDFロック日時",
    "pdf_locked_by": "PDFロック者",
    "rag_ingested_flag": "RAG取込",
    "rag_ingested_at": "RAG取込日時",
    "rag_ingested_by": "RAG取込者",
    "report_pdf_original_filename": "報告書ファイル名",
    "report_pdf_stored_filename": "報告書PDF保存ファイル名",
    "report_pdf_hash_sha256": "報告書PDFハッシュ値",
    "report_pdf_size_bytes": "報告書PDFサイズ",
    "report_pdf_saved_at": "報告書PDF保存日時",
    "report_pdf_saved_by": "報告書PDF保存者",
}


# ============================================================
# 画面一覧等で使用する追加ラベル
# ============================================================

PROJECT_LIST_EXTRA_LABELS: dict[str, str] = {
    "state": "状態",
    "contract_filename": "契約書ファイル名",
    "lock_status": "ロック状況",
    "rag_status": "RAG取り込み状況",
}


# ============================================================
# RAG根拠情報で使用する追加ラベル
# ============================================================

PROJECT_REFERENCE_LABELS: dict[str, str] = {
    "year": PROJECT_COLUMN_LABELS["project_year"],
    "pno": PROJECT_COLUMN_LABELS["project_no"],
    "reference_id": "参照番号",
    "project_name": PROJECT_COLUMN_LABELS["project_name"],
    "project_short_name": PROJECT_COLUMN_LABELS["project_short_name"],
    "client_name": PROJECT_COLUMN_LABELS["client_name"],
    "main_department": PROJECT_COLUMN_LABELS["main_department"],
    "file_name": PROJECT_COLUMN_LABELS["report_pdf_original_filename"],
    "page_start": "開始頁",
    "page_end": "終了頁",
}


# ============================================================
# 共通ラベル取得
# ============================================================

def get_project_column_label(column: str) -> str:
    # ------------------------------------------------------------
    # Project Master の共通表示ラベルを返す
    # 未定義の場合は元のカラム名をそのまま返す
    # ------------------------------------------------------------
    key = str(column)

    if key in PROJECT_COLUMN_LABELS:
        return PROJECT_COLUMN_LABELS[key]

    if key in PROJECT_LIST_EXTRA_LABELS:
        return PROJECT_LIST_EXTRA_LABELS[key]

    if key in PROJECT_REFERENCE_LABELS:
        return PROJECT_REFERENCE_LABELS[key]

    return key


# ============================================================
# DataFrame表示用ラベル生成
# ============================================================

def build_project_column_label_map(
    columns: list[str] | tuple[str, ...],
) -> dict[str, str]:
    # ------------------------------------------------------------
    # DataFrame.rename(columns=...) に渡すdictを生成する
    # ------------------------------------------------------------
    return {
        str(c): get_project_column_label(str(c))
        for c in columns
    }


# ============================================================
# Excelヘッダー生成
# ============================================================

def build_project_export_header_labels(
    columns: list[str] | tuple[str, ...],
) -> list[str]:
    # ------------------------------------------------------------
    # columns の順番を正本として表示ラベルを生成する
    # ------------------------------------------------------------
    return [
        get_project_column_label(str(c))
        for c in columns
    ]