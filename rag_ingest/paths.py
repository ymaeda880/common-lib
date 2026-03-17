# common_lib/rag_ingest/paths.py
# =============================================================================
# RAG ingest : Path 解決ユーティリティ
#
# 役割：
# - vectorstore の保存場所を解決する
# - shard ディレクトリの path を正本として管理する
# - vectors.npy / meta.jsonl / processed_files.json の path を生成する
#
# 設計方針：
# - 保存先は必ず次の構造にする
#
#     Databases/vectorstore/<collection_id>/<shard_id>/
#
# - collection_id
#       project / rules / contracts など
#
# - shard_id
#       project の場合は year
#       rules   の場合は yyzz 等
#
# - shard_id は文字列として扱う（year決め打ちはしない）
#
# - path は pathlib.Path を使う
#
# - vectorstore path は「Databases ルート」を渡して解決する
#
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from pathlib import Path


# =============================================================================
# VectorStorePaths
# =============================================================================
class VectorStorePaths:
    # -----------------------------------------------------------------------------
    # vectorstore shard のパス集合
    #
    # 例：
    #
    #   Databases/vectorstore/project/2019/
    #
    #       vectors.npy
    #       meta.jsonl
    #       processed_files.json
    #
    # -----------------------------------------------------------------------------

    def __init__(
        self,
        databases_root: Path,
        collection_id: str,
        shard_id: str,
    ) -> None:

        self.databases_root = Path(databases_root)

        self.collection_id = collection_id
        self.shard_id = shard_id

        # ---------------------------------------------------------------------
        # Databases/vectorstore
        # ---------------------------------------------------------------------
        self.vectorstore_root = self.databases_root / "vectorstore"

        # ---------------------------------------------------------------------
        # Databases/vectorstore/<collection_id>
        # ---------------------------------------------------------------------
        self.collection_dir = self.vectorstore_root / collection_id

        # ---------------------------------------------------------------------
        # Databases/vectorstore/<collection_id>/<shard_id>
        # ---------------------------------------------------------------------
        self.shard_dir = self.collection_dir / shard_id

        # ---------------------------------------------------------------------
        # shard 配下ファイル
        # ---------------------------------------------------------------------
        self.vectors_path = self.shard_dir / "vectors.npy"
        self.meta_path = self.shard_dir / "meta.jsonl"
        self.processed_path = self.shard_dir / "processed_files.json"

    # -----------------------------------------------------------------------------
    # shard directory 作成
    # -----------------------------------------------------------------------------
    def ensure_dirs(self) -> None:

        self.collection_dir.mkdir(parents=True, exist_ok=True)
        self.shard_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------------
    # vectors.npy の存在確認
    # -----------------------------------------------------------------------------
    def vectors_exists(self) -> bool:

        return self.vectors_path.exists()

    # -----------------------------------------------------------------------------
    # meta.jsonl の存在確認
    # -----------------------------------------------------------------------------
    def meta_exists(self) -> bool:

        return self.meta_path.exists()

    # -----------------------------------------------------------------------------
    # processed_files.json の存在確認
    # -----------------------------------------------------------------------------
    def processed_exists(self) -> bool:

        return self.processed_path.exists()

    # -----------------------------------------------------------------------------
    # shard summary
    # -----------------------------------------------------------------------------
    def summary(self) -> dict:

        return {
            "collection_id": self.collection_id,
            "shard_id": self.shard_id,
            "vectorstore_root": str(self.vectorstore_root),
            "collection_dir": str(self.collection_dir),
            "shard_dir": str(self.shard_dir),
            "vectors_path": str(self.vectors_path),
            "meta_path": str(self.meta_path),
            "processed_path": str(self.processed_path),
        }


# =============================================================================
# convenience function
# =============================================================================
def resolve_vectorstore_paths(
    databases_root: Path,
    collection_id: str,
    shard_id: str,
) -> VectorStorePaths:

    # -------------------------------------------------------------------------
    # VectorStorePaths を生成する簡易関数
    # -------------------------------------------------------------------------

    return VectorStorePaths(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )