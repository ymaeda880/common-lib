# common_lib/rag_search/vector_search.py
# =============================================================================
# RAG search : ベクトル検索（最小版）
#
# 役割：
# - query vector と LoadedShard を受け取り cosine 類似度検索を行う
# - meta.jsonl に存在する vector_index のみを対象にする
# - top-k の結果を返す
#
# 方針：
# - brute force のみ（ANNなし）
# - rerank / overlap / 補完は一切やらない
# - debugしやすいようにシンプルにする
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from .shard_loader import LoadedShard


# =============================================================================
# models（最小）
# =============================================================================
@dataclass(frozen=True)
class SearchHit:
    vector_index: int
    score: float
    meta: dict

    # ------------------------------------------------------------
    # helper
    # ------------------------------------------------------------
    @property
    def text(self) -> str:
        return str(self.meta.get("text", ""))

    @property
    def chunk_index(self):
        return self.meta.get("chunk_index")

    @property
    def attrs(self) -> dict:
        v = self.meta.get("attrs")
        return v if isinstance(v, dict) else {}


# =============================================================================
# public : 単一 shard 検索
# =============================================================================
def search_loaded_shard(
    *,
    shard: LoadedShard,
    query_vector: np.ndarray,
    top_k: int = 5,
) -> List[SearchHit]:
    # -------------------------------------------------------------------------
    # 1. query normalize
    # -------------------------------------------------------------------------
    q = _to_1d_vector(query_vector)

    if q.shape[0] != shard.vectors_dim:
        raise ValueError(
            f"query dim mismatch: query={q.shape[0]}, shard={shard.vectors_dim}"
        )

    # -------------------------------------------------------------------------
    # 2. valid indices
    # -------------------------------------------------------------------------
    valid_indices = shard.valid_vector_indices()
    if not valid_indices:
        return []

    idx_arr = np.asarray(valid_indices, dtype=np.int64)

    # -------------------------------------------------------------------------
    # 3. 対象ベクトル抽出
    # -------------------------------------------------------------------------
    target_vectors = shard.vectors[idx_arr]

    # -------------------------------------------------------------------------
    # 4. cosine similarity
    # -------------------------------------------------------------------------
    scores = _cosine_similarity(
        matrix=target_vectors,
        vector=q,
    )

    # -------------------------------------------------------------------------
    # 5. hit 作成
    # -------------------------------------------------------------------------
    hits: List[SearchHit] = []

    for i, score in enumerate(scores):
        vector_index = int(idx_arr[i])
        meta = shard.get_meta(vector_index)

        if meta is None:
            continue

        hits.append(
            SearchHit(
                vector_index=vector_index,
                score=float(score),
                meta=meta,
            )
        )

    # -------------------------------------------------------------------------
    # 6. sort & top-k
    # -------------------------------------------------------------------------
    hits.sort(key=lambda x: x.score, reverse=True)

    return hits[: int(top_k)]


# =============================================================================
# public : 複数 shard 検索
# =============================================================================
def search_many_shards(
    *,
    shards: Sequence[LoadedShard],
    query_vector: np.ndarray,
    top_k: int = 5,
) -> List[SearchHit]:
    # -------------------------------------------------------------------------
    # 各 shard を検索して統合
    # -------------------------------------------------------------------------
    all_hits: List[SearchHit] = []

    for shard in shards:
        hits = search_loaded_shard(
            shard=shard,
            query_vector=query_vector,
            top_k=int(top_k),
        )
        all_hits.extend(hits)

    # -------------------------------------------------------------------------
    # 全体で sort
    # -------------------------------------------------------------------------
    all_hits.sort(key=lambda x: x.score, reverse=True)

    return all_hits[: int(top_k)]


# =============================================================================
# internal
# =============================================================================
def _to_1d_vector(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float32)

    if x.ndim == 1:
        return x

    if x.ndim == 2 and x.shape[0] == 1:
        return x[0]

    raise ValueError(f"query vector shape invalid: {x.shape}")


def _cosine_similarity(
    *,
    matrix: np.ndarray,
    vector: np.ndarray,
) -> np.ndarray:
    # -------------------------------------------------------------------------
    # matrix: (n, d)
    # vector: (d,)
    # return: (n,)
    # -------------------------------------------------------------------------
    mat = np.asarray(matrix, dtype=np.float32)
    vec = np.asarray(vector, dtype=np.float32)

    # norm
    vec_norm = np.linalg.norm(vec)
    mat_norm = np.linalg.norm(mat, axis=1)

    if float(vec_norm) == 0.0:
        raise ValueError("query vector norm is zero")

    denom = mat_norm * vec_norm
    dot = mat @ vec

    scores = np.zeros(mat.shape[0], dtype=np.float32)
    mask = denom > 0.0

    scores[mask] = dot[mask] / denom[mask]

    return scores