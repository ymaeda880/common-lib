# common_lib/rag_ingest/batch_usecase.py
# =============================================================================
# RAG ingest : 複数文書バッチ実行 usecase
#
# 役割：
# - 複数の IngestSource をまとめて処理する
# - 実行モードに応じて
#     - 未処理だけ追加
#     - 再投入
#   を切り替える
# - 各文書の結果を BatchIngestResult に集計して返す
#
# 設計方針：
# - page 側には for ループの業務ロジックを置かない
# - 1件処理は ingest_usecase / rebuild_usecase に委譲する
# - バッチ全体は「止めずに続ける」を基本とする
# - 1件失敗しても、他の文書は処理継続する
#
# 注意：
# - progress 表示そのものは page 側で行う想定
# - 本 usecase は結果集計と処理分岐を担当する
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from pathlib import Path
from typing import Iterable, Literal, Optional, Sequence

from .chunk_ops import ChunkOptions
from .ingest_usecase import ingest_one_document
from .models import BatchIngestResult, IngestResult, IngestSource
from .rebuild_usecase import rebuild_one_document


# =============================================================================
# type
# =============================================================================
BatchMode = Literal["append_unprocessed", "rebuild_selected"]


# =============================================================================
# helper
# =============================================================================
def normalize_batch_mode(mode: str) -> BatchMode:
    # -----------------------------------------------------------------------------
    # バッチ実行モードを正規化する
    # -----------------------------------------------------------------------------
    v = str(mode or "").strip().lower()

    if v == "append_unprocessed":
        return "append_unprocessed"

    if v == "rebuild_selected":
        return "rebuild_selected"

    raise ValueError(
        "batch mode が不正です。"
        " 'append_unprocessed' または 'rebuild_selected' を指定してください。"
    )


def _build_error_result_from_source(
    *,
    source: IngestSource,
    message: str,
) -> IngestResult:
    # -----------------------------------------------------------------------------
    # source から error 結果を組み立てる
    # -----------------------------------------------------------------------------
    return IngestResult(
        status="error",
        collection_id=str(source.collection_id),
        shard_id=str(source.shard_id),
        doc_id=str(source.doc_id),
        file=str(source.file),
        file_name=str(source.file_name),
        message=str(message),
        chunk_count=0,
        vector_count=0,
        source_text_kind=str(source.source_text_kind),
        source_text_path=str(source.source_text_path),
        source_pdf_path=str(source.source_pdf_path),
        sha256=str(source.sha256),
        embed_model=str(source.embed_model),
        attrs=dict(source.attrs or {}),
    )


def _dedupe_sources_by_doc_id(
    sources: Sequence[IngestSource],
) -> list[IngestSource]:
    # -----------------------------------------------------------------------------
    # 同一 doc_id の重複 source を除去する
    #
    # 方針：
    # - 先勝ち
    # - 順序は保持する
    # -----------------------------------------------------------------------------
    out: list[IngestSource] = []
    seen: set[str] = set()

    for src in sources:
        doc_id = str(src.doc_id or "").strip()
        if not doc_id:
            continue

        if doc_id in seen:
            continue

        seen.add(doc_id)
        out.append(src)

    return out


# =============================================================================
# 1件 dispatch
# =============================================================================
def run_one_by_mode(
    *,
    projects_root: Path,
    databases_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    source: IngestSource,
    mode: BatchMode,
    chunk_options: Optional[ChunkOptions] = None,
) -> IngestResult:
    # -----------------------------------------------------------------------------
    # mode に応じて 1件処理を切り替える
    # -----------------------------------------------------------------------------
    if mode == "append_unprocessed":
        return ingest_one_document(
            projects_root=projects_root,
            databases_root=databases_root,
            user_sub=str(user_sub),
            app_name=str(app_name),
            page_name=str(page_name),
            source=source,
            chunk_options=chunk_options,
            skip_if_processed=True,
        )

    if mode == "rebuild_selected":
        return rebuild_one_document(
            projects_root=projects_root,
            databases_root=databases_root,
            user_sub=str(user_sub),
            app_name=str(app_name),
            page_name=str(page_name),
            source=source,
            chunk_options=chunk_options,
            delete_even_if_not_processed=True,
        )

    raise ValueError(f"未対応の mode です: {mode}")


# =============================================================================
# main
# =============================================================================
def run_batch_ingest(
    *,
    projects_root: Path,
    databases_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    sources: Sequence[IngestSource],
    mode: str,
    chunk_options: Optional[ChunkOptions] = None,
    dedupe_by_doc_id: bool = True,
) -> BatchIngestResult:
    # -----------------------------------------------------------------------------
    # 複数 source をまとめて処理する
    #
    # 引数：
    # - mode:
    #     "append_unprocessed"
    #     "rebuild_selected"
    #
    # - dedupe_by_doc_id:
    #     True の場合、同一 doc_id の重複 source は先勝ちで除去する
    #
    # 戻り値：
    # - BatchIngestResult
    #
    # 方針：
    # - 1件失敗しても残りを継続
    # - 個別結果は全部 result に入れる
    # -----------------------------------------------------------------------------
    batch_mode = normalize_batch_mode(mode)

    src_list = list(sources or [])
    if dedupe_by_doc_id:
        src_list = _dedupe_sources_by_doc_id(src_list)

    result = BatchIngestResult()

    for src in src_list:
        try:
            one = run_one_by_mode(
                projects_root=projects_root,
                databases_root=databases_root,
                user_sub=str(user_sub),
                app_name=str(app_name),
                page_name=str(page_name),
                source=src,
                mode=batch_mode,
                chunk_options=chunk_options,
            )
        except Exception as e:
            one = _build_error_result_from_source(
                source=src,
                message=f"バッチ処理中に例外が発生しました: {e}",
            )

        result.add(one)

    return result


# =============================================================================
# convenience
# =============================================================================
def run_batch_append_unprocessed(
    *,
    projects_root: Path,
    databases_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    sources: Sequence[IngestSource],
    chunk_options: Optional[ChunkOptions] = None,
    dedupe_by_doc_id: bool = True,
) -> BatchIngestResult:
    # -----------------------------------------------------------------------------
    # 未処理だけ追加
    # -----------------------------------------------------------------------------
    return run_batch_ingest(
        projects_root=projects_root,
        databases_root=databases_root,
        user_sub=user_sub,
        app_name=app_name,
        page_name=page_name,
        sources=sources,
        mode="append_unprocessed",
        chunk_options=chunk_options,
        dedupe_by_doc_id=dedupe_by_doc_id,
    )


def run_batch_rebuild_selected(
    *,
    projects_root: Path,
    databases_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    sources: Sequence[IngestSource],
    chunk_options: Optional[ChunkOptions] = None,
    dedupe_by_doc_id: bool = True,
) -> BatchIngestResult:
    # -----------------------------------------------------------------------------
    # 選択文書を再投入
    # -----------------------------------------------------------------------------
    return run_batch_ingest(
        projects_root=projects_root,
        databases_root=databases_root,
        user_sub=user_sub,
        app_name=app_name,
        page_name=page_name,
        sources=sources,
        mode="rebuild_selected",
        chunk_options=chunk_options,
        dedupe_by_doc_id=dedupe_by_doc_id,
    )