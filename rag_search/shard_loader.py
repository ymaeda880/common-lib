# common_lib/rag_search/shard_loader.py
# =============================================================================
# RAG search : shard loader
#
# 役割：
# - Databases/vectorstore/<collection_id>/<shard_id>/ を読む
# - vectors.npy を読む
# - meta.jsonl を読む
# - meta.jsonl の vector_index を検証する
# - 有効な meta 行だけを返す
#
# 方針：
# - vectors.npy は append only 前提
# - 検索対象として有効なのは meta.jsonl に存在する vector_index のみ
# - 壊れた meta 行や不正 index は issues に記録して除外する
# - processed_files.json はこの loader では使わない
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


# =============================================================================
# models
# =============================================================================
@dataclass(frozen=True)
class MetaValidationIssue:
    # -------------------------------------------------------------------------
    # kind:
    # - invalid_json
    # - not_dict
    # - missing_vector_index
    # - non_int_vector_index
    # - negative_vector_index
    # - out_of_range_vector_index
    # - duplicate_vector_index
    # -------------------------------------------------------------------------
    kind: str
    line_no: int
    detail: str


@dataclass
class LoadedShard:
    # -------------------------------------------------------------------------
    # shard 基本情報
    # -------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    shard_dir: Path

    # -------------------------------------------------------------------------
    # ベクトル本体
    # -------------------------------------------------------------------------
    vectors: np.ndarray

    # -------------------------------------------------------------------------
    # 有効 meta
    # - key: vector_index
    # - value: meta.jsonl の 1行 dict
    # -------------------------------------------------------------------------
    meta_by_vector_index: dict[int, dict[str, Any]] = field(default_factory=dict)

    # -------------------------------------------------------------------------
    # 検証 issues
    # -------------------------------------------------------------------------
    issues: list[MetaValidationIssue] = field(default_factory=list)

    # -------------------------------------------------------------------------
    # 参考情報
    # -------------------------------------------------------------------------
    vectors_row_count: int = 0
    vectors_dim: int = 0
    meta_valid_count: int = 0

    # -------------------------------------------------------------------------
    # helper
    # -------------------------------------------------------------------------
    def valid_vector_indices(self) -> list[int]:
        return sorted(self.meta_by_vector_index.keys())

    def get_meta(self, vector_index: int) -> dict[str, Any] | None:
        return self.meta_by_vector_index.get(int(vector_index))


