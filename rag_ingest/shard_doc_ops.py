# common_lib/rag_ingest/shard_doc_ops.py
# =============================================================================
# shard doc operations（RAG ingest 共通ライブラリ）
#
# 役割：
# - shard（Databases/vectorstore/<collection_id>/<shard_id>/）を読み込む
# - meta.jsonl / processed_files.json から doc 単位集計を作る
# - 選択 doc の削除予定件数を集計する
# - 選択 doc を shard から登録解除する
#   - meta.jsonl から除外
#   - processed_files.json から除外
#   - processing_status.json を not_ingested に戻す
#
# 重要方針：
# - vectors.npy は append only のため、このモジュールでは一切変更しない
# - meta.jsonl を metadata の正本として扱う
# - 検索対象は meta.jsonl に残っている doc のみ
# - collection_id は可変（project / rules / manual / minutes など）
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports（stdlib）
# =============================================================================
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil

# =============================================================================
# common_lib（rag_ingest）
# =============================================================================
from common_lib.rag_ingest.paths import resolve_vectorstore_paths
from common_lib.rag_ingest.manifest_ops import (
    meta_record_from_dict,
    processed_file_record_from_dict,
)

# =============================================================================
# dataclass：load result
# =============================================================================
@dataclass
class ShardDocState:
    # -------------------------------------------------------------------------
    # shard 読込結果
    # -------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    shard_dir: Path
    meta_path: Path
    processed_path: Path
    vectors_path: Path

    meta_raw_rows: list[dict]
    processed_raw_rows: list[dict]

    meta_records: list
    processed_records: list

    meta_json_error_rows: list[dict]
    meta_parse_errors: list[dict]

    processed_json_error: bool
    processed_parse_errors: list[dict]


# =============================================================================
# helper：timestamp
# =============================================================================
def _now_iso_utc() -> str:
    # -------------------------------------------------------------------------
    # UTC の ISO 文字列を返す
    # -------------------------------------------------------------------------
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
# helper：jsonl write
# =============================================================================
def _write_jsonl(path: Path, rows: list[dict]) -> None:
    # -------------------------------------------------------------------------
    # JSONL を上書き保存する
    # -------------------------------------------------------------------------
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# =============================================================================
# helper：json write
# =============================================================================
def _write_json(path: Path, data) -> None:
    # -------------------------------------------------------------------------
    # JSON を上書き保存する
    # -------------------------------------------------------------------------
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =============================================================================
# helper：backup
# =============================================================================
def _backup_before_delete(
    *,
    shard_dir: Path,
    meta_path: Path,
    processed_path: Path,
) -> Path:
    # -------------------------------------------------------------------------
    # 削除前バックアップを作成する
    # -------------------------------------------------------------------------
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = shard_dir / "_backups" / "doc_delete" / ts
    backup_dir.mkdir(parents=True, exist_ok=True)

    if meta_path.exists():
        shutil.copy2(meta_path, backup_dir / meta_path.name)

    if processed_path.exists():
        shutil.copy2(processed_path, backup_dir / processed_path.name)

    return backup_dir


# =============================================================================
# helper：processing status path
# =============================================================================
def _resolve_processing_status_path_from_meta_row(row: dict) -> Path | None:
    # -------------------------------------------------------------------------
    # meta row から processing_status.json の想定パスを求める
    #
    # 前提：
    # - source_text_path が保存されている
    # - 例：
    #   Archive/project/2019/009/text/report_clean.txt
    #   → Archive/project/2019/009/text/processing_status.json
    #
    # 注意：
    # - collection_id が project 以外でも、source_text_path の親に
    #   processing_status.json がある前提で共通に扱う
    # -------------------------------------------------------------------------
    source_text_path = str(row.get("source_text_path") or "").strip()
    if not source_text_path:
        return None

    p = Path(source_text_path)
    return p.parent / "processing_status.json"


# =============================================================================
# helper：reset processing status
# =============================================================================
def _reset_processing_status(
    *,
    processing_status_path: Path,
    actor: str | None,
) -> tuple[bool, str]:
    # -------------------------------------------------------------------------
    # processing_status.json を not_ingested に戻す
    # -------------------------------------------------------------------------
    if not processing_status_path.exists():
        return False, f"processing_status.json が存在しません: {processing_status_path}"

    try:
        with processing_status_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return False, "processing_status.json が dict 形式ではありません。"

        data["rag_status"] = "not_ingested"
        data["rag_ingested_at"] = None
        data["rag_ingested_by"] = None
        data["updated_at"] = _now_iso_utc()
        data["updated_by"] = str(actor or "")
        data["note"] = "manual doc delete from shard"

        with processing_status_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return True, "ok"

    except Exception as e:
        return False, str(e)


# =============================================================================
# public：load shard doc state
# =============================================================================
def load_shard_doc_state(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
) -> ShardDocState:
    # -------------------------------------------------------------------------
    # shard の doc 状態を読み込む
    # -------------------------------------------------------------------------
    collection_id = str(collection_id)
    shard_id = str(shard_id)

    paths = resolve_vectorstore_paths(
        databases_root=databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    meta_raw_rows = _read_jsonl(paths.meta_path)
    processed_raw_obj = _read_json(paths.processed_path)

    meta_json_error_rows = [x for x in meta_raw_rows if x.get("__json_error__")]
    meta_rows_ok = [x for x in meta_raw_rows if not x.get("__json_error__")]

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

    processed_json_error = False
    if isinstance(processed_raw_obj, list):
        processed_raw_rows = processed_raw_obj
    else:
        processed_json_error = True
        processed_raw_rows = []

    processed_records = []
    processed_parse_errors = []

    for idx, row in enumerate(processed_raw_rows):
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

    return ShardDocState(
        collection_id=collection_id,
        shard_id=shard_id,
        shard_dir=paths.shard_dir,
        meta_path=paths.meta_path,
        processed_path=paths.processed_path,
        vectors_path=paths.vectors_path,
        meta_raw_rows=meta_raw_rows,
        processed_raw_rows=processed_raw_rows,
        meta_records=meta_records,
        processed_records=processed_records,
        meta_json_error_rows=meta_json_error_rows,
        meta_parse_errors=meta_parse_errors,
        processed_json_error=processed_json_error,
        processed_parse_errors=processed_parse_errors,
    )


# =============================================================================
# public：build doc summary rows
# =============================================================================
def build_doc_summary_rows(
    *,
    meta_records: list,
    processed_records: list,
) -> list[dict]:
    # -------------------------------------------------------------------------
    # doc 単位一覧を作る
    # -------------------------------------------------------------------------
    doc_meta_rows: dict[str, list] = defaultdict(list)

    for rec in meta_records:
        doc_meta_rows[str(rec.doc_id)].append(rec)

    processed_by_doc: dict[str, list] = defaultdict(list)
    for rec in processed_records:
        processed_by_doc[str(rec.doc_id)].append(rec)

    all_doc_ids = sorted(set(doc_meta_rows.keys()) | set(processed_by_doc.keys()))

    rows: list[dict] = []

    for doc_id in all_doc_ids:
        meta_list = doc_meta_rows.get(doc_id, [])
        processed_list = processed_by_doc.get(doc_id, [])

        file_name = ""
        ingested_at = ""
        vector_index_min = None
        vector_index_max = None

        if meta_list:
            file_name = str(
                getattr(meta_list[0], "file_name", "")
                or getattr(meta_list[0], "file", "")
                or ""
            )
            ingested_at = str(getattr(meta_list[0], "ingested_at", "") or "")
            vis = [int(x.vector_index) for x in meta_list]
            if vis:
                vector_index_min = min(vis)
                vector_index_max = max(vis)
        elif processed_list:
            file_name = str(getattr(processed_list[0], "file", "") or "")
            ingested_at = str(getattr(processed_list[0], "ingested_at", "") or "")

        processed_exists = bool(processed_list)
        meta_count = len(meta_list)

        if meta_list and processed_list:
            note = "正常"
        elif meta_list and not processed_list:
            note = "meta のみ存在"
        elif not meta_list and processed_list:
            note = "processed のみ存在"
        else:
            note = "不明"

        rows.append(
            {
                "doc_id": str(doc_id),
                "file_name": str(file_name),
                "meta_count": int(meta_count),
                "processed_exists": bool(processed_exists),
                "ingested_at": str(ingested_at),
                "vector_index_min": vector_index_min,
                "vector_index_max": vector_index_max,
                "note": str(note),
            }
        )

    rows.sort(
        key=lambda x: (
            str(x["doc_id"]),
            str(x["file_name"]),
        )
    )

    return rows


# =============================================================================
# public：build delete plan
# =============================================================================
def build_delete_plan(
    *,
    state: ShardDocState,
    selected_doc_ids: list[str],
) -> dict:
    # -------------------------------------------------------------------------
    # 削除予定件数を集計する
    # -------------------------------------------------------------------------
    selected_set = {str(x) for x in selected_doc_ids if str(x).strip()}

    meta_delete_count = sum(
        1
        for rec in state.meta_records
        if str(rec.doc_id) in selected_set
    )

    processed_delete_count = sum(
        1
        for rec in state.processed_records
        if str(rec.doc_id) in selected_set
    )

    processing_status_targets: set[str] = set()

    for row in state.meta_raw_rows:
        if row.get("__json_error__"):
            continue

        doc_id = str(row.get("doc_id") or "")
        if doc_id not in selected_set:
            continue

        ps = _resolve_processing_status_path_from_meta_row(row)
        if ps is not None:
            processing_status_targets.add(str(ps))

    return {
        "selected_doc_count": int(len(selected_set)),
        "delete_meta_count": int(meta_delete_count),
        "delete_processed_count": int(processed_delete_count),
        "reset_status_count": int(len(processing_status_targets)),
        "selected_doc_ids": sorted(selected_set),
        "processing_status_paths": sorted(processing_status_targets),
    }


# =============================================================================
# public：deregister docs from shard
# =============================================================================
def deregister_docs_from_shard(
    databases_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    selected_doc_ids: list[str],
    actor: str | None = None,
    create_backup: bool = True,
) -> dict:
    # -------------------------------------------------------------------------
    # 選択 doc を shard から登録解除する
    #
    # 処理：
    # - meta.jsonl から除外
    # - processed_files.json から除外
    # - processing_status.json を not_ingested に戻す
    #
    # 注意：
    # - vectors.npy は変更しない
    # -------------------------------------------------------------------------
    collection_id = str(collection_id)
    shard_id = str(shard_id)

    state = load_shard_doc_state(
        databases_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    selected_set = {str(x) for x in selected_doc_ids if str(x).strip()}

    if not selected_set:
        return {
            "ok": False,
            "message": "選択 doc がありません。",
            "backup_dir": None,
            "result_rows": [],
            "delete_plan": build_delete_plan(state=state, selected_doc_ids=[]),
        }

    # -------------------------------------------------------------------------
    # 前提チェック
    # -------------------------------------------------------------------------
    if state.meta_json_error_rows:
        return {
            "ok": False,
            "message": "meta.jsonl に JSON エラー行があるため削除を中止しました。",
            "backup_dir": None,
            "result_rows": [],
            "delete_plan": build_delete_plan(
                state=state,
                selected_doc_ids=list(selected_set),
            ),
        }

    if state.meta_parse_errors:
        return {
            "ok": False,
            "message": "meta.jsonl に復元エラーがあるため削除を中止しました。",
            "backup_dir": None,
            "result_rows": [],
            "delete_plan": build_delete_plan(
                state=state,
                selected_doc_ids=list(selected_set),
            ),
        }

    if state.processed_json_error:
        return {
            "ok": False,
            "message": "processed_files.json が list 形式ではないため削除を中止しました。",
            "backup_dir": None,
            "result_rows": [],
            "delete_plan": build_delete_plan(
                state=state,
                selected_doc_ids=list(selected_set),
            ),
        }

    if state.processed_parse_errors:
        return {
            "ok": False,
            "message": "processed_files.json に復元エラーがあるため削除を中止しました。",
            "backup_dir": None,
            "result_rows": [],
            "delete_plan": build_delete_plan(
                state=state,
                selected_doc_ids=list(selected_set),
            ),
        }

    delete_plan = build_delete_plan(
        state=state,
        selected_doc_ids=list(selected_set),
    )

    # -------------------------------------------------------------------------
    # バックアップ
    # -------------------------------------------------------------------------
    backup_dir = None
    if create_backup:
        backup_dir = _backup_before_delete(
            shard_dir=state.shard_dir,
            meta_path=state.meta_path,
            processed_path=state.processed_path,
        )

    # -------------------------------------------------------------------------
    # raw rows を doc_id で除外
    # -------------------------------------------------------------------------
    filtered_meta_rows = [
        row
        for row in state.meta_raw_rows
        if not row.get("__json_error__")
        and str(row.get("doc_id") or "") not in selected_set
    ]

    filtered_processed_rows = [
        row
        for row in state.processed_raw_rows
        if str(row.get("doc_id") or "") not in selected_set
    ]

    # -------------------------------------------------------------------------
    # 保存
    # -------------------------------------------------------------------------
    _write_jsonl(state.meta_path, filtered_meta_rows)
    _write_json(state.processed_path, filtered_processed_rows)

    # -------------------------------------------------------------------------
    # processing_status 更新対象を収集
    # -------------------------------------------------------------------------
    processing_status_by_doc: dict[str, set[Path]] = defaultdict(set)

    for row in state.meta_raw_rows:
        if row.get("__json_error__"):
            continue

        doc_id = str(row.get("doc_id") or "")
        if doc_id not in selected_set:
            continue

        ps = _resolve_processing_status_path_from_meta_row(row)
        if ps is not None:
            processing_status_by_doc[doc_id].add(ps)

    # -------------------------------------------------------------------------
    # doc ごとの結果行を作る
    # -------------------------------------------------------------------------
    meta_counter = Counter(
        str(getattr(rec, "doc_id", ""))
        for rec in state.meta_records
    )

    processed_counter = Counter(
        str(getattr(rec, "doc_id", ""))
        for rec in state.processed_records
    )

    result_rows: list[dict] = []

    for doc_id in sorted(selected_set):
        meta_deleted = int(meta_counter.get(doc_id, 0))
        processed_deleted = int(processed_counter.get(doc_id, 0))

        status_paths = sorted(processing_status_by_doc.get(doc_id, set()))
        status_reset_ok = True
        status_messages: list[str] = []

        if not status_paths:
            status_reset_ok = False
            status_messages.append("processing_status.json の対象が見つかりません。")
        else:
            for ps in status_paths:
                ok, msg = _reset_processing_status(
                    processing_status_path=ps,
                    actor=actor,
                )
                if not ok:
                    status_reset_ok = False
                status_messages.append(f"{ps}: {msg}")

        if status_reset_ok:
            final_status = "success"
        elif meta_deleted > 0 or processed_deleted > 0:
            final_status = "partial_success"
        else:
            final_status = "failed"

        result_rows.append(
            {
                "collection_id": collection_id,
                "shard_id": shard_id,
                "doc_id": str(doc_id),
                "meta_deleted_count": int(meta_deleted),
                "processed_deleted_count": int(processed_deleted),
                "status_reset_ok": bool(status_reset_ok),
                "final_status": str(final_status),
                "message": " | ".join(status_messages) if status_messages else "",
            }
        )

    return {
        "ok": True,
        "message": "doc 登録解除を実行しました。",
        "backup_dir": str(backup_dir) if backup_dir is not None else None,
        "result_rows": result_rows,
        "delete_plan": delete_plan,
    }


# =============================================================================
# backward compatibility：project 固定ラッパー
# =============================================================================
def load_project_shard_doc_state(
    databases_root: Path,
    *,
    shard_id: str,
) -> ShardDocState:
    # -------------------------------------------------------------------------
    # project 固定互換ラッパー
    # -------------------------------------------------------------------------
    return load_shard_doc_state(
        databases_root,
        collection_id="project",
        shard_id=str(shard_id),
    )


# =============================================================================
# backward compatibility：project 固定ラッパー
# =============================================================================
def deregister_docs_from_project_shard(
    databases_root: Path,
    *,
    shard_id: str,
    selected_doc_ids: list[str],
    actor: str | None = None,
    create_backup: bool = True,
) -> dict:
    # -------------------------------------------------------------------------
    # project 固定互換ラッパー
    # -------------------------------------------------------------------------
    return deregister_docs_from_shard(
        databases_root,
        collection_id="project",
        shard_id=str(shard_id),
        selected_doc_ids=selected_doc_ids,
        actor=actor,
        create_backup=create_backup,
    )