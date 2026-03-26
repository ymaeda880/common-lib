# common_lib/pdf_catalog/__init__.py
# =============================================================================
# 汎用PDFカタログ（共通ライブラリ）
#
# 役割：
# - project 以外の汎用PDFコレクション用の path / scan / status を提供する
# - Archive/<collection_id>/pdfs/<shard_id>/ 配下のPDF群を入口として扱う
# - 展開先は Archive/<collection_id>/<shard_id>/<doc_id>/... を前提とする
#
# 公開API：
# - paths
# - scan
# - status
# =============================================================================

from .paths import (
    get_collection_root,
    get_pdfs_root,
    get_shard_pdfs_dir,
    get_doc_root,
    get_doc_pdf_dir,
    get_doc_text_dir,
    get_doc_ocr_dir,
    get_doc_others_dir,
    get_doc_pdf_status_path,
    get_doc_processing_status_path,
    get_source_pdf_path,
    ensure_doc_layout_dirs,
)

from .scan import (
    GenericPdfSourceRecord,
    list_collection_ids_with_pdfs,
    list_shard_ids_with_source_pdfs,
    list_source_pdfs_by_shard,
)

from .status import (
    GenericPdfDisplayStatus,
    read_generic_pdf_status,
    read_generic_processing_status,
    build_generic_pdf_display_status,
)

from .processing_status_ops import (
    GenericProcessingStatusRecord,
    get_processing_status_path,
    read_processing_status,
    write_processing_status,
    reset_processing_status,
    delete_processing_status,
    upsert_pdf_info_status,
    mark_ocr_done,
    mark_text_extracted,
    mark_cleaned,
    mark_error,
    upsert_error_status,
    get_processing_status_for_state,
    matches_source_pdf,
)