# common_lib/rag_ingest/__init__.py
# =============================================================================
# RAG ingest（高レベルAPI）
#
# 役割：
# - rag_ingest 配下の主要APIの公開入口
# - page / app 側は本ファイル経由で import できるようにする
# =============================================================================

from common_lib.rag_ingest.processed_status_ops import (
    get_processed_doc_id_set,
)

from common_lib.rag_ingest.project.ingest_status_ops import (
    get_project_processed_doc_id_set,
    resolve_project_report_doc_id,
    is_project_report_ingested,
    is_project_ingested,
)