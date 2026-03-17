# common_lib/rag_ingest/ingest_usecase.py
# =============================================================================
# RAG ingest : 1文書取り込み usecase
#
# 役割：
# - 解決済み IngestSource を受け取り、1文書の ingest を最後まで実行する
# - chunk 化
# - embedding 実行
# - meta / processed 生成
# - vectorstore への append
#
# 設計方針：
# - source 解決は adapter 側で済ませてから渡す
# - page 側にロジックを置かない
# - append 前後の整合は vectorstore_io 正本に任せる
# - token / cost は embedding_ops 側で正本記録する
#
# 注意：
# - 本 usecase は「未処理だけ追加」向けの基本処理
# - 既存 doc_id の削除を伴う再投入は rebuild_usecase 側で行う
#
# page 対応の重要方針：
# - page_start / page_end は後付け推定しない
# - source_pages_path の pages 配列を順に連結して ingest 用全文を作る
# - 同時にページ境界表を作り、その全文上の chunk span から
#   page_start / page_end を機械的に決定する
# - これにより、chunk / span / page が同一基準で一致する
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
import json
from pathlib import Path
from typing import Optional

import numpy as np

from .chunk_ops import ChunkOptions, chunk_text
from .embedding_ops import run_embedding_for_chunks
from .manifest_ops import (
    build_meta_record,
    build_processed_file_record,
    utc_now_iso_z,
)
from .models import ChunkRecord, IngestResult, IngestSource, MetaRecord
from .vectorstore_io import (
    append_to_vectorstore,
    get_next_vector_index,
    get_processed_record,
)


# =============================================================================
# helper
# =============================================================================
def _safe_attrs_value(attrs: dict, key: str, default: str = "") -> str:
    # -----------------------------------------------------------------------------
    # attrs から安全に文字列値を取得
    # -----------------------------------------------------------------------------
    if not isinstance(attrs, dict):
        return default
    v = attrs.get(key, default)
    return str(v if v is not None else default)


def _build_ingest_result(
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


def _build_chunk_texts(chunks: list[ChunkRecord]) -> list[str]:
    # -----------------------------------------------------------------------------
    # ChunkRecord 列から embedding 対象テキスト列を作る
    # -----------------------------------------------------------------------------
    return [str(c.text) for c in chunks if str(c.text or "").strip()]


# =============================================================================
# helper : pages json
# =============================================================================
def _resolve_source_pages_abs_path(
    *,
    projects_root: Path,
    source: IngestSource,
) -> Path:
    # -----------------------------------------------------------------------------
    # source_pages_path の実ファイルパスを解決する
    #
    # 現状方針：
    # - project は Archive/project ルート相対
    # - 将来他 collection が増えた場合は adapter 側で path ルールを合わせる
    # -----------------------------------------------------------------------------
    rel = str(source.source_pages_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise RuntimeError("source.source_pages_path が空です。")

    if str(source.collection_id) == "project":
        return Path(projects_root) / "Archive" / "project" / rel

    return Path(projects_root) / rel


def _load_pages_json(
    *,
    pages_json_path: Path,
) -> list[dict]:
    # -----------------------------------------------------------------------------
    # pages json を読み込み、pages 配列を返す
    #
    # 想定形式：
    # {
    #   ...
    #   "pages": [
    #     {"page_no": 1, "text": "..."},
    #     ...
    #   ]
    # }
    # -----------------------------------------------------------------------------
    if not Path(pages_json_path).exists():
        raise RuntimeError(f"pages json が存在しません: {pages_json_path}")

    try:
        payload = json.loads(Path(pages_json_path).read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"pages json の読込に失敗しました: {pages_json_path} : {e}") from e

    if not isinstance(payload, dict):
        raise RuntimeError(f"pages json のトップレベルが dict ではありません: {pages_json_path}")

    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise RuntimeError(f"pages json に pages 配列がありません: {pages_json_path}")

    out: list[dict] = []
    for row in pages:
        if not isinstance(row, dict):
            continue

        page_no = int(row.get("page_no", 0) or 0)
        page_text = str(row.get("text", "") or "")

        if page_no <= 0:
            continue

        out.append(
            {
                "page_no": page_no,
                "text": page_text,
            }
        )

    if not out:
        raise RuntimeError(f"pages json の pages 配列が空です: {pages_json_path}")

    return out


def _build_source_text_and_page_ranges_from_pages(
    *,
    pages: list[dict],
) -> tuple[str, list[dict]]:
    # -----------------------------------------------------------------------------
    # pages 配列から ingest 用全文とページ境界表を作る
    #
    # 方針：
    # - pages[].text を順番にそのまま連結する
    # - 同時に page_no / start / end（end は exclusive）を記録する
    #
    # 戻り値：
    # - full_text
    # - page_ranges
    #
    # page_ranges の各要素：
    #   {
    #     "page_no": 12,
    #     "start": 8980,
    #     "end": 10176,
    #   }
    # -----------------------------------------------------------------------------
    full_text_parts: list[str] = []
    page_ranges: list[dict] = []

    cursor = 0

    for row in pages:
        page_no = int(row.get("page_no", 0) or 0)
        page_text = str(row.get("text", "") or "")

        if page_no <= 0:
            continue

        start = int(cursor)
        full_text_parts.append(page_text)
        cursor += len(page_text)
        end = int(cursor)

        page_ranges.append(
            {
                "page_no": page_no,
                "start": start,
                "end": end,
            }
        )

    if not page_ranges:
        raise RuntimeError("ページ境界表を構築できませんでした。")

    full_text = "".join(full_text_parts)
    return full_text, page_ranges


def _find_page_no_for_char_pos(
    *,
    pos: int,
    page_ranges: list[dict],
) -> int:
    # -----------------------------------------------------------------------------
    # 文字位置 pos を含むページ番号を返す
    #
    # ルール：
    # - start <= pos < end を優先
    # - どれにも入らない場合は、直前ページ / 末尾ページに寄せる
    # - 何も無ければ 0
    # -----------------------------------------------------------------------------
    if not page_ranges:
        return 0

    p = int(pos)

    for row in page_ranges:
        start = int(row["start"])
        end = int(row["end"])
        if start <= p < end:
            return int(row["page_no"])

    prev_page_no = 0
    for row in page_ranges:
        start = int(row["start"])
        if p < start:
            return int(prev_page_no or row["page_no"])
        prev_page_no = int(row["page_no"])

    return int(page_ranges[-1]["page_no"])


def _build_chunk_page_ranges(
    *,
    chunks: list[ChunkRecord],
    page_ranges: list[dict],
) -> list[tuple[int, int]]:
    # -----------------------------------------------------------------------------
    # 各 chunk について (page_start, page_end) を構築する
    #
    # 方針：
    # - chunk.span_start が入る page を page_start にする
    # - chunk.span_end - 1 が入る page を page_end にする
    # - これにより、chunk / span / page が同じ全文基準で一致する
    # -----------------------------------------------------------------------------
    out: list[tuple[int, int]] = []

    for chunk in chunks:
        span_start = int(chunk.span_start)
        span_end = int(chunk.span_end)

        if span_end <= span_start:
            start_pos = span_start
            end_pos = span_start
        else:
            start_pos = span_start
            end_pos = span_end - 1

        page_start = _find_page_no_for_char_pos(
            pos=start_pos,
            page_ranges=page_ranges,
        )
        page_end = _find_page_no_for_char_pos(
            pos=end_pos,
            page_ranges=page_ranges,
        )

        if page_start > 0 and page_end > 0 and page_end < page_start:
            page_end = page_start

        out.append((int(page_start), int(page_end)))

    return out


def _build_meta_records(
    *,
    source: IngestSource,
    chunks: list[ChunkRecord],
    chunk_page_ranges: list[tuple[int, int]],
    start_vector_index: int,
    ingested_at: str,
) -> list[MetaRecord]:
    # -----------------------------------------------------------------------------
    # chunks から MetaRecord 列を生成する
    # vector_index は start_vector_index から連番採番する
    # -----------------------------------------------------------------------------
    out: list[MetaRecord] = []

    if len(chunk_page_ranges) != len(chunks):
        raise RuntimeError(
            "chunk_page_ranges 件数と chunks 件数が一致しません。"
            f" chunks={len(chunks)}, chunk_page_ranges={len(chunk_page_ranges)}"
        )

    for i, chunk in enumerate(chunks):
        page_start, page_end = chunk_page_ranges[i]

        out.append(
            build_meta_record(
                source=source,
                chunk=chunk,
                vector_index=int(start_vector_index) + i,
                page_start=int(page_start),
                page_end=int(page_end),
                ingested_at=ingested_at,
            )
        )

    return out


# =============================================================================
# main
# =============================================================================
def ingest_one_document(
    *,
    projects_root: Path,
    databases_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    source: IngestSource,
    chunk_options: Optional[ChunkOptions] = None,
    skip_if_processed: bool = True,
) -> IngestResult:
    # -----------------------------------------------------------------------------
    # 1文書を ingest する
    #
    # flow:
    # 1. 既存 processed 確認
    # 2. pages json から ingest 用全文 + ページ境界表を構築
    # 3. chunk 化
    # 4. page_start / page_end 計算
    # 5. embedding
    # 6. meta / processed 生成
    # 7. vectorstore へ append
    #
    # 引数：
    # - projects_root:
    #     embedding の busy_run 記録用
    #
    # - databases_root:
    #     Databases ルート
    #
    # - user_sub / app_name / page_name:
    #     busy_run 記録用
    #
    # - source:
    #     adapter 側で解決済みの IngestSource
    #
    # - chunk_options:
    #     chunk 化オプション。None の場合はデフォルト
    #
    # - skip_if_processed:
    #     True の場合、processed 既存なら skip を返す
    #
    # 戻り値：
    # - IngestResult
    # -----------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # 事前チェック
    # -------------------------------------------------------------------------
    if not str(source.collection_id or "").strip():
        raise ValueError("source.collection_id が空です。")

    if not str(source.shard_id or "").strip():
        raise ValueError("source.shard_id が空です。")

    if not str(source.doc_id or "").strip():
        raise ValueError("source.doc_id が空です。")

    if not str(source.source_pages_path or "").strip():
        return _build_ingest_result(
            status="error",
            source=source,
            message="source_pages_path が空のため page 情報を解決できません。",
        )

    # -------------------------------------------------------------------------
    # 既存 processed 確認
    # -------------------------------------------------------------------------
    existing = get_processed_record(
        databases_root=databases_root,
        collection_id=str(source.collection_id),
        shard_id=str(source.shard_id),
        doc_id=str(source.doc_id),
    )

    if skip_if_processed and existing is not None:
        return _build_ingest_result(
            status="skip",
            source=source,
            message="すでに processed 済みのため skip しました。",
        )

    # -------------------------------------------------------------------------
    # pages json 読込
    # -------------------------------------------------------------------------
    pages_json_path = _resolve_source_pages_abs_path(
        projects_root=projects_root,
        source=source,
    )

    pages = _load_pages_json(
        pages_json_path=pages_json_path,
    )

    # -------------------------------------------------------------------------
    # ingest 用全文 + ページ境界表の構築
    # -------------------------------------------------------------------------
    ingest_text, page_ranges = _build_source_text_and_page_ranges_from_pages(
        pages=pages,
    )

    if not str(ingest_text or "").strip():
        return _build_ingest_result(
            status="skip",
            source=source,
            message="pages json から構築した ingest 用全文が空のため ingest を行いません。",
        )

    # -------------------------------------------------------------------------
    # chunk 化
    # -------------------------------------------------------------------------
    chunks = chunk_text(
        str(ingest_text),
        options=chunk_options,
    )

    if not chunks:
        return _build_ingest_result(
            status="skip",
            source=source,
            message="chunk を生成できなかったため skip しました。",
        )

    chunk_texts = _build_chunk_texts(chunks)
    if not chunk_texts:
        return _build_ingest_result(
            status="skip",
            source=source,
            message="有効な chunk テキストが存在しないため skip しました。",
        )

    # -------------------------------------------------------------------------
    # page_start / page_end 計算
    # -------------------------------------------------------------------------
    chunk_page_ranges = _build_chunk_page_ranges(
        chunks=chunks,
        page_ranges=page_ranges,
    )

    # -------------------------------------------------------------------------
    # embedding
    # -------------------------------------------------------------------------
    embed_res = run_embedding_for_chunks(
        projects_root=projects_root,
        user_sub=str(user_sub),
        app_name=str(app_name),
        page_name=str(page_name),
        model_key=str(source.embed_model),
        chunk_texts=chunk_texts,
        feature=f"rag_ingest:{source.collection_id}",
        meta={
            "collection_id": str(source.collection_id),
            "shard_id": str(source.shard_id),
            "doc_id": str(source.doc_id),
            "file_name": str(source.file_name),
            "source_text_kind": str(source.source_text_kind),
            "chunk_count": len(chunks),
            "source_chars": len(str(ingest_text or "")),
            "attrs": dict(source.attrs or {}),
        },
    )

    if len(embed_res.vectors) != len(chunks):
        return _build_ingest_result(
            status="error",
            source=source,
            message=(
                "embedding 結果件数と chunk 件数が一致しません。"
                f" chunk_count={len(chunks)}, vector_count={len(embed_res.vectors)}"
            ),
            chunk_count=len(chunks),
            vector_count=len(embed_res.vectors),
        )

    # -------------------------------------------------------------------------
    # meta / processed 作成
    # -------------------------------------------------------------------------
    ingested_at = utc_now_iso_z()

    start_vector_index = get_next_vector_index(
        databases_root=databases_root,
        collection_id=str(source.collection_id),
        shard_id=str(source.shard_id),
    )

    meta_records = _build_meta_records(
        source=source,
        chunks=chunks,
        chunk_page_ranges=chunk_page_ranges,
        start_vector_index=start_vector_index,
        ingested_at=ingested_at,
    )

    processed_record = build_processed_file_record(
        source=source,
        ingested_at=ingested_at,
    )

    # -------------------------------------------------------------------------
    # vectors 変換
    # -------------------------------------------------------------------------
    new_vectors = np.asarray(embed_res.vectors, dtype=np.float32)

    # -------------------------------------------------------------------------
    # append
    # -------------------------------------------------------------------------
    append_to_vectorstore(
        databases_root=databases_root,
        collection_id=str(source.collection_id),
        shard_id=str(source.shard_id),
        new_vectors=new_vectors,
        new_meta_records=meta_records,
        new_processed_record=processed_record,
    )

    # -------------------------------------------------------------------------
    # 完了
    # -------------------------------------------------------------------------
    msg = (
        "ingest 完了"
        f" | chunks={len(meta_records)}"
        f" | vectors={len(embed_res.vectors)}"
        f" | model={source.embed_model}"
        f" | source={source.source_text_kind}"
    )

    return _build_ingest_result(
        status="ok",
        source=source,
        message=msg,
        chunk_count=len(meta_records),
        vector_count=len(embed_res.vectors),
    )