# common_lib/rag_ingest/vectorstore_io.py
# =============================================================================
# RAG ingest : vectorstore I/O 正本
#
# 役割：
# - Databases/vectorstore/<collection_id>/<shard_id>/ 配下の
#   vectors.npy / meta.jsonl / processed_files.json を読み書きする
# - append / doc_id単位削除 / 再保存 の正本I/Oを提供する
# - vectors と meta の件数整合を検査する
#
# 設計方針：
# - vectors.npy の i 行目 <-> meta.jsonl の i 行目 は必ず対応していなければならない
# - processed_files.json は文書単位の管理情報を持つ
# - path解決は paths.py を使う
# - メタ生成/復元は manifest_ops.py を使う
# - できるだけ page や adapter 側に I/O を漏らさない
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
import json
from pathlib import Path
from typing import Any, Iterable, List, Optional

import numpy as np

from .manifest_ops import (
    find_processed_record_by_doc_id,
    meta_record_from_dict,
    meta_record_to_dict,
    processed_file_record_from_dict,
    processed_file_record_to_dict,
)
from .models import MetaRecord, ProcessedFileRecord, VectorStoreSnapshot
from .paths import VectorStorePaths, resolve_vectorstore_paths


# =============================================================================
# 定数
# =============================================================================
DEFAULT_EMBEDDING_DIM = 0


# =============================================================================
# 例外
# =============================================================================
class VectorStoreIOError(Exception):
    # -----------------------------------------------------------------------------
    # vectorstore I/O 共通例外
    # -----------------------------------------------------------------------------
    pass


class VectorStoreIntegrityError(VectorStoreIOError):
    # -----------------------------------------------------------------------------
    # vectors と meta の整合崩れ
    # -----------------------------------------------------------------------------
    pass


# =============================================================================
# JSON helper
# =============================================================================
def _read_json_file(path: Path, default: Any) -> Any:
    # -----------------------------------------------------------------------------
    # JSONファイルを読む
    # -----------------------------------------------------------------------------
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_file(path: Path, data: Any) -> None:
    # -----------------------------------------------------------------------------
    # JSONファイルを書く
    # -----------------------------------------------------------------------------
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# =============================================================================
# JSONL helper
# =============================================================================
def _read_jsonl_file(path: Path) -> list[dict]:
    # -----------------------------------------------------------------------------
    # JSONLファイルを読む
    # -----------------------------------------------------------------------------
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
                raise VectorStoreIOError(
                    f"JSONL読込エラー: {path} line={lineno} : {e}"
                ) from e

    return rows


def _write_jsonl_file(path: Path, rows: Iterable[dict]) -> None:
    # -----------------------------------------------------------------------------
    # JSONLファイルを書く
    # -----------------------------------------------------------------------------
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
            )
            f.write("\n")


# =============================================================================
# numpy helper
# =============================================================================
def _empty_vectors(dim: int = DEFAULT_EMBEDDING_DIM) -> np.ndarray:
    # -----------------------------------------------------------------------------
    # 空ベクトル配列を返す
    #
    # dim=0 の場合 shape=(0, 0)
    # -----------------------------------------------------------------------------
    d = int(dim)
    if d < 0:
        raise ValueError("embedding dimension は 0 以上である必要があります。")
    return np.empty((0, d), dtype=np.float32)


def _ensure_2d_float32(arr: Any) -> np.ndarray:
    # -----------------------------------------------------------------------------
    # vectors を 2次元 float32 ndarray に正規化する
    # -----------------------------------------------------------------------------
    np_arr = np.asarray(arr, dtype=np.float32)

    if np_arr.ndim == 1:
        if np_arr.size == 0:
            return _empty_vectors(0)
        np_arr = np_arr.reshape(1, -1)

    if np_arr.ndim != 2:
        raise VectorStoreIOError("vectors は2次元配列である必要があります。")

    return np_arr


def _load_vectors_npy(path: Path) -> np.ndarray:
    # -----------------------------------------------------------------------------
    # vectors.npy を読む
    # -----------------------------------------------------------------------------
    if not path.exists():
        return _empty_vectors(0)

    try:
        arr = np.load(path, allow_pickle=False)
    except Exception as e:
        raise VectorStoreIOError(f"vectors.npy 読込失敗: {path} : {e}") from e

    return _ensure_2d_float32(arr)


def _save_vectors_npy(path: Path, vectors: np.ndarray) -> None:
    # -----------------------------------------------------------------------------
    # vectors.npy を保存する
    # -----------------------------------------------------------------------------
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, _ensure_2d_float32(vectors), allow_pickle=False)


# =============================================================================
# 整合チェック
# =============================================================================
def _vector_row_count(vectors: np.ndarray) -> int:
    # -----------------------------------------------------------------------------
    # vectors の行数
    # -----------------------------------------------------------------------------
    arr = _ensure_2d_float32(vectors)
    return int(arr.shape[0])


def _vector_dim(vectors: np.ndarray) -> int:
    # -----------------------------------------------------------------------------
    # vectors の次元数
    # -----------------------------------------------------------------------------
    arr = _ensure_2d_float32(vectors)
    if arr.ndim != 2:
        return 0
    return int(arr.shape[1])

def validate_vector_meta_alignment(
    vectors: np.ndarray,
    meta_records: list[MetaRecord],
) -> None:
    # -----------------------------------------------------------------------------
    # vectors と meta の整合を確認する
    #
    # append only 方針のため、
    # - vectors の行数 == meta 件数
    # は要求しない。
    #
    # 代わりに
    # - 各 meta.vector_index が 0 以上
    # - 各 meta.vector_index が vectors 行数未満
    # - vector_index に重複がない
    # を確認する。
    # -----------------------------------------------------------------------------
    n_vec = _vector_row_count(vectors)

    seen: set[int] = set()

    for rec in meta_records:
        vi = int(rec.vector_index)

        if vi < 0:
            raise VectorStoreIntegrityError(
                f"meta.jsonl の vector_index が負です: {vi}"
            )

        if vi >= n_vec and n_vec > 0:
            raise VectorStoreIntegrityError(
                "meta.jsonl の vector_index が vectors.npy の範囲外です。"
                f" vector_index={vi}, vector_rows={n_vec}"
            )

        if vi in seen:
            raise VectorStoreIntegrityError(
                f"meta.jsonl 内で vector_index が重複しています: {vi}"
            )

        seen.add(vi)


def validate_snapshot(snapshot: VectorStoreSnapshot) -> None:
    # -----------------------------------------------------------------------------
    # snapshot 全体の整合確認
    # -----------------------------------------------------------------------------
    validate_vector_meta_alignment(snapshot.vectors, snapshot.meta_records)


# =============================================================================
# path helper
# =============================================================================
def get_vectorstore_paths(
    databases_root: Path,
    collection_id: str,
    shard_id: str,
) -> VectorStorePaths:
    # -----------------------------------------------------------------------------
    # paths 解決
    # -----------------------------------------------------------------------------
    return resolve_vectorstore_paths(
        databases_root=Path(databases_root),
        collection_id=str(collection_id),
        shard_id=str(shard_id),
    )


# =============================================================================
# 読み込み
# =============================================================================
def load_meta_records(meta_path: Path) -> list[MetaRecord]:
    # -----------------------------------------------------------------------------
    # meta.jsonl 読込
    # -----------------------------------------------------------------------------
    rows = _read_jsonl_file(meta_path)
    return [meta_record_from_dict(x) for x in rows]


def load_processed_records(processed_path: Path) -> list[ProcessedFileRecord]:
    # -----------------------------------------------------------------------------
    # processed_files.json 読込
    # -----------------------------------------------------------------------------
    rows = _read_json_file(processed_path, default=[])

    if rows is None:
        rows = []

    if not isinstance(rows, list):
        raise VectorStoreIOError(
            f"processed_files.json の内容が list ではありません: {processed_path}"
        )

    return [processed_file_record_from_dict(x) for x in rows]


def load_vectorstore_snapshot(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
) -> VectorStoreSnapshot:
    # -----------------------------------------------------------------------------
    # shard 全体を読み込む
    # -----------------------------------------------------------------------------
    paths = get_vectorstore_paths(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    vectors = _load_vectors_npy(paths.vectors_path)
    meta_records = load_meta_records(paths.meta_path)
    processed_records = load_processed_records(paths.processed_path)

    snapshot = VectorStoreSnapshot(
        vectors=vectors,
        meta_records=meta_records,
        processed_records=processed_records,
    )

    validate_snapshot(snapshot)
    return snapshot


# =============================================================================
# 保存
# =============================================================================
def save_meta_records(
    meta_path: Path,
    meta_records: list[MetaRecord],
) -> None:
    # -----------------------------------------------------------------------------
    # meta.jsonl 保存
    # -----------------------------------------------------------------------------
    rows = [meta_record_to_dict(x) for x in meta_records]
    _write_jsonl_file(meta_path, rows)


def save_processed_records(
    processed_path: Path,
    processed_records: list[ProcessedFileRecord],
) -> None:
    # -----------------------------------------------------------------------------
    # processed_files.json 保存
    # -----------------------------------------------------------------------------
    rows = [processed_file_record_to_dict(x) for x in processed_records]
    _write_json_file(processed_path, rows)


def save_vectorstore_snapshot(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
    vectors: np.ndarray,
    meta_records: list[MetaRecord],
    processed_records: list[ProcessedFileRecord],
) -> None:
    # -----------------------------------------------------------------------------
    # shard 全体を保存する
    # -----------------------------------------------------------------------------
    paths = get_vectorstore_paths(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )
    paths.ensure_dirs()

    vectors2 = _ensure_2d_float32(vectors)
    validate_vector_meta_alignment(vectors2, meta_records)

    _save_vectors_npy(paths.vectors_path, vectors2)
    save_meta_records(paths.meta_path, meta_records)
    save_processed_records(paths.processed_path, processed_records)


# =============================================================================
# 初期化
# =============================================================================
def initialize_empty_vectorstore(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
) -> None:
    # -----------------------------------------------------------------------------
    # 空の shard を初期化する
    # -----------------------------------------------------------------------------
    vectors = _empty_vectors(int(embedding_dim))
    meta_records: list[MetaRecord] = []
    processed_records: list[ProcessedFileRecord] = []

    save_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
        vectors=vectors,
        meta_records=meta_records,
        processed_records=processed_records,
    )