# =============================================================================
# public : path helpers
# =============================================================================
def get_vectorstore_shard_dir(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # Databases/vectorstore/<collection_id>/<shard_id>
    # -------------------------------------------------------------------------
    return Path(databases_root) / "vectorstore" / str(collection_id) / str(shard_id)


def get_vectors_npy_path(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # vectors.npy path
    # -------------------------------------------------------------------------
    return get_vectorstore_shard_dir(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    ) / "vectors.npy"


def get_meta_jsonl_path(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # meta.jsonl path
    # -------------------------------------------------------------------------
    return get_vectorstore_shard_dir(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    ) / "meta.jsonl"


# =============================================================================
# public : main
# =============================================================================
def load_vectorstore_shard(
    *,
    databases_root: Path,
    collection_id: str,
    shard_id: str,
) -> LoadedShard:
    # -------------------------------------------------------------------------
    # 1. paths
    # -------------------------------------------------------------------------
    shard_dir = get_vectorstore_shard_dir(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )
    vectors_path = shard_dir / "vectors.npy"
    meta_path = shard_dir / "meta.jsonl"

    # -------------------------------------------------------------------------
    # 2. existence checks
    # -------------------------------------------------------------------------
    if not shard_dir.exists():
        raise FileNotFoundError(f"shard dir not found: {shard_dir}")

    if not vectors_path.exists():
        raise FileNotFoundError(f"vectors.npy not found: {vectors_path}")

    if not meta_path.exists():
        raise FileNotFoundError(f"meta.jsonl not found: {meta_path}")

    # -------------------------------------------------------------------------
    # 3. vectors load
    # -------------------------------------------------------------------------
    vectors = np.load(vectors_path)

    if not isinstance(vectors, np.ndarray):
        raise TypeError(f"vectors.npy could not be loaded as ndarray: {vectors_path}")

    if vectors.ndim != 2:
        raise ValueError(
            f"vectors.npy must be 2-D, got ndim={vectors.ndim} : {vectors_path}"
        )

    vectors_row_count = int(vectors.shape[0])
    vectors_dim = int(vectors.shape[1])

    # -------------------------------------------------------------------------
    # 4. meta load
    # -------------------------------------------------------------------------
    meta_by_vector_index, issues = _load_valid_meta_jsonl(
        meta_path=meta_path,
        vectors_row_count=vectors_row_count,
    )

    # -------------------------------------------------------------------------
    # 5. result
    # -------------------------------------------------------------------------
    return LoadedShard(
        collection_id=str(collection_id),
        shard_id=str(shard_id),
        shard_dir=shard_dir,
        vectors=vectors,
        meta_by_vector_index=meta_by_vector_index,
        issues=issues,
        vectors_row_count=vectors_row_count,
        vectors_dim=vectors_dim,
        meta_valid_count=len(meta_by_vector_index),
    )


# =============================================================================
# internal : meta loader
# =============================================================================
def _load_valid_meta_jsonl(
    *,
    meta_path: Path,
    vectors_row_count: int,
) -> tuple[dict[int, dict[str, Any]], list[MetaValidationIssue]]:
    # -------------------------------------------------------------------------
    # meta.jsonl を読んで、有効な行だけを返す
    # -------------------------------------------------------------------------
    meta_by_vector_index: dict[int, dict[str, Any]] = {}
    issues: list[MetaValidationIssue] = []

    with Path(meta_path).open("r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = str(raw_line or "").strip()

            # -----------------------------------------------------------------
            # 空行は無視
            # -----------------------------------------------------------------
            if not line:
                continue

            # -----------------------------------------------------------------
            # json parse
            # -----------------------------------------------------------------
            try:
                row = json.loads(line)
            except Exception as e:
                issues.append(
                    MetaValidationIssue(
                        kind="invalid_json",
                        line_no=line_no,
                        detail=str(e),
                    )
                )
                continue

            if not isinstance(row, dict):
                issues.append(
                    MetaValidationIssue(
                        kind="not_dict",
                        line_no=line_no,
                        detail="meta row is not dict",
                    )
                )
                continue

            # -----------------------------------------------------------------
            # vector_index check
            # -----------------------------------------------------------------
            if "vector_index" not in row:
                issues.append(
                    MetaValidationIssue(
                        kind="missing_vector_index",
                        line_no=line_no,
                        detail="vector_index missing",
                    )
                )
                continue

            vector_index = row.get("vector_index")

            if not isinstance(vector_index, int):
                issues.append(
                    MetaValidationIssue(
                        kind="non_int_vector_index",
                        line_no=line_no,
                        detail=f"value={vector_index!r}",
                    )
                )
                continue

            if vector_index < 0:
                issues.append(
                    MetaValidationIssue(
                        kind="negative_vector_index",
                        line_no=line_no,
                        detail=f"value={vector_index}",
                    )
                )
                continue

            if vector_index >= int(vectors_row_count):
                issues.append(
                    MetaValidationIssue(
                        kind="out_of_range_vector_index",
                        line_no=line_no,
                        detail=f"value={vector_index}, row_count={vectors_row_count}",
                    )
                )
                continue

            if vector_index in meta_by_vector_index:
                issues.append(
                    MetaValidationIssue(
                        kind="duplicate_vector_index",
                        line_no=line_no,
                        detail=f"value={vector_index}",
                    )
                )
                continue

            # -----------------------------------------------------------------
            # valid row
            # -----------------------------------------------------------------
            meta_by_vector_index[int(vector_index)] = row

    return meta_by_vector_index, issues