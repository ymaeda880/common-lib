# common_lib/rag_ingest/rebuild_usecase.py
# =============================================================================
# RAG ingest : 再投入 usecase
#
# 役割：
# - 指定 doc_id の既存 chunk / processed を vectorstore から削除する
# - その後、同じ source を使って再 ingest する
#
# 設計方針：
# - 再投入は「削除 -> 再 ingest」の順で行う
# - 削除対象の識別は共通基盤では doc_id を正本とする
# - project の場合、実質的には year/pno/pdf_filename に対応するが、
#   ここではあくまで doc_id 単位で扱う
#
# 注意：
# - 本 usecase は source 解決済みの IngestSource を受け取る
# - source 解決は adapter 側で行う
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from pathlib import Path
from typing import Optional

from .chunk_ops import ChunkOptions
from .ingest_usecase import ingest_one_document
from .models import IngestResult, IngestSource
from .vectorstore_io import delete_doc_id_from_vectorstore, get_processed_record


# =============================================================================
# helper
# =============================================================================
def _build_result(
    *,
    status: str,
    source: IngestSource,
    message: str,
    chunk_count: int = 0,
    vector_count: int = 0,
) -> IngestResult:
    # -----------------------------------------------------------------------------
    # IngestResult を組み立てる
    # -----------------------------------------------------------------------------
    return IngestResult(
        status=status,  # type: ignore[arg-type]
        collection_id=str(source.collection_id),
        shard_id=str(source.shard_id),
        doc_id=str(source.doc_id),
        file=str(source.file),
        file_name=str(source.file_name),
        message=str(message),
        chunk_count=int(chunk_count),
        vector_count=int(vector_count),
        source_text_kind=str(source.source_text_kind),
        source_text_path=str(source.source_text_path),
        source_pdf_path=str(source.source_pdf_path),
        sha256=str(source.sha256),
        embed_model=str(source.embed_model),
        attrs=dict(source.attrs or {}),
    )


# =============================================================================
# main
# =============================================================================
def rebuild_one_document(
    *,
    projects_root: Path,
    databases_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    source: IngestSource,
    chunk_options: Optional[ChunkOptions] = None,
    delete_even_if_not_processed: bool = True,
) -> IngestResult:
    # -----------------------------------------------------------------------------
    # 1文書を再投入する
    #
    # flow:
    # 1. 既存 processed を確認
    # 2. 必要なら vectorstore から doc_id を削除
    # 3. ingest_one_document(skip_if_processed=False) を実行
    #
    # 引数：
    # - delete_even_if_not_processed:
    #     True なら processed 未登録でも削除処理を実行する
    #     False なら processed 未登録時は削除を省略する
    #
    # 戻り値：
    # - IngestResult
    # -----------------------------------------------------------------------------
    if not str(source.doc_id or "").strip():
        raise ValueError("source.doc_id が空です。")

    # -------------------------------------------------------------------------
    # 既存 processed 確認
    # -------------------------------------------------------------------------
    existing = get_processed_record(
        databases_root=databases_root,
        collection_id=str(source.collection_id),
        shard_id=str(source.shard_id),
        doc_id=str(source.doc_id),
    )

    # -------------------------------------------------------------------------
    # 削除
    # -------------------------------------------------------------------------
    if existing is not None or bool(delete_even_if_not_processed):
        delete_doc_id_from_vectorstore(
            databases_root=databases_root,
            collection_id=str(source.collection_id),
            shard_id=str(source.shard_id),
            doc_id=str(source.doc_id),
        )

    # -------------------------------------------------------------------------
    # 再 ingest
    # -------------------------------------------------------------------------
    try:
        res = ingest_one_document(
            projects_root=projects_root,
            databases_root=databases_root,
            user_sub=str(user_sub),
            app_name=str(app_name),
            page_name=str(page_name),
            source=source,
            chunk_options=chunk_options,
            skip_if_processed=False,
        )
    except Exception as e:
        return _build_result(
            status="error",
            source=source,
            message=f"再投入エラー: {e}",
        )

    if res.status == "ok":
        msg = (
            "再投入完了"
            f" | chunks={res.chunk_count}"
            f" | vectors={res.vector_count}"
            f" | model={source.embed_model}"
            f" | source={source.source_text_kind}"
        )
        return _build_result(
            status="ok",
            source=source,
            message=msg,
            chunk_count=res.chunk_count,
            vector_count=res.vector_count,
        )

    if res.status == "skip":
        return _build_result(
            status="skip",
            source=source,
            message=f"再投入 skip: {res.message}",
            chunk_count=res.chunk_count,
            vector_count=res.vector_count,
        )

    return _build_result(
        status="error",
        source=source,
        message=f"再投入失敗: {res.message}",
        chunk_count=res.chunk_count,
        vector_count=res.vector_count,
    )