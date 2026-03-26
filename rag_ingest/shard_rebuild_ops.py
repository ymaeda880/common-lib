# -*- coding: utf-8 -*-
# common_lib/rag_ingest/shard_rebuild_ops.py
# =============================================================================
# RAG ingest : shard 再構築オペレーション（正本API）
#
# 役割：
# - shard の再構築必要性を判定する
#   - vectors.npy の行数
#   - meta.jsonl の件数
#   - processed_files.json の件数
# - 再構築前バックアップを作成する
# - project shard について、現在有効な doc から source を再構成する
# - shard 全体の clean rebuild を実行する
#
# 重要方針：
# - 再構築必要性の判定は「vectors 行数」と「meta 件数」の比較だけを用いる
# - 削除履歴は扱わない
# - clean rebuild は、現在有効な doc だけから
#   vectors.npy / meta.jsonl / processed_files.json を全再生成して保存する
# - project の source 解決は source_adapter 正本を使う
# - chunk / embedding / manifest 構築は ingest_usecase 正本 helper を使う
# - shard 保存は vectorstore_io.save_vectorstore_snapshot 正本を使う
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports（stdlib）
# =============================================================================
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import shutil

# =============================================================================
# imports（3rd party）
# =============================================================================
import numpy as np

# =============================================================================
# common_lib（rag_ingest）
# =============================================================================
from common_lib.rag_ingest.chunk_ops import ChunkOptions
from common_lib.rag_ingest.ingest_usecase import (
    PreparedDocumentPayload,
    prepare_one_document_payload,
)
from common_lib.rag_ingest.models import IngestSource, MetaRecord, ProcessedFileRecord
from common_lib.rag_ingest.project.source_adapter import resolve_project_report_source
from common_lib.rag_ingest.shard_doc_ops import load_shard_doc_state
from common_lib.rag_ingest.vectorstore_io import (
    save_vectorstore_snapshot,
)

# =============================================================================
# dataclass：status
# =============================================================================
@dataclass(frozen=True)
class ShardRebuildStatus:
    # -------------------------------------------------------------------------
    # shard の再構築判定情報
    # -------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    shard_dir: Path

    vectors_exists: bool
    meta_exists: bool
    processed_exists: bool

    vectors_row_count: int
    vectors_dim: int
    meta_count: int
    processed_count: int

    diff_vectors_minus_meta: int

    meta_json_error_rows: list[dict]
    meta_parse_errors: list[dict]
    processed_json_error: bool
    processed_parse_errors: list[dict]

    needs_rebuild: bool
    level: str
    message: str


# =============================================================================
# dataclass：source collect result
# =============================================================================
@dataclass(frozen=True)
class ProjectShardSourceCollectResult:
    # -------------------------------------------------------------------------
    # project shard の source 再構成結果
    # -------------------------------------------------------------------------
    collection_id: str
    shard_id: str

    source_count: int
    skipped_count: int

    sources: list[IngestSource]
    skipped_rows: list[dict[str, Any]]


# =============================================================================
# dataclass：rebuild plan
# =============================================================================
@dataclass(frozen=True)
class ShardRebuildPlan:
    # -------------------------------------------------------------------------
    # clean rebuild 事前計画
    # -------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    old_vectors_row_count: int
    old_meta_count: int
    old_processed_count: int
    target_doc_count: int
    skipped_doc_count: int
    embed_models: list[str]


# =============================================================================
# dataclass：result
# =============================================================================
@dataclass(frozen=True)
class ShardRebuildResult:
    # -------------------------------------------------------------------------
    # clean rebuild 実行結果
    # -------------------------------------------------------------------------
    ok: bool
    message: str

    collection_id: str
    shard_id: str
    shard_dir: str

    backup_dir: Optional[str]

    old_vectors_row_count: int
    old_meta_count: int
    old_processed_count: int

    new_vectors_row_count: int
    new_meta_count: int
    new_processed_count: int

    actor: str
    rebuilt_at: str


