# common_lib/rag_ingest/shard_audit_ops.py
# =============================================================================
# shard audit operations（RAG ingest 共通ライブラリ）
#
# 役割：
# - shard（Databases/vectorstore/<collection_id>/<shard_id>/）の監査情報を作る
# - vectors.npy / meta.jsonl / processed_files.json の整合性を確認する
# - vector_index の重複 / 負値 / 範囲外 / orphan を集計する
# - processed / meta の doc_id 不整合を集計する
#
# 方針：
# - 読み取り専用
# - vectors.npy / meta.jsonl / processed_files.json は変更しない
# - UI 依存を持たない
# - collection_id は可変（project / rules / manual / minutes など）
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports（stdlib）
# =============================================================================
from collections import Counter, defaultdict
from pathlib import Path
import json

# =============================================================================
# imports（3rd party）
# =============================================================================
import numpy as np

# =============================================================================
# common_lib（rag_ingest）
# =============================================================================
from common_lib.rag_ingest.paths import resolve_vectorstore_paths
from common_lib.rag_ingest.manifest_ops import (
    meta_record_from_dict,
    processed_file_record_from_dict,
)

# =============================================================================
# helper：jsonl read
# =============================================================================
def _read_jsonl(path: Path) -> list[dict]:
    # -------------------------------------------------------------------------
    # JSONL を読み込む
    # -------------------------------------------------------------------------
    if not path.exists():
        return []

    rows: list[dict] = []

    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                rows.append(json.loads(s))
            except Exception as e:
                rows.append(
                    {
                        "__json_error__": True,
                        "__line__": lineno,
                        "__raw__": s,
                        "__error__": str(e),
                    }
                )

    return rows


# =============================================================================
# helper：json read
# =============================================================================
def _read_json(path: Path):
    # -------------------------------------------------------------------------
    # JSON を読み込む
    # -------------------------------------------------------------------------
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# public：vectors info
# =============================================================================
def load_vectors_info(vectors_path: Path) -> dict:
    # -------------------------------------------------------------------------
    # vectors.npy の情報を取得する
    # -------------------------------------------------------------------------
    if not vectors_path.exists():
        return {
            "exists": False,
            "shape": None,
            "dtype": None,
            "rows": 0,
            "dim": 0,
            "size_bytes": 0,
            "error": None,
        }

    try:
        arr = np.load(vectors_path, allow_pickle=False)

        if arr.ndim == 1:
            if arr.size == 0:
                rows = 0
                dim = 0
            else:
                rows = 1
                dim = int(arr.shape[0])
        elif arr.ndim == 2:
            rows = int(arr.shape[0])
            dim = int(arr.shape[1])
        else:
            rows = 0
            dim = 0

        return {
            "exists": True,
            "shape": tuple(arr.shape),
            "dtype": str(arr.dtype),
            "rows": rows,
            "dim": dim,
            "size_bytes": int(vectors_path.stat().st_size),
            "error": None,
        }

    except Exception as e:
        return {
            "exists": True,
            "shape": None,
            "dtype": None,
            "rows": 0,
            "dim": 0,
            "size_bytes": int(vectors_path.stat().st_size),
            "error": str(e),
        }


# =============================================================================
# public：judge health
# =============================================================================
def judge_shard_health(
    *,
    integrity_errors: list[str],
    orphan_vector_indices: list[int],
    processed_only_doc_ids: list[str],
    meta_only_doc_ids: list[str],
) -> str:
    # -------------------------------------------------------------------------
    # shard health を判定する
    # -------------------------------------------------------------------------
    if integrity_errors:
        return "error"

    if orphan_vector_indices or processed_only_doc_ids or meta_only_doc_ids:
        return "warn"

    return "ok"


# =============================================================================
# public：inspect shard
# =============================================================================
def inspect_shard(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> dict:
    # -------------------------------------------------------------------------
    # 1つの shard を監査する
    # -------------------------------------------------------------------------
    collection_id = str(collection_id)
    shard_id = str(shard_id)

    paths = resolve_vectorstore_paths(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    shard_exists = paths.shard_dir.exists()
    vectors_info = load_vectors_info(paths.vectors_path)

    meta_raw_rows = _read_jsonl(paths.meta_path)
    processed_raw_rows = _read_json(paths.processed_path)

    meta_json_error_rows = [x for x in meta_raw_rows if x.get("__json_error__")]
    meta_rows_ok = [x for x in meta_raw_rows if not x.get("__json_error__")]

    processed_json_error = False
    if not isinstance(processed_raw_rows, list):
        processed_json_error = True
        processed_rows_ok = []
    else:
        processed_rows_ok = processed_raw_rows

    meta_records = []
    meta_parse_errors = []
    for idx, row in enumerate(meta_rows_ok):
        try:
            meta_records.append(meta_record_from_dict(row))
        except Exception as e:
            meta_parse_errors.append(
                {
                    "row_index": idx,
                    "error": str(e),
                    "row": row,
                }
            )

    processed_records = []
    processed_parse_errors = []
    for idx, row in enumerate(processed_rows_ok):
        try:
            processed_records.append(processed_file_record_from_dict(row))
        except Exception as e:
            processed_parse_errors.append(
                {
                    "row_index": idx,
                    "error": str(e),
                    "row": row,
                }
            )

    vector_rows = int(vectors_info["rows"] or 0)

    vector_indices: list[int] = []
    vector_index_doc_map: dict[int, list[str]] = defaultdict(list)
    out_of_range_rows: list[dict] = []
    negative_rows: list[dict] = []

    doc_counter = Counter()
    file_counter = Counter()

    for rec in meta_records:
        vi = int(rec.vector_index)
        vector_indices.append(vi)
        vector_index_doc_map[vi].append(str(rec.doc_id))
        doc_counter[str(rec.doc_id)] += 1
        file_counter[str(rec.file)] += 1

        if vi < 0:
            negative_rows.append(
                {
                    "vector_index": vi,
                    "doc_id": rec.doc_id,
                    "chunk_id": rec.chunk_id,
                }
            )

        if vector_rows > 0 and vi >= vector_rows:
            out_of_range_rows.append(
                {
                    "vector_index": vi,
                    "doc_id": rec.doc_id,
                    "chunk_id": rec.chunk_id,
                }
            )

    dup_counter = Counter(vector_indices)
    duplicate_vector_indices = sorted(
        [k for k, v in dup_counter.items() if v > 1]
    )

    meta_vector_index_set = set(vector_indices)
    all_vector_index_set = set(range(vector_rows))
    orphan_vector_indices = sorted(list(all_vector_index_set - meta_vector_index_set))

    processed_doc_ids = {str(x.doc_id) for x in processed_records}
    meta_doc_ids = {str(x.doc_id) for x in meta_records}

    processed_only_doc_ids = sorted(list(processed_doc_ids - meta_doc_ids))
    meta_only_doc_ids = sorted(list(meta_doc_ids - processed_doc_ids))

    duplicate_doc_ids_in_processed = sorted(
        [k for k, v in Counter([str(x.doc_id) for x in processed_records]).items() if v > 1]
    )

    top_docs = doc_counter.most_common(30)

    integrity_errors: list[str] = []

    if meta_json_error_rows:
        integrity_errors.append("meta.jsonl に JSON 解析エラー行があります。")

    if meta_parse_errors:
        integrity_errors.append("meta.jsonl に MetaRecord 復元エラーがあります。")

    if processed_json_error:
        integrity_errors.append("processed_files.json が list 形式ではありません。")

    if processed_parse_errors:
        integrity_errors.append("processed_files.json に ProcessedFileRecord 復元エラーがあります。")

    if duplicate_vector_indices:
        integrity_errors.append("meta.jsonl 内で vector_index が重複しています。")

    if negative_rows:
        integrity_errors.append("meta.jsonl 内に負の vector_index があります。")

    if out_of_range_rows:
        integrity_errors.append("meta.jsonl 内に vectors.npy 範囲外の vector_index があります。")

    health = judge_shard_health(
        integrity_errors=integrity_errors,
        orphan_vector_indices=orphan_vector_indices,
        processed_only_doc_ids=processed_only_doc_ids,
        meta_only_doc_ids=meta_only_doc_ids,
    )

    return {
        "collection_id": collection_id,
        "paths": paths.summary(),
        "shard_exists": shard_exists,
        "vectors_info": vectors_info,
        "meta_row_count_raw": len(meta_raw_rows),
        "meta_row_count_ok": len(meta_rows_ok),
        "processed_row_count_ok": len(processed_rows_ok),
        "meta_json_error_rows": meta_json_error_rows,
        "meta_parse_errors": meta_parse_errors,
        "processed_json_error": processed_json_error,
        "processed_parse_errors": processed_parse_errors,
        "meta_records": meta_records,
        "processed_records": processed_records,
        "duplicate_vector_indices": duplicate_vector_indices,
        "negative_rows": negative_rows,
        "out_of_range_rows": out_of_range_rows,
        "orphan_vector_indices": orphan_vector_indices,
        "processed_only_doc_ids": processed_only_doc_ids,
        "meta_only_doc_ids": meta_only_doc_ids,
        "duplicate_doc_ids_in_processed": duplicate_doc_ids_in_processed,
        "top_docs": top_docs,
        "health": health,
        "integrity_errors": integrity_errors,
    }


# =============================================================================
# backward compatibility：project 固定ラッパー
# =============================================================================
def inspect_project_shard(
    databases_root: Path,
    *,
    shard_id: str,
) -> dict:
    # -------------------------------------------------------------------------
    # project 固定互換ラッパー
    # -------------------------------------------------------------------------
    return inspect_shard(
        databases_root,
        collection_id="project",
        shard_id=str(shard_id),
    )