# =============================================================================
# append
# =============================================================================
def append_to_vectorstore(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
    new_vectors: Any,
    new_meta_records: list[MetaRecord],
    new_processed_record: Optional[ProcessedFileRecord] = None,
) -> VectorStoreSnapshot:
    # -----------------------------------------------------------------------------
    # shard に新しい文書の vectors / meta / processed を追加する
    #
    # 注意：
    # - new_vectors の行数 == new_meta_records 件数 である必要がある
    # - processed は文書単位なので 1件または None
    # -----------------------------------------------------------------------------
    snapshot = load_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    old_vectors = _ensure_2d_float32(snapshot.vectors)
    add_vectors = _ensure_2d_float32(new_vectors)

    if _vector_row_count(add_vectors) != len(new_meta_records):
        raise VectorStoreIntegrityError(
            "append対象の vectors 件数と meta 件数が一致しません。"
            f" new_vectors={_vector_row_count(add_vectors)},"
            f" new_meta={len(new_meta_records)}"
        )

    old_dim = _vector_dim(old_vectors)
    add_dim = _vector_dim(add_vectors)

    if _vector_row_count(old_vectors) == 0:
        combined_vectors = add_vectors
    elif _vector_row_count(add_vectors) == 0:
        combined_vectors = old_vectors
    else:
        if old_dim != add_dim:
            raise VectorStoreIntegrityError(
                "既存vectors と追加vectors の次元数が一致しません。"
                f" old_dim={old_dim}, add_dim={add_dim}"
            )
        combined_vectors = np.vstack([old_vectors, add_vectors])

    combined_meta = list(snapshot.meta_records) + list(new_meta_records)

    combined_processed = list(snapshot.processed_records)
    if new_processed_record is not None:
        combined_processed.append(new_processed_record)

    save_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
        vectors=combined_vectors,
        meta_records=combined_meta,
        processed_records=combined_processed,
    )

    return load_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )


# =============================================================================
# doc_id 単位削除
# =============================================================================
def delete_doc_id_from_vectorstore(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> VectorStoreSnapshot:
    # -----------------------------------------------------------------------------
    # 指定 doc_id に属する chunk を meta / processed から削除する
    #
    # 重要：
    # - append only 方針のため vectors.npy は削除しない
    # - vectors.npy 側の古いベクトルは孤立ベクトルとして残る
    # -----------------------------------------------------------------------------
    target_doc_id = str(doc_id or "").strip()
    if not target_doc_id:
        raise ValueError("doc_id が空です。")

    snapshot = load_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    vectors = _ensure_2d_float32(snapshot.vectors)

    new_meta_records = [
        rec for rec in snapshot.meta_records
        if str(rec.doc_id) != target_doc_id
    ]

    new_processed_records = [
        rec for rec in snapshot.processed_records
        if str(rec.doc_id) != target_doc_id
    ]

    save_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
        vectors=vectors,
        meta_records=new_meta_records,
        processed_records=new_processed_records,
    )

    return load_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

def get_next_vector_index(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
) -> int:
    # -----------------------------------------------------------------------------
    # 次に採番すべき vector_index を返す
    #
    # append only 方針のため、vectors.npy の行数をそのまま次 index とする。
    # -----------------------------------------------------------------------------
    snapshot = load_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    vectors = _ensure_2d_float32(snapshot.vectors)
    return _vector_row_count(vectors)

# =============================================================================
# processed helper
# =============================================================================
def get_processed_record(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Optional[ProcessedFileRecord]:
    # -----------------------------------------------------------------------------
    # processed_files.json から doc_id 一致の1件を取得
    # -----------------------------------------------------------------------------
    snapshot = load_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    return find_processed_record_by_doc_id(snapshot.processed_records, doc_id)


def is_doc_id_processed(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> bool:
    # -----------------------------------------------------------------------------
    # doc_id が processed 済みか
    # -----------------------------------------------------------------------------
    rec = get_processed_record(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    return rec is not None


# =============================================================================
# summary
# =============================================================================
def get_vectorstore_summary(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
) -> dict:
    # -----------------------------------------------------------------------------
    # shard の要約情報を返す
    # -----------------------------------------------------------------------------
    paths = get_vectorstore_paths(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    snapshot = load_vectorstore_snapshot(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    vectors = _ensure_2d_float32(snapshot.vectors)

    return {
        "collection_id": str(collection_id),
        "shard_id": str(shard_id),
        "shard_dir": str(paths.shard_dir),
        "vectors_path": str(paths.vectors_path),
        "meta_path": str(paths.meta_path),
        "processed_path": str(paths.processed_path),
        "vector_rows": _vector_row_count(vectors),
        "embedding_dim": _vector_dim(vectors),
        "meta_count": len(snapshot.meta_records),
        "processed_count": len(snapshot.processed_records),
    }