# =============================================================================
# helper：paths
# =============================================================================
def get_vectorstore_root(databases_root: Path) -> Path:
    # -------------------------------------------------------------------------
    # Databases/vectorstore を返す
    # -------------------------------------------------------------------------
    return Path(databases_root) / "vectorstore"


def get_shard_dir(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # shard dir を返す
    # -------------------------------------------------------------------------
    return get_vectorstore_root(Path(databases_root)) / str(collection_id) / str(shard_id)


def get_vectors_path(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # vectors.npy path
    # -------------------------------------------------------------------------
    return get_shard_dir(
        databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    ) / "vectors.npy"


def get_meta_path(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # meta.jsonl path
    # -------------------------------------------------------------------------
    return get_shard_dir(
        databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    ) / "meta.jsonl"


def get_processed_path(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # processed_files.json path
    # -------------------------------------------------------------------------
    return get_shard_dir(
        databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    ) / "processed_files.json"


# =============================================================================
# helper：vectors shape
# =============================================================================
def get_vectors_shape(vectors_path: Path) -> tuple[int, int]:
    # -------------------------------------------------------------------------
    # vectors.npy の shape を返す
    # - 無い場合は (0, 0)
    # - 1次元配列は (len, 1) とみなす
    # -------------------------------------------------------------------------
    p = Path(vectors_path)
    if not p.exists():
        return (0, 0)

    arr = np.load(p, mmap_mode="r")

    if arr.ndim == 0:
        return (0, 0)

    if arr.ndim == 1:
        return (int(arr.shape[0]), 1)

    return (int(arr.shape[0]), int(arr.shape[1]))


# =============================================================================
# helper：status message
# =============================================================================
def _build_status_message(
    *,
    vectors_row_count: int,
    meta_count: int,
    has_integrity_error: bool,
) -> tuple[bool, str, str]:
    # -------------------------------------------------------------------------
    # 再構築必要性を判定して
    # (needs_rebuild, level, message) を返す
    # -------------------------------------------------------------------------
    diff = int(vectors_row_count) - int(meta_count)

    if has_integrity_error:
        return (
            False,
            "error",
            "meta.jsonl または processed_files.json に整合性エラーがあります。"
            " 先にファイルの修正が必要です。",
        )

    if diff == 0:
        return (
            False,
            "info",
            "vectors.npy の行数と meta.jsonl の件数は一致しています。"
            " 現時点では shard 再構築は必須ではありません。",
        )

    if diff > 0:
        return (
            True,
            "warning",
            "vectors.npy の行数が meta.jsonl の件数を上回っています。"
            " shard 全体の clean rebuild を推奨します。",
        )

    return (
        True,
        "warning",
        "meta.jsonl の件数が vectors.npy の行数を上回っています。"
        " shard 内に不整合がある可能性があるため、"
        " shard 全体の clean rebuild を推奨します。",
    )


# =============================================================================
# public：status
# =============================================================================
def build_shard_rebuild_status(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> ShardRebuildStatus:
    # -------------------------------------------------------------------------
    # shard の再構築判定情報を返す
    # -------------------------------------------------------------------------
    shard_dir = get_shard_dir(
        databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    vectors_path = get_vectors_path(
        databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )
    meta_path = get_meta_path(
        databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )
    processed_path = get_processed_path(
        databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    state = load_shard_doc_state(
        Path(databases_root),
        collection_id=str(collection_id),
        shard_id=str(shard_id),
    )

    vectors_row_count, vectors_dim = get_vectors_shape(vectors_path)
    meta_count = len(state.meta_records)
    processed_count = len(state.processed_records)

    has_integrity_error = bool(
        state.meta_json_error_rows
        or state.meta_parse_errors
        or state.processed_json_error
        or state.processed_parse_errors
    )

    needs_rebuild, level, message = _build_status_message(
        vectors_row_count=vectors_row_count,
        meta_count=meta_count,
        has_integrity_error=has_integrity_error,
    )

    return ShardRebuildStatus(
        collection_id=str(collection_id),
        shard_id=str(shard_id),
        shard_dir=shard_dir,
        vectors_exists=vectors_path.exists(),
        meta_exists=meta_path.exists(),
        processed_exists=processed_path.exists(),
        vectors_row_count=int(vectors_row_count),
        vectors_dim=int(vectors_dim),
        meta_count=int(meta_count),
        processed_count=int(processed_count),
        diff_vectors_minus_meta=int(vectors_row_count - meta_count),
        meta_json_error_rows=list(state.meta_json_error_rows),
        meta_parse_errors=list(state.meta_parse_errors),
        processed_json_error=bool(state.processed_json_error),
        processed_parse_errors=list(state.processed_parse_errors),
        needs_rebuild=bool(needs_rebuild),
        level=str(level),
        message=str(message),
    )


# =============================================================================
# helper：backup
# =============================================================================
def create_shard_rebuild_backup(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    backup_root_name: str = "_rebuild_backups",
) -> Path:
    # -------------------------------------------------------------------------
    # shard 再構築前バックアップを作成する
    # -------------------------------------------------------------------------
    shard_dir = get_shard_dir(
        databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    if not shard_dir.exists():
        raise FileNotFoundError(f"shard dir が存在しません: {shard_dir}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = shard_dir / backup_root_name / ts
    backup_dir.mkdir(parents=True, exist_ok=False)

    for name in ("vectors.npy", "meta.jsonl", "processed_files.json"):
        src = shard_dir / name
        if src.exists():
            shutil.copy2(src, backup_dir / name)

    return backup_dir


# =============================================================================
# helper：doc_id parse（project）
# =============================================================================
def _parse_project_doc_id(doc_id: str) -> tuple[int, str, str]:
    # -------------------------------------------------------------------------
    # project doc_id を分解する
    # 形式：
    #   <year>/<pno>/<pdf_filename>
    # -------------------------------------------------------------------------
    s = str(doc_id or "").strip().replace("\\", "/")
    parts = s.split("/", 2)

    if len(parts) != 3:
        raise ValueError(f"project doc_id 形式が不正です: {doc_id}")

    year = int(parts[0])
    pno = str(parts[1]).zfill(3)
    pdf_filename = str(parts[2]).strip()

    if not pdf_filename:
        raise ValueError(f"pdf_filename が空です: {doc_id}")

    return (year, pno, pdf_filename)


# =============================================================================
# helper：choose embed model
# =============================================================================
def _choose_embed_model_for_doc(
    *,
    doc_id: str,
    state,
) -> str:
    # -------------------------------------------------------------------------
    # doc ごとの embed_model を決める
    #
    # 優先順位：
    # - processed_records
    # - meta_records
    # -------------------------------------------------------------------------
    for rec in state.processed_records:
        if str(getattr(rec, "doc_id", "") or "") == str(doc_id):
            model = str(getattr(rec, "embed_model", "") or "").strip()
            if model:
                return model

    for rec in state.meta_records:
        if str(getattr(rec, "doc_id", "") or "") == str(doc_id):
            model = str(getattr(rec, "embed_model", "") or "").strip()
            if model:
                return model

    raise ValueError(f"embed_model を決定できません: {doc_id}")


# =============================================================================
# helper：choose pdf lock flag
# =============================================================================
def _choose_pdf_lock_flag_for_project_doc(
    *,
    doc_id: str,
    state,
) -> int:
    # -------------------------------------------------------------------------
    # 現在の shard から pdf_lock_flag は取れないので、
    # rebuild source 解決時は 1 を既定とする
    #
    # 理由：
    # - resolve_project_report_source() は image PDF の場合のみ
    #   pdf_lock_flag=1 を要求する
    # - 既に shard に存在する doc は、少なくとも過去に ingest できた文書なので、
    #   rebuild 時にも source 解決を試みる価値がある
    # -------------------------------------------------------------------------
    _ = doc_id
    _ = state
    return 1


# =============================================================================
# public：project shard sources
# =============================================================================
def collect_project_shard_sources(
    projects_root: Path,
    databases_root: Path,
    *,
    shard_id: str,
) -> ProjectShardSourceCollectResult:
    # -------------------------------------------------------------------------
    # 既存 shard から project 用 IngestSource 一覧を再構成する
    # -------------------------------------------------------------------------
    state = load_shard_doc_state(
        databases_root=Path(databases_root),
        collection_id="project",
        shard_id=str(shard_id),
    )

    # -------------------------------------------------------------------------
    # 前提チェック
    # -------------------------------------------------------------------------
    if state.meta_json_error_rows:
        raise ValueError("meta.jsonl に JSON エラー行があるため source 再構成できません。")

    if state.meta_parse_errors:
        raise ValueError("meta.jsonl に復元エラーがあるため source 再構成できません。")

    if state.processed_json_error:
        raise ValueError("processed_files.json が list 形式ではないため source 再構成できません。")

    if state.processed_parse_errors:
        raise ValueError("processed_files.json に復元エラーがあるため source 再構成できません。")

    # -------------------------------------------------------------------------
    # doc 一覧
    # - processed を優先
    # - 無ければ meta から補う
    # -------------------------------------------------------------------------
    doc_ids_from_processed = {
        str(getattr(rec, "doc_id", "") or "").strip()
        for rec in state.processed_records
        if str(getattr(rec, "doc_id", "") or "").strip()
    }
    doc_ids_from_meta = {
        str(getattr(rec, "doc_id", "") or "").strip()
        for rec in state.meta_records
        if str(getattr(rec, "doc_id", "") or "").strip()
    }

    all_doc_ids = sorted(doc_ids_from_processed | doc_ids_from_meta)

    out_sources: list[IngestSource] = []
    skipped_rows: list[dict[str, Any]] = []

    for doc_id in all_doc_ids:
        try:
            year, pno, pdf_filename = _parse_project_doc_id(doc_id)
            embed_model = _choose_embed_model_for_doc(doc_id=doc_id, state=state)
            pdf_lock_flag = _choose_pdf_lock_flag_for_project_doc(doc_id=doc_id, state=state)

            res = resolve_project_report_source(
                Path(projects_root),
                project_year=int(year),
                project_no=str(pno),
                pdf_filename=str(pdf_filename),
                embed_model=str(embed_model),
                pdf_lock_flag=int(pdf_lock_flag),
            )

            if not res.ok or res.source is None:
                skipped_rows.append(
                    {
                        "doc_id": str(doc_id),
                        "year": int(year),
                        "pno": str(pno),
                        "filename": str(pdf_filename),
                        "embed_model": str(embed_model),
                        "message": str(res.message or "source 解決不可"),
                    }
                )
                continue

            out_sources.append(res.source)

        except Exception as e:
            skipped_rows.append(
                {
                    "doc_id": str(doc_id),
                    "year": None,
                    "pno": "",
                    "filename": "",
                    "embed_model": "",
                    "message": f"doc source 再構成中に例外: {e}",
                }
            )

    return ProjectShardSourceCollectResult(
        collection_id="project",
        shard_id=str(shard_id),
        source_count=len(out_sources),
        skipped_count=len(skipped_rows),
        sources=out_sources,
        skipped_rows=skipped_rows,
    )


# =============================================================================
# public：plan
# =============================================================================
def build_project_shard_rebuild_plan(
    projects_root: Path,
    databases_root: Path,
    *,
    shard_id: str,
) -> ShardRebuildPlan:
    # -------------------------------------------------------------------------
    # project shard の clean rebuild 事前計画を返す
    # -------------------------------------------------------------------------
    status = build_shard_rebuild_status(
        databases_root=Path(databases_root),
        collection_id="project",
        shard_id=str(shard_id),
    )

    collect_result = collect_project_shard_sources(
        projects_root=Path(projects_root),
        databases_root=Path(databases_root),
        shard_id=str(shard_id),
    )

    embed_models = sorted(
        {
            str(src.embed_model or "").strip()
            for src in collect_result.sources
            if str(src.embed_model or "").strip()
        }
    )

    return ShardRebuildPlan(
        collection_id="project",
        shard_id=str(shard_id),
        old_vectors_row_count=int(status.vectors_row_count),
        old_meta_count=int(status.meta_count),
        old_processed_count=int(status.processed_count),
        target_doc_count=int(collect_result.source_count),
        skipped_doc_count=int(collect_result.skipped_count),
        embed_models=embed_models,
    )


# =============================================================================
# helper：concat vectors
# =============================================================================
def _concat_vectors(payloads: list[PreparedDocumentPayload]) -> np.ndarray:
    # -------------------------------------------------------------------------
    # payload 群の vectors を結合する
    # -------------------------------------------------------------------------
    if not payloads:
        return np.empty((0, 0), dtype=np.float32)

    arrays = [np.asarray(x.new_vectors, dtype=np.float32) for x in payloads]

    if not arrays:
        return np.empty((0, 0), dtype=np.float32)

    if len(arrays) == 1:
        return arrays[0]

    return np.vstack(arrays)


# =============================================================================
# helper：build payloads for shard rebuild
# =============================================================================
def _prepare_project_shard_payloads(
    projects_root: Path,
    *,
    user_sub: str,
    app_name: str,
    page_name: str,
    sources: list[IngestSource],
    chunk_options: Optional[ChunkOptions],
) -> list[PreparedDocumentPayload]:
    # -------------------------------------------------------------------------
    # project shard rebuild 用に全 source の payload を構築する
    #
    # 方針：
    # - vector_index は shard 全体で 0 から連番
    # -------------------------------------------------------------------------
    payloads: list[PreparedDocumentPayload] = []
    next_vector_index = 0

    for src in sources:
        payload = prepare_one_document_payload(
            projects_root=Path(projects_root),
            user_sub=str(user_sub),
            app_name=str(app_name),
            page_name=str(page_name),
            source=src,
            start_vector_index=int(next_vector_index),
            chunk_options=chunk_options,
        )

        payloads.append(payload)
        next_vector_index += len(payload.meta_records)

    return payloads


# =============================================================================
# public：clean rebuild
# =============================================================================
def clean_rebuild_project_shard(
    projects_root: Path,
    databases_root: Path,
    *,
    shard_id: str,
    actor: str,
    create_backup: bool = True,
    chunk_options: Optional[ChunkOptions] = None,
    user_sub: Optional[str] = None,
    app_name: str = "rag_builder_app",
    page_name: str = "350_シャード再構築",
) -> ShardRebuildResult:
    # -------------------------------------------------------------------------
    # project shard を clean rebuild する
    #
    # flow:
    # 1. status 確認
    # 2. source 収集
    # 3. 全 doc の payload 構築
    # 4. vectors / meta / processed を全生成
    # 5. backup
    # 6. save_vectorstore_snapshot() で全保存
    # -------------------------------------------------------------------------
    status = build_shard_rebuild_status(
        databases_root=Path(databases_root),
        collection_id="project",
        shard_id=str(shard_id),
    )

    if status.level == "error":
        raise ValueError(status.message)

    collect_result = collect_project_shard_sources(
        projects_root=Path(projects_root),
        databases_root=Path(databases_root),
        shard_id=str(shard_id),
    )

    if collect_result.skipped_rows:
        raise ValueError(
            "source 解決に失敗した doc があるため clean rebuild を中止しました。"
            f" skipped={len(collect_result.skipped_rows)}"
        )

    if not collect_result.sources:
        raise ValueError("再構築対象の source がありません。")

    effective_user_sub = str(user_sub or actor or "").strip()
    if not effective_user_sub:
        raise ValueError("user_sub / actor が空です。")

    payloads = _prepare_project_shard_payloads(
        projects_root=Path(projects_root),
        user_sub=effective_user_sub,
        app_name=str(app_name),
        page_name=str(page_name),
        sources=collect_result.sources,
        chunk_options=chunk_options,
    )

    new_vectors = _concat_vectors(payloads)

    new_meta_records: list[MetaRecord] = []
    new_processed_records: list[ProcessedFileRecord] = []

    for payload in payloads:
        new_meta_records.extend(payload.meta_records)
        new_processed_records.append(payload.processed_record)

    backup_dir: Optional[Path] = None
    if create_backup:
        backup_dir = create_shard_rebuild_backup(
            databases_root=Path(databases_root),
            collection_id="project",
            shard_id=str(shard_id),
        )

    save_vectorstore_snapshot(
        databases_root=Path(databases_root),
        collection_id="project",
        shard_id=str(shard_id),
        vectors=new_vectors,
        meta_records=new_meta_records,
        processed_records=new_processed_records,
    )

    new_status = build_shard_rebuild_status(
        databases_root=Path(databases_root),
        collection_id="project",
        shard_id=str(shard_id),
    )

    rebuilt_at = datetime.now().isoformat(timespec="seconds")

    return ShardRebuildResult(
        ok=True,
        message=(
            "shard clean rebuild を実行しました。"
            f" docs={len(collect_result.sources)}"
            f" | vectors={new_status.vectors_row_count}"
            f" | meta={new_status.meta_count}"
            f" | processed={new_status.processed_count}"
        ),
        collection_id="project",
        shard_id=str(shard_id),
        shard_dir=str(get_shard_dir(
            Path(databases_root),
            collection_id="project",
            shard_id=str(shard_id),
        )),
        backup_dir=str(backup_dir) if backup_dir else None,
        old_vectors_row_count=int(status.vectors_row_count),
        old_meta_count=int(status.meta_count),
        old_processed_count=int(status.processed_count),
        new_vectors_row_count=int(new_status.vectors_row_count),
        new_meta_count=int(new_status.meta_count),
        new_processed_count=int(new_status.processed_count),
        actor=str(actor),
        rebuilt_at=str(rebuilt_at),
    )


# =============================================================================
# public：summary rows
# =============================================================================
def build_rebuild_summary_rows(status: ShardRebuildStatus) -> list[dict[str, Any]]:
    # -------------------------------------------------------------------------
    # page 表示用の要約行を返す
    # -------------------------------------------------------------------------
    return [
        {"項目": "vectors 行数", "値": int(status.vectors_row_count)},
        {"項目": "vectors 次元", "値": int(status.vectors_dim)},
        {"項目": "meta 件数", "値": int(status.meta_count)},
        {"項目": "processed 件数", "値": int(status.processed_count)},
        {"項目": "差分（vectors - meta）", "値": int(status.diff_vectors_minus_meta)},
        {"項目": "再構築必要性", "値": str(status.message)},
    ]


# =============================================================================
# public：plan rows
# =============================================================================
def build_rebuild_plan_rows(plan: ShardRebuildPlan) -> list[dict[str, Any]]:
    # -------------------------------------------------------------------------
    # page 表示用の計画行を返す
    # -------------------------------------------------------------------------
    return [
        {"項目": "old vectors 行数", "値": int(plan.old_vectors_row_count)},
        {"項目": "old meta 件数", "値": int(plan.old_meta_count)},
        {"項目": "old processed 件数", "値": int(plan.old_processed_count)},
        {"項目": "再構築対象 doc 数", "値": int(plan.target_doc_count)},
        {"項目": "source 解決失敗 doc 数", "値": int(plan.skipped_doc_count)},
        {"項目": "embed_models", "値": ", ".join(plan.embed_models) if plan.embed_models else ""},
    ]


# =============================================================================
# public：result rows
# =============================================================================
def build_rebuild_result_rows(result: ShardRebuildResult) -> list[dict[str, Any]]:
    # -------------------------------------------------------------------------
    # page 表示用の結果行を返す
    # -------------------------------------------------------------------------
    return [
        {"項目": "old vectors 行数", "値": int(result.old_vectors_row_count)},
        {"項目": "new vectors 行数", "値": int(result.new_vectors_row_count)},
        {"項目": "old meta 件数", "値": int(result.old_meta_count)},
        {"項目": "new meta 件数", "値": int(result.new_meta_count)},
        {"項目": "old processed 件数", "値": int(result.old_processed_count)},
        {"項目": "new processed 件数", "値": int(result.new_processed_count)},
        {"項目": "actor", "値": str(result.actor)},
        {"項目": "rebuilt_at", "値": str(result.rebuilt_at)},
    ]