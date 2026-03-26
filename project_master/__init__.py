# common_lib/project_master/__init__.py
# ------------------------------------------------------------
# Project Master（高レベルAPI）
# - パス解決 / スキーマ初期化 / projects CRUD / 状態判定
# - 報告書PDF本体操作
# - 報告書OCR / text / clean 操作
# - 処理状態（text/processing_status.json）操作
# ------------------------------------------------------------

from common_lib.project_master.paths import (
    # ------------------------------------------------------------
    # paths（正本）
    # ------------------------------------------------------------
    ProjectMasterPaths,
    get_archive_root,
    get_project_master_root,
    get_project_master_db_path,
    get_project_master_paths,
    normalize_year_4digits,
    normalize_pno_3digits,
    get_project_root_dir,
    get_project_pdf_dir,
    get_project_ocr_dir,
    get_project_text_dir,
    get_project_others_dir,
    get_project_contract_dir,
    get_project_pdf_status_json_path,
)

from common_lib.project_master.models import (
    # ------------------------------------------------------------
    # models
    # ------------------------------------------------------------
    Project,
)

from common_lib.project_master.schema import (
    # ------------------------------------------------------------
    # schema（init）
    # ------------------------------------------------------------
    init_project_master_db,
)

from common_lib.project_master.projects_repo import (
    # ------------------------------------------------------------
    # repository（CRUD）
    # ------------------------------------------------------------
    get_project,
    insert_project,
    update_project,
)

from common_lib.project_master.report_pdf_ops import (
    # ------------------------------------------------------------
    # report pdf（正本API）
    # ------------------------------------------------------------
    get_report_pdf_path,
    upsert_report_pdf,
    delete_report_pdf,
    set_pdf_lock,
    clear_pdf_lock,
    get_report_pdf_bytes_and_sha256,
    get_pdf_page_count_from_bytes,
    render_pdf_page_png_simple_from_bytes,
)

from common_lib.project_master.report_ocr_ops import (
    # ------------------------------------------------------------
    # report ocr / text / clean（正本API）
    # ------------------------------------------------------------
    REPORT_RAW_TXT_NAME,
    REPORT_CLEAN_TXT_NAME,
    EXTRACT_META_JSON_NAME,
    OCR_PDF_SUFFIX,
    run_report_ocr_pipeline,
    run_report_clean_only,
)

from common_lib.project_master.state import (
    # ------------------------------------------------------------
    # state（UI）
    # ------------------------------------------------------------
    StateResult,
    calc_state,
    STATE_S0_NOT_REGISTERED,
    STATE_S1_REGISTERED,
    STATE_S3_PDF_LOCKED,
    STATE_S4_RAG_INGESTED,
)

from common_lib.project_master.pdf_status_ops import (
    # ------------------------------------------------------------
    # pdf status ops（pdf/pdf_status.json）
    # ------------------------------------------------------------
    PDF_STATUS_FILENAME,
    ReportPdfListItem,
    get_pdf_status_path,
    read_pdf_status,
    write_pdf_status,
    list_years_with_report_pdf,
    list_report_pdfs_by_year,
)

from common_lib.project_master.processing_status_ops import (
    PROCESSING_STATUS_FILENAME,
    PDF_KIND_TEXT,
    PDF_KIND_IMAGE,
    ProcessingStatusRecord,
    get_processing_status_path,
    read_processing_status,
    write_processing_status,
    reset_processing_status,
    delete_processing_status,
    upsert_pdf_info_status,
    mark_ocr_done,
    mark_text_extracted,
    mark_cleaned,
    matches_source_pdf,
)

from common_lib.project_master.report_check_ops import (
    # ------------------------------------------------------------
    # report check（103ページ用）
    # ------------------------------------------------------------
    REPORT_RAW_TXT_NAME,
    ACTION_SKIPPED,
    ACTION_PROCESSED_TEXT_PDF,
    ACTION_PROCESSED_IMAGE_PDF,
    ACTION_ERROR,
    ReportCheckItemResult,
    ReportCheckYearResult,
    check_one_report_pdf,
    check_report_pdfs_by_year,
)

# ------------------------------------------------------------
# report display status ops
# ------------------------------------------------------------
from .report_display_status_ops import (
    ReportDisplayStatus,
    build_report_display_status,
)