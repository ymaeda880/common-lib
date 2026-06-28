# common_lib/project_master/export_labels.py
# ============================================================
# Project Master export labels（共通ラベル正本）
# ============================================================

from __future__ import annotations

# ============================================================
# DBカラム名 → 表示ラベル
# ============================================================
PROJECT_EXPORT_COLUMN_LABELS: dict[str, str] = {
    "project_year": "プロジェクト年度",
    "project_no": "プロジェクト番号",
    "project_name": "プロジェクト名",
    "project_short_name": "プロジェクト略称",
    "client_name": "発注者",
    "main_department": "主幹部署",
    "contract_amount": "契約金額",
    "confidential_flag": "社外秘フラグ",
    "input_user_id": "入力者ID",
    "input_date": "入力日",
    "update_user_id": "更新者ID",
    "update_date": "更新日",
    "pdf_lock_flag": "PDFロックフラグ",
    "pdf_locked_at": "PDFロック日時",
    "pdf_locked_by": "PDFロック者",
    "rag_ingested_flag": "RAG取込フラグ",
    "rag_ingested_at": "RAG取込日時",
    "rag_ingested_by": "RAG取込者",
    "report_pdf_original_filename": "報告書PDF元ファイル名",
    "report_pdf_stored_filename": "報告書PDF保存ファイル名",
    "report_pdf_hash_sha256": "報告書PDFハッシュ値",
    "report_pdf_size_bytes": "報告書PDFサイズ",
    "report_pdf_saved_at": "報告書PDF保存日時",
    "report_pdf_saved_by": "報告書PDF保存者",
}


# ============================================================
# Excelヘッダー生成
# ============================================================
def build_project_export_header_labels(
    columns: list[str] | tuple[str, ...],
) -> list[str]:
    # ------------------------------------------------------------
    # columns の順番を正本として、表示ラベルを生成する
    # ------------------------------------------------------------
    return [
        PROJECT_EXPORT_COLUMN_LABELS.get(str(c), str(c))
        for c in columns
    ]