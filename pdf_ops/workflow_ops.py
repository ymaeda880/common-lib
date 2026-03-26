# -*- coding: utf-8 -*-
# common_lib/pdf_ops/workflow_ops.py
# ============================================================
# PDF workflow（汎用PDF保守の実行フロー）
#
# 役割：
# - shard 内の未展開PDFを doc レイアウトへ展開する
# - 展開済みPDFを解析し、text PDF の raw text を抽出する
# - pdf_status.json / processing_status.json の正本更新を行う
# - 例外時に error status を正本へ記録する
#
# 方針：
# - UI依存の処理は持たない
# - Archive/<collection_id>/... 配下の generic PDF collection を対象とする
# - status 更新は page 側ではなく、この workflow 側で完結させる
# - text 抽出は既存の extract_text_direct を正本として用いる
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ============================================================
# imports（pdf_catalog）
# ============================================================
from common_lib.pdf_catalog import (
    list_source_pdfs_by_shard,
    get_doc_pdf_dir,
    get_doc_pdf_status_path,
    get_source_pdf_path,
    ensure_doc_layout_dirs,
)

from common_lib.pdf_catalog.paths import (
    get_raw_text_path,
    get_raw_pages_json_path,
)

from common_lib.pdf_catalog.processing_status_ops import (
    upsert_pdf_info_status,
    mark_text_extracted,
    upsert_error_status,
)

# ============================================================
# imports（pdf_ops / pdf_tools）
# ============================================================
from common_lib.pdf_ops.analyze_ops import (
    classify_pdf_and_extract_page_texts,
    write_raw_text_outputs,
)

from common_lib.pdf_tools.text_extract.extract import (
    extract_text_direct,
)

# ============================================================
# imports（utils）
# ============================================================
from common_lib.utils.hash_ops import (
    sha256_of_bytes,
)

# ============================================================
# helpers（time / json）
# ============================================================
def _now_iso_jst() -> str:
    # ------------------------------------------------------------
    # JST の ISO文字列
    # ------------------------------------------------------------
    return datetime.now(ZoneInfo("Asia/Tokyo")).replace(microsecond=0).isoformat()


def _write_json_pretty(path: Path, data: dict | list) -> None:
    # ------------------------------------------------------------
    # JSONを書き込む
    # ------------------------------------------------------------
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# helpers（pdf_status）
# ============================================================
def _write_pdf_status_registered(
    *,
    archive_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    done_by: str,
) -> None:
    # ------------------------------------------------------------
    # pdf_status.json を作成する
    # ------------------------------------------------------------
    path = get_doc_pdf_status_path(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    data = {
        "registered_at": _now_iso_jst(),
        "registered_by": str(done_by),
    }
    _write_json_pretty(path, data)


# ============================================================
# public：expand
# ============================================================
def expand_docs_for_shard(
    *,
    archive_root: Path,
    collection_id: str,
    shard_id: str,
    done_by: str,
) -> tuple[str, list[str]]:
    # ------------------------------------------------------------
    # shard 内の未展開PDFを doc レイアウトへ展開する
    #
    # 実施内容：
    # - doc layout directory 作成
    # - pdf/ に原本PDFをコピー
    # - pdf/pdf_status.json を作成
    #
    # 注意：
    # - processing_status.json はここでは作成しない
    # ------------------------------------------------------------
    records = list_source_pdfs_by_shard(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    expanded_count = 0
    skipped_count = 0
    error_lines: list[str] = []

    for rec in records:
        try:
            ensure_doc_layout_dirs(
                archive_root,
                collection_id=collection_id,
                shard_id=shard_id,
                doc_id=rec.doc_id,
            )

            pdf_dir = get_doc_pdf_dir(
                archive_root,
                collection_id=collection_id,
                shard_id=shard_id,
                doc_id=rec.doc_id,
            )
            copied_pdf_path = pdf_dir / rec.pdf_filename

            pdf_status_path = get_doc_pdf_status_path(
                archive_root,
                collection_id=collection_id,
                shard_id=shard_id,
                doc_id=rec.doc_id,
            )

            if copied_pdf_path.exists() and pdf_status_path.exists():
                skipped_count += 1
                continue

            if not copied_pdf_path.exists():
                shutil.copy2(rec.pdf_path, copied_pdf_path)

            if not pdf_status_path.exists():
                _write_pdf_status_registered(
                    archive_root=archive_root,
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=rec.doc_id,
                    done_by=done_by,
                )

            expanded_count += 1

        except Exception as e:
            error_lines.append(f"{rec.doc_id} | {e}")

    msg = f"フォルダー展開: 新規 {expanded_count} 件 / skip {skipped_count} 件"
    return msg, error_lines


# ============================================================
# public：extract
# ============================================================
def extract_text_for_shard(
    *,
    archive_root: Path,
    collection_id: str,
    shard_id: str,
    done_by: str,
) -> tuple[str, list[str]]:
    # ------------------------------------------------------------
    # shard 内のPDFについて初回解析 + text抽出を行う
    #
    # 実施内容：
    # - 展開済みPDFを読む
    # - source_pdf_sha256 / pdf_kind / page_count を確定
    # - processing_status.json を作成 / 更新
    # - text PDF なら report_raw.txt / report_raw_pages.json を作成
    # - 抽出成功時は mark_text_extracted を記録
    # - 失敗時は upsert_error_status を記録
    # ------------------------------------------------------------
    records = list_source_pdfs_by_shard(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
    )

    processed_count = 0
    skipped_count = 0
    error_lines: list[str] = []

    for rec in records:
        try:
            copied_pdf_dir = get_doc_pdf_dir(
                archive_root,
                collection_id=collection_id,
                shard_id=shard_id,
                doc_id=rec.doc_id,
            )
            copied_pdf_path = copied_pdf_dir / rec.pdf_filename

            # ----------------------------------------------------
            # 展開前は処理しない
            # ----------------------------------------------------
            if not copied_pdf_path.exists():
                skipped_count += 1
                continue

            # ----------------------------------------------------
            # PDF解析
            # ----------------------------------------------------
            fitz, pdf_bytes, pdf_kind, page_count, page_texts = (
                classify_pdf_and_extract_page_texts(copied_pdf_path)
            )
            pdf_sha = sha256_of_bytes(pdf_bytes)

            # ----------------------------------------------------
            # pdf 基本情報を正本へ記録
            # ----------------------------------------------------
            upsert_pdf_info_status(
                archive_root,
                collection_id=collection_id,
                shard_id=shard_id,
                doc_id=rec.doc_id,
                source_pdf_filename=rec.pdf_filename,
                source_pdf_sha256=pdf_sha,
                pdf_kind=pdf_kind,
                page_count=page_count,
                done_by=done_by,
            )

            # ----------------------------------------------------
            # text PDF のみ raw text を作成
            # ----------------------------------------------------
            if pdf_kind == "text":
                raw_text = extract_text_direct(
                    fitz=fitz,
                    pdf_bytes=pdf_bytes,
                    page_start_0=0,
                    page_end_0_inclusive=max(0, int(page_count) - 1),
                )

                write_raw_text_outputs(
                    raw_path=get_raw_text_path(
                        archive_root,
                        collection_id=collection_id,
                        shard_id=shard_id,
                        doc_id=rec.doc_id,
                    ),
                    raw_pages_path=get_raw_pages_json_path(
                        archive_root,
                        collection_id=collection_id,
                        shard_id=shard_id,
                        doc_id=rec.doc_id,
                    ),
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=rec.doc_id,
                    pdf_filename=rec.pdf_filename,
                    source_pdf_sha256=pdf_sha,
                    raw_text=str(raw_text or ""),
                    page_texts=page_texts,
                )

                mark_text_extracted(
                    archive_root,
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=rec.doc_id,
                    done_by=done_by,
                )

            processed_count += 1

        except Exception as e:
            error_lines.append(f"{rec.doc_id} | {e}")

            # ----------------------------------------------------
            # error status を正本へ記録
            # ----------------------------------------------------
            try:
                source_pdf_path = get_source_pdf_path(
                    archive_root,
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=rec.doc_id,
                )

                copied_pdf_dir = get_doc_pdf_dir(
                    archive_root,
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=rec.doc_id,
                )
                copied_pdf_path = copied_pdf_dir / rec.pdf_filename

                target_pdf_path = copied_pdf_path if copied_pdf_path.exists() else source_pdf_path

                if target_pdf_path.exists():
                    pdf_bytes = target_pdf_path.read_bytes()
                    pdf_sha = sha256_of_bytes(pdf_bytes)
                else:
                    pdf_sha = ""

                upsert_error_status(
                    archive_root,
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=rec.doc_id,
                    source_pdf_filename=rec.pdf_filename,
                    source_pdf_sha256=pdf_sha,
                    pdf_kind="",
                    page_count=0,
                    done_by=done_by,
                    error_message=str(e),
                )
            except Exception:
                pass

    msg = f"テキスト抽出: 処理 {processed_count} 件 / skip {skipped_count} 件"
    return msg, error_lines