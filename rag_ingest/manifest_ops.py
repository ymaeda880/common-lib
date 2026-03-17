# common_lib/rag_ingest/manifest_ops.py
# =============================================================================
# RAG ingest : manifest / metadata 正本ロジック
#
# 役割：
# - doc_id / chunk_id の命名規則を正本として管理する
# - MetaRecord を生成する
# - ProcessedFileRecord を生成する
# - meta.jsonl / processed_files.json 用 dict を安定して出力する
#
# 設計方針：
# - 共通基盤では year / pno を固定項目にしない
# - collection 固有情報は attrs に持たせる
# - chunk_id は page依存にしない
# - chunk_id は <doc_id>#cXXXXXX の形式とする
# - source path はルート相対パス文字列を前提とする
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .models import ChunkRecord, IngestSource, MetaRecord, ProcessedFileRecord


# =============================================================================
# 定数
# =============================================================================
DEFAULT_CHUNK_ID_WIDTH = 6


# =============================================================================
# helper : time
# =============================================================================
def utc_now_iso_z() -> str:
    # -----------------------------------------------------------------------------
    # UTC現在時刻を ISO 8601 + Z 形式で返す
    #
    # 例：
    #   2025-10-04T00:30:50Z
    # -----------------------------------------------------------------------------
    dt = datetime.now(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


# =============================================================================
# helper : attrs
# =============================================================================
def normalize_attrs(attrs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    # -----------------------------------------------------------------------------
    # attrs を dict に正規化する
    # -----------------------------------------------------------------------------
    if isinstance(attrs, dict):
        return dict(attrs)
    return {}


# =============================================================================
# doc_id
# =============================================================================
def build_doc_id(*parts: str) -> str:
    # -----------------------------------------------------------------------------
    # doc_id を "/" 連結で作る
    #
    # 例：
    #   build_doc_id("2019", "009", "xxx.pdf")
    #   -> "2019/009/xxx.pdf"
    #
    # 注意：
    # - parts には空文字を入れない
    # - OS依存 separator ではなく "/" に統一する
    # -----------------------------------------------------------------------------
    cleaned = []
    for p in parts:
        s = str(p or "").strip().replace("\\", "/").strip("/")
        if not s:
            raise ValueError("doc_id の構成要素に空文字は使えません。")
        cleaned.append(s)
    return "/".join(cleaned)


# =============================================================================
# file_name
# =============================================================================
def build_file_name_from_file(file_path_like: str) -> str:
    # -----------------------------------------------------------------------------
    # file / doc_id から file_name を取り出す
    # -----------------------------------------------------------------------------
    s = str(file_path_like or "").replace("\\", "/").strip()
    if not s:
        raise ValueError("file_name を取り出す元の path が空です。")
    return Path(s).name


# =============================================================================
# chunk_id
# =============================================================================
def build_chunk_id(
    doc_id: str,
    chunk_index: int,
    width: int = DEFAULT_CHUNK_ID_WIDTH,
) -> str:
    # -----------------------------------------------------------------------------
    # chunk_id を作る
    #
    # 形式：
    #   <doc_id>#cXXXXXX
    #
    # 例：
    #   2019/009/xxx.pdf#c000001
    #
    # 注意：
    # - chunk_index は 0 以上
    # - 表示上わかりやすくするため 1-based 表現で埋め込む
    #   ただし元の chunk_index 自体は 0-based のまま保持する
    # -----------------------------------------------------------------------------
    if not str(doc_id or "").strip():
        raise ValueError("doc_id が空のため chunk_id を作れません。")

    if int(chunk_index) < 0:
        raise ValueError("chunk_index は 0 以上である必要があります。")

    serial = int(chunk_index) + 1
    return f"{doc_id}#c{serial:0{int(width)}d}"


# =============================================================================
# source text kind
# =============================================================================
def normalize_source_text_kind(source_text_kind: str) -> str:
    # -----------------------------------------------------------------------------
    # source_text_kind を正規化する
    # -----------------------------------------------------------------------------
    v = str(source_text_kind or "").strip().lower()
    if v in ("raw", "clean", "other"):
        return v
    if not v:
        return "other"
    return "other"


# =============================================================================
# source path
# =============================================================================
def normalize_relative_path(path_like: str) -> str:
    # -----------------------------------------------------------------------------
    # ルート相対パス文字列として正規化する
    #
    # 方針：
    # - backslash は slash に統一
    # - 前後の空白除去
    # - 先頭 / は除去
    #
    # 注意：
    # - 絶対パス禁止まではここでは強制しない
    #   （adapter / caller 側でルート相対パスを渡す運用）
    # -----------------------------------------------------------------------------
    s = str(path_like or "").strip().replace("\\", "/").strip()
    return s.lstrip("/")


# =============================================================================
# page helper
# =============================================================================
def normalize_page_no(value: Any, default: int = 0) -> int:
    # -----------------------------------------------------------------------------
    # ページ番号を int に正規化する
    #
    # 方針：
    # - None / 空文字 / 不正値 は default
    # - 0 未満は 0 に丸める
    # -----------------------------------------------------------------------------
    try:
        v = int(value)
    except Exception:
        return int(default)

    if v < 0:
        return 0
    return v


# =============================================================================
# meta record
# =============================================================================
def build_meta_record(
    *,
    source: IngestSource,
    chunk: ChunkRecord,
    vector_index: int,
    page_start: int = 0,
    page_end: int = 0,
    ingested_at: Optional[str] = None,
) -> MetaRecord:
    # -----------------------------------------------------------------------------
    # IngestSource + ChunkRecord から MetaRecord を生成する
    # -----------------------------------------------------------------------------
    ts = str(ingested_at or "").strip() or utc_now_iso_z()

    return MetaRecord(
        collection_id=str(source.collection_id),
        shard_id=str(source.shard_id),
        doc_id=str(source.doc_id),
        file=str(source.file),
        file_name=str(source.file_name),
        vector_index=int(vector_index),
        chunk_id=build_chunk_id(
            doc_id=str(source.doc_id),
            chunk_index=int(chunk.chunk_index),
        ),
        chunk_index=int(chunk.chunk_index),
        text=str(chunk.text),
        span_start=int(chunk.span_start),
        span_end=int(chunk.span_end),
        chunk_len_tokens=int(chunk.chunk_len_tokens),
        page_start=normalize_page_no(page_start, default=0),
        page_end=normalize_page_no(page_end, default=0),
        source_pdf_path=normalize_relative_path(source.source_pdf_path),
        source_text_path=normalize_relative_path(source.source_text_path),
        source_pages_path=normalize_relative_path(source.source_pages_path),
        source_text_kind=normalize_source_text_kind(source.source_text_kind),
        sha256=str(source.sha256),
        embed_model=str(source.embed_model),
        ingested_at=ts,
        attrs=normalize_attrs(source.attrs),
    )


# =============================================================================
# processed record
# =============================================================================
def build_processed_file_record(
    *,
    source: IngestSource,
    ingested_at: Optional[str] = None,
) -> ProcessedFileRecord:
    # -----------------------------------------------------------------------------
    # IngestSource から ProcessedFileRecord を生成する
    # -----------------------------------------------------------------------------
    ts = str(ingested_at or "").strip() or utc_now_iso_z()

    return ProcessedFileRecord(
        collection_id=str(source.collection_id),
        shard_id=str(source.shard_id),
        doc_id=str(source.doc_id),
        file=str(source.file),
        sha256=str(source.sha256),
        source_pdf_path=normalize_relative_path(source.source_pdf_path),
        source_text_path=normalize_relative_path(source.source_text_path),
        source_text_kind=normalize_source_text_kind(source.source_text_kind),
        embed_model=str(source.embed_model),
        ingested_at=ts,
        attrs=normalize_attrs(source.attrs),
    )


# =============================================================================
# serialization
# =============================================================================
def meta_record_to_dict(rec: MetaRecord) -> Dict[str, Any]:
    # -----------------------------------------------------------------------------
    # MetaRecord を jsonl 保存向け dict に変換する
    #
    # 注意：
    # - 項目順を安定させるため、明示的に dict を組み立てる
    # -----------------------------------------------------------------------------
    return {
        "collection_id": rec.collection_id,
        "shard_id": rec.shard_id,
        "doc_id": rec.doc_id,
        "file": rec.file,
        "file_name": rec.file_name,
        "vector_index": rec.vector_index,
        "chunk_id": rec.chunk_id,
        "chunk_index": rec.chunk_index,
        "text": rec.text,
        "span_start": rec.span_start,
        "span_end": rec.span_end,
        "chunk_len_tokens": rec.chunk_len_tokens,
        "page_start": rec.page_start,
        "page_end": rec.page_end,
        "source_pdf_path": rec.source_pdf_path,
        "source_text_path": rec.source_text_path,
        "source_pages_path": rec.source_pages_path,
        "source_text_kind": rec.source_text_kind,
        "sha256": rec.sha256,
        "embed_model": rec.embed_model,
        "ingested_at": rec.ingested_at,
        "attrs": normalize_attrs(rec.attrs),
    }


def processed_file_record_to_dict(rec: ProcessedFileRecord) -> Dict[str, Any]:
    # -----------------------------------------------------------------------------
    # ProcessedFileRecord を json 保存向け dict に変換する
    # -----------------------------------------------------------------------------
    return {
        "collection_id": rec.collection_id,
        "shard_id": rec.shard_id,
        "doc_id": rec.doc_id,
        "file": rec.file,
        "sha256": rec.sha256,
        "source_pdf_path": rec.source_pdf_path,
        "source_text_path": rec.source_text_path,
        "source_text_kind": rec.source_text_kind,
        "embed_model": rec.embed_model,
        "ingested_at": rec.ingested_at,
        "attrs": normalize_attrs(rec.attrs),
    }


# =============================================================================
# deserialization
# =============================================================================
def meta_record_from_dict(d: Dict[str, Any]) -> MetaRecord:
    # -----------------------------------------------------------------------------
    # dict から MetaRecord を復元する
    # -----------------------------------------------------------------------------
    src = dict(d or {})
    return MetaRecord(
        collection_id=str(src.get("collection_id", "") or ""),
        shard_id=str(src.get("shard_id", "") or ""),
        doc_id=str(src.get("doc_id", "") or ""),
        file=str(src.get("file", "") or ""),
        file_name=str(src.get("file_name", "") or ""),
        vector_index=int(src.get("vector_index", 0) or 0),
        chunk_id=str(src.get("chunk_id", "") or ""),
        chunk_index=int(src.get("chunk_index", 0) or 0),
        text=str(src.get("text", "") or ""),
        span_start=int(src.get("span_start", 0) or 0),
        span_end=int(src.get("span_end", 0) or 0),
        chunk_len_tokens=int(src.get("chunk_len_tokens", 0) or 0),
        page_start=normalize_page_no(src.get("page_start", 0), default=0),
        page_end=normalize_page_no(src.get("page_end", 0), default=0),
        source_pdf_path=normalize_relative_path(src.get("source_pdf_path", "") or ""),
        source_text_path=normalize_relative_path(src.get("source_text_path", "") or ""),
        source_pages_path=normalize_relative_path(src.get("source_pages_path", "") or ""),
        source_text_kind=normalize_source_text_kind(src.get("source_text_kind", "") or ""),
        sha256=str(src.get("sha256", "") or ""),
        embed_model=str(src.get("embed_model", "") or ""),
        ingested_at=str(src.get("ingested_at", "") or ""),
        attrs=normalize_attrs(src.get("attrs")),
    )


def processed_file_record_from_dict(d: Dict[str, Any]) -> ProcessedFileRecord:
    # -----------------------------------------------------------------------------
    # dict から ProcessedFileRecord を復元する
    # -----------------------------------------------------------------------------
    src = dict(d or {})
    return ProcessedFileRecord(
        collection_id=str(src.get("collection_id", "") or ""),
        shard_id=str(src.get("shard_id", "") or ""),
        doc_id=str(src.get("doc_id", "") or ""),
        file=str(src.get("file", "") or ""),
        sha256=str(src.get("sha256", "") or ""),
        source_pdf_path=normalize_relative_path(src.get("source_pdf_path", "") or ""),
        source_text_path=normalize_relative_path(src.get("source_text_path", "") or ""),
        source_text_kind=normalize_source_text_kind(src.get("source_text_kind", "") or ""),
        embed_model=str(src.get("embed_model", "") or ""),
        ingested_at=str(src.get("ingested_at", "") or ""),
        attrs=normalize_attrs(src.get("attrs")),
    )


# =============================================================================
# processed 判定ヘルパ
# =============================================================================
def is_same_processed_file(
    rec: ProcessedFileRecord,
    *,
    doc_id: str,
    sha256: Optional[str] = None,
    embed_model: Optional[str] = None,
    source_text_kind: Optional[str] = None,
) -> bool:
    # -----------------------------------------------------------------------------
    # processed_files.json 内の1件が、指定条件と一致するか判定する
    #
    # 基本一致条件：
    # - doc_id 一致
    #
    # 追加条件：
    # - sha256 が指定されたら一致確認
    # - embed_model が指定されたら一致確認
    # - source_text_kind が指定されたら一致確認
    #
    # 用途：
    # - 未処理だけ追加
    # - 同名差し替え検知
    # - モデル変更時の再投入要否判定
    # -----------------------------------------------------------------------------
    if str(rec.doc_id) != str(doc_id):
        return False

    if sha256 is not None and str(rec.sha256) != str(sha256):
        return False

    if embed_model is not None and str(rec.embed_model) != str(embed_model):
        return False

    if source_text_kind is not None and str(rec.source_text_kind) != normalize_source_text_kind(source_text_kind):
        return False

    return True


def find_processed_record_by_doc_id(
    records: list[ProcessedFileRecord],
    doc_id: str,
) -> Optional[ProcessedFileRecord]:
    # -----------------------------------------------------------------------------
    # doc_id 一致で processed record を1件探す
    #
    # 見つからなければ None
    # -----------------------------------------------------------------------------
    target = str(doc_id)
    for rec in records:
        if str(rec.doc_id) == target:
            return rec
    return None