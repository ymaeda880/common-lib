# -*- coding: utf-8 -*-
# common_lib/pdf_ops/generic_ocr_ops.py
# ============================================================
# Generic PDF OCR / text / clean オペレーション（正本API）
#
# 役割：
# - generic PDF に対する OCR 実行
# - OCR済みPDFの保存
# - raw text / clean text / extract_meta.json の保存
# - clean後ページテキストの report_clean_pages.json 保存
# - text/processing_status.json の更新
#
# 設計方針：
# - path解決は common_lib.pdf_catalog を正本として使う
# - OCR / text抽出のエンジン本体は common_lib.pdf_tools.text_extract.extract を使う
# - OCR時に clean を行う場合は、clean後ページ単位テキストから
#   report_clean_pages.json を作成する
# - 判定・処理状態の正本は text/processing_status.json
# - pdf/pdf_status.json は登録情報のみであり、本ファイルでは更新しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import datetime as dt
import json
import shutil
from pathlib import Path

# ============================================================
# imports（pdf_catalog）
# ============================================================
from common_lib.pdf_catalog import (
    ensure_doc_layout_dirs,
    get_doc_pdf_dir,
    get_source_pdf_path,
    list_source_pdfs_by_shard,
)
from common_lib.pdf_catalog.paths import (
    get_raw_text_path,
    get_clean_text_path,
    get_raw_pages_json_path,
)
import common_lib.pdf_catalog.processing_status_ops as generic_status_ops
from common_lib.pdf_catalog.processing_status_ops import (
    upsert_pdf_info_status,
    mark_text_extracted,
    upsert_error_status,
)

# ============================================================
# imports（common_lib/pdf_tools）
# ============================================================
from common_lib.pdf_tools.text_extract.fitz_guard import try_import_fitz
from common_lib.pdf_tools.text_extract.detect import detect_pdf_kind_from_bytes
from common_lib.pdf_tools.text_extract.extract import (
    extract_text_direct,
    build_ocr_pdf_bytes,
    extract_text_from_pdf_bytes,
)
from common_lib.pdf_tools.text_extract.utils import sha256_bytes
from common_lib.pdf_tools.text_clean import (
    CleanOptions,
    clean_ocr_text,
)
from common_lib.pdf_tools.pages_json import (
    create_clean_pages_json,
)

# ============================================================
# constants（text artifacts）
# ============================================================
REPORT_RAW_TXT_NAME = "report_raw.txt"
REPORT_CLEAN_TXT_NAME = "report_clean.txt"
REPORT_CLEAN_PAGES_JSON_NAME = "report_clean_pages.json"
EXTRACT_META_JSON_NAME = "extract_meta.json"
PROCESSING_STATUS_JSON_NAME = "processing_status.json"
OCR_PDF_SUFFIX = "_ocr.pdf"


# ============================================================
# helpers（fs）
# ============================================================
def _require_existing_dir(*, dir_path: Path, name: str) -> None:
    # ------------------------------------------------------------
    # ディレクトリ存在前提ガード
    # ------------------------------------------------------------
    if not dir_path.exists():
        raise RuntimeError(f"{name} が存在しません（不整合）。 path={dir_path}")
    if not dir_path.is_dir():
        raise RuntimeError(f"{name} がディレクトリではありません（不整合）。 path={dir_path}")


def _atomic_write_bytes(dst: Path, data: bytes) -> None:
    # ------------------------------------------------------------
    # bytes atomic write
    # ------------------------------------------------------------
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dst)


def _atomic_write_text(dst: Path, text: str) -> None:
    # ------------------------------------------------------------
    # text atomic write
    # ------------------------------------------------------------
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(dst)


def _atomic_write_json(dst: Path, obj: object) -> None:
    # ------------------------------------------------------------
    # json atomic write
    # ------------------------------------------------------------
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(dst)


def _clear_dir_contents_strict(*, dir_path: Path, name: str) -> None:
    # ------------------------------------------------------------
    # 配下全削除（握らない）
    # ------------------------------------------------------------
    _require_existing_dir(dir_path=dir_path, name=name)

    for p in dir_path.iterdir():
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"{name} 配下の削除に失敗しました（事故防止のため握りません）。 "
                f"dir={dir_path} failed_entry={p}"
            ) from e


# ============================================================
# helpers（artifact paths）
# ============================================================
def _get_doc_root(
    *,
    archive_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # ------------------------------------------------------------
    # doc root
    # ------------------------------------------------------------
    pdf_dir = get_doc_pdf_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    return pdf_dir.parent


def _get_doc_ocr_dir(
    *,
    archive_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # ------------------------------------------------------------
    # ocr dir
    # ------------------------------------------------------------
    return _get_doc_root(
        archive_root=archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "ocr"


def _get_doc_text_dir(
    *,
    archive_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # ------------------------------------------------------------
    # text dir
    # ------------------------------------------------------------
    return _get_doc_root(
        archive_root=archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "text"


def _get_extract_meta_path(*, text_dir: Path) -> Path:
    # ------------------------------------------------------------
    # meta path
    # ------------------------------------------------------------
    return text_dir / EXTRACT_META_JSON_NAME


def _get_report_clean_pages_json_path(*, text_dir: Path) -> Path:
    # ------------------------------------------------------------
    # clean pages json path
    # ------------------------------------------------------------
    return text_dir / REPORT_CLEAN_PAGES_JSON_NAME


def _get_processing_status_path(*, text_dir: Path) -> Path:
    # ------------------------------------------------------------
    # processing_status path
    # ------------------------------------------------------------
    return text_dir / PROCESSING_STATUS_JSON_NAME


def _get_report_ocr_pdf_path(*, ocr_dir: Path, original_pdf_filename: str) -> Path:
    # ------------------------------------------------------------
    # OCR済みPDF path
    # ------------------------------------------------------------
    stem = Path(str(original_pdf_filename or "report.pdf")).stem
    return ocr_dir / f"{stem}{OCR_PDF_SUFFIX}"


def _join_pages_text(pages_text_list: list[str]) -> str:
    # ------------------------------------------------------------
    # ページ単位テキストを全文へ連結
    # ------------------------------------------------------------
    return "\n\n".join([str(x or "") for x in pages_text_list])


def _extract_text_from_pdf_bytes_by_page(
    *,
    fitz,
    pdf_bytes: bytes,
    page_count_total: int,
) -> list[str]:
    # ------------------------------------------------------------
    # PDF bytes からページ単位テキストを抽出
    # ------------------------------------------------------------
    pages: list[str] = []

    for page_idx in range(int(page_count_total)):
        one_page_text = extract_text_from_pdf_bytes(
            fitz=fitz,
            pdf_bytes=pdf_bytes,
            page_start_0=int(page_idx),
            page_end_0_inclusive=int(page_idx),
        )
        pages.append(str(one_page_text or ""))

    return pages


# ============================================================
# helpers（meta）
# ============================================================
def _build_extract_meta_obj(
    *,
    source_pdf_filename: str,
    source_pdf_sha256: str,
    raw_text_filename: str,
    clean_text_filename: str,
    ocr_pdf_filename: str,
    pdf_kind: str,
    page_count_total: int,
    pages_processed: int,
    used_ocr: bool,
    ocr_lang: str,
    started_at: str,
    finished_at: str,
    status: str,
    error_message: str | None,
    clean_applied: bool,
    cleaned_at: str | None,
) -> dict[str, object]:
    # ------------------------------------------------------------
    # extract_meta.json payload
    # ------------------------------------------------------------
    return {
        "source_pdf_filename": str(source_pdf_filename or ""),
        "source_pdf_sha256": str(source_pdf_sha256 or ""),
        "raw_text_filename": str(raw_text_filename or ""),
        "clean_text_filename": str(clean_text_filename or ""),
        "ocr_pdf_filename": str(ocr_pdf_filename or ""),
        "extract": {
            "pdf_kind": str(pdf_kind or ""),
            "page_count_total": int(page_count_total),
            "pages_processed": int(pages_processed),
            "used_ocr": bool(used_ocr),
            "ocr_lang": str(ocr_lang or ""),
            "started_at": str(started_at or ""),
            "finished_at": str(finished_at or ""),
            "status": str(status or ""),
            "error_message": error_message,
        },
        "cleaning": {
            "clean_applied": bool(clean_applied),
            "cleaned_at": cleaned_at,
        } if (clean_applied or cleaned_at is not None) else None,
    }


# ============================================================
# helpers（clean options）
# ============================================================
def _build_default_clean_options() -> CleanOptions:
    # ------------------------------------------------------------
    # cleaning 既定値
    # ------------------------------------------------------------
    return CleanOptions(
        remove_jp_in_sentence_spaces=True,
        drop_toc_block=True,
        toc_min_run=6,
        drop_repeated_lines=True,
        repeated_min_count=3,
        repeated_max_len=40,
        join_wrapped_lines=True,
        drop_garbage_english_lines=True,
        drop_decoration_lines=True,
        drop_tiny_noise_lines=True,
    )


# ============================================================
# helpers（status optional）
# ============================================================
def _call_optional_status_op(name: str, **kwargs) -> None:
    # ------------------------------------------------------------
    # generic processing_status_ops に実装があれば呼ぶ
    # - 現時点で mark_ocr_done / mark_cleaned の有無が未確認のため
    #   無ければ no-op とする
    # ------------------------------------------------------------
    fn = getattr(generic_status_ops, name, None)
    if callable(fn):
        fn(**kwargs)


# ============================================================
# public（OCR pipeline：1件）
# ============================================================
def run_generic_ocr_pipeline(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    pdf_filename: str,
    done_by: str,
    ocr_lang: str = "jpn+eng",
    do_clean_text: bool = True,
) -> dict[str, object]:
    # ------------------------------------------------------------
    # generic PDF 1件に対して OCR / text抽出 / clean保存 を実行する
    #
    # 出力：
    # - ocr/<stem>_ocr.pdf        （image PDF の場合）
    # - text/report_raw.txt
    # - text/report_clean.txt     （do_clean_text=True の場合）
    # - text/extract_meta.json
    # - text/processing_status.json 更新
    # ------------------------------------------------------------
    ensure_doc_layout_dirs(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    source_pdf_path = get_source_pdf_path(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    doc_pdf_dir = get_doc_pdf_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    copied_pdf_path = doc_pdf_dir / str(pdf_filename or "")

    # ------------------------------------------------------------
    # 展開済みPDFがあれば優先、無ければ原本PDF
    # ------------------------------------------------------------
    target_pdf_path = copied_pdf_path if copied_pdf_path.exists() else source_pdf_path

    if target_pdf_path is None or (not target_pdf_path.exists()):
        raise RuntimeError(
            f"対象PDFが存在しません。 collection_id={collection_id} shard_id={shard_id} doc_id={doc_id}"
        )

    pdf_bytes = target_pdf_path.read_bytes()
    pdf_sha256 = sha256_bytes(pdf_bytes)

    ocr_dir = _get_doc_ocr_dir(
        archive_root=archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    text_dir = _get_doc_text_dir(
        archive_root=archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    _require_existing_dir(dir_path=ocr_dir, name="ocr_dir")
    _require_existing_dir(dir_path=text_dir, name="text_dir")

    # ------------------------------------------------------------
    # fitz
    # ------------------------------------------------------------
    fitz_res = try_import_fitz()
    if (not fitz_res.ok) or (fitz_res.fitz is None):
        raise RuntimeError(f"PyMuPDF（fitz）が利用できません。 import error: {fitz_res.error}")
    fitz = fitz_res.fitz

    # ------------------------------------------------------------
    # PDF判定
    # ------------------------------------------------------------
    detected_kind, detected_pages = detect_pdf_kind_from_bytes(
        fitz=fitz,
        pdf_bytes=pdf_bytes,
        sample_pages=3,
        min_text_chars=40,
    )
    pdfkind = str(detected_kind or "")
    page_count_total = int(detected_pages)

    if pdfkind not in ("text", "image"):
        raise RuntimeError(f"pdf_kind 判定結果が不正です。 pdf_kind={pdfkind}")

    if page_count_total <= 0:
        raise RuntimeError(f"page_count が不正です。 page_count={page_count_total}")

    # ------------------------------------------------------------
    # processing_status.json に PDF基本情報を記録
    # ------------------------------------------------------------
    upsert_pdf_info_status(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
        source_pdf_filename=str(target_pdf_path.name),
        source_pdf_sha256=str(pdf_sha256),
        pdf_kind=str(pdfkind),
        page_count=int(page_count_total),
        done_by=str(done_by),
    )

    # ------------------------------------------------------------
    # paths
    # ------------------------------------------------------------
    raw_txt_path = get_raw_text_path(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    clean_txt_path = get_clean_text_path(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )
    clean_pages_json_path = _get_report_clean_pages_json_path(text_dir=text_dir)
    meta_path = _get_extract_meta_path(text_dir=text_dir)
    processing_status_path = _get_processing_status_path(text_dir=text_dir)

    started_at = dt.datetime.now().replace(microsecond=0).isoformat()

    try:
        # --------------------------------------------------------
        # 派生物を厳格全消し
        # - PDFそのものは消さない
        # --------------------------------------------------------
        _clear_dir_contents_strict(dir_path=ocr_dir, name="ocr_dir")
        _clear_dir_contents_strict(dir_path=text_dir, name="text_dir")

        # --------------------------------------------------------
        # PDF基本情報は text_dir 全消し後に再記録
        # --------------------------------------------------------
        upsert_pdf_info_status(
            archive_root,
            collection_id=collection_id,
            shard_id=shard_id,
            doc_id=doc_id,
            source_pdf_filename=str(target_pdf_path.name),
            source_pdf_sha256=str(pdf_sha256),
            pdf_kind=str(pdfkind),
            page_count=int(page_count_total),
            done_by=str(done_by),
        )

        # --------------------------------------------------------
        # text PDF：直接抽出
        # --------------------------------------------------------
        if pdfkind == "text":
            raw_text = extract_text_direct(
                fitz=fitz,
                pdf_bytes=pdf_bytes,
                page_start_0=0,
                page_end_0_inclusive=max(0, page_count_total - 1),
            )
            raw_page_texts: list[str] = []
            used_ocr = False
            ocr_pdf_filename = ""

        # --------------------------------------------------------
        # image PDF：OCR 実行
        # --------------------------------------------------------
        elif pdfkind == "image":
            ocr_pdf_bytes = build_ocr_pdf_bytes(
                fitz=fitz,
                pdf_bytes=pdf_bytes,
                page_start_0=0,
                page_end_0_inclusive=max(0, page_count_total - 1),
                ocr_lang=str(ocr_lang or "jpn+eng"),
                ocr_dpi=300,
            )

            ocr_pdf_path = _get_report_ocr_pdf_path(
                ocr_dir=ocr_dir,
                original_pdf_filename=str(target_pdf_path.name),
            )
            _atomic_write_bytes(ocr_pdf_path, ocr_pdf_bytes)

            raw_page_texts = _extract_text_from_pdf_bytes_by_page(
                fitz=fitz,
                pdf_bytes=ocr_pdf_bytes,
                page_count_total=int(page_count_total),
            )
            raw_text = _join_pages_text(raw_page_texts)

            used_ocr = True
            ocr_pdf_filename = str(ocr_pdf_path.name)

            _call_optional_status_op(
                "mark_ocr_done",
                archive_root=archive_root,
                collection_id=collection_id,
                shard_id=shard_id,
                doc_id=doc_id,
                done_by=str(done_by),
            )

        else:
            raise RuntimeError(f"pdf_kind が不正です。 pdf_kind={pdfkind}")

        # --------------------------------------------------------
        # raw text 保存
        # --------------------------------------------------------
        _atomic_write_text(raw_txt_path, str(raw_text or ""))

        mark_text_extracted(
            archive_root,
            collection_id=collection_id,
            shard_id=shard_id,
            doc_id=doc_id,
            done_by=str(done_by),
        )

        # --------------------------------------------------------
        # clean text 保存（任意）
        # - OCR時に clean を行う場合は、ページ単位 clean 結果から
        #   report_clean.txt / report_clean_pages.json を作る
        # --------------------------------------------------------
        clean_applied = False
        cleaned_at: str | None = None

        if bool(do_clean_text):
            clean_options = _build_default_clean_options()

            # ----------------------------------------------------
            # text PDF は本ページでは clean 対象外
            # - ただし API 呼び出しが来ても壊さないよう、
            #   clean は image PDF のみ適用
            # ----------------------------------------------------
            if pdfkind == "image":
                clean_page_texts: list[str] = []

                for raw_page_text in raw_page_texts:
                    clean_page_text, _clean_report = clean_ocr_text(
                        str(raw_page_text or ""),
                        clean_options,
                    )
                    clean_page_texts.append(str(clean_page_text or ""))

                clean_text = _join_pages_text(clean_page_texts)
                _atomic_write_text(clean_txt_path, str(clean_text or ""))

                create_clean_pages_json(
                    clean_pages_json_path,
                    collection_id=str(collection_id),
                    shard_id=str(shard_id),
                    doc_id=str(doc_id),
                    pdf_filename=str(target_pdf_path.name),
                    source_pdf_sha256=str(pdf_sha256),
                    pages_text_list=clean_page_texts,
                )

                _call_optional_status_op(
                    "mark_cleaned",
                    archive_root=archive_root,
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=doc_id,
                    done_by=str(done_by),
                )

                clean_applied = True
                cleaned_at = dt.datetime.now().replace(microsecond=0).isoformat()

        finished_at = dt.datetime.now().replace(microsecond=0).isoformat()

        # --------------------------------------------------------
        # meta 保存
        # --------------------------------------------------------
        meta_obj = _build_extract_meta_obj(
            source_pdf_filename=str(target_pdf_path.name),
            source_pdf_sha256=str(pdf_sha256),
            raw_text_filename=REPORT_RAW_TXT_NAME,
            clean_text_filename=REPORT_CLEAN_TXT_NAME if clean_applied else "",
            ocr_pdf_filename=str(ocr_pdf_filename),
            pdf_kind=str(pdfkind),
            page_count_total=int(page_count_total),
            pages_processed=int(page_count_total),
            used_ocr=bool(used_ocr),
            ocr_lang=str(ocr_lang or ""),
            started_at=str(started_at),
            finished_at=str(finished_at),
            status="ok",
            error_message=None,
            clean_applied=bool(clean_applied),
            cleaned_at=cleaned_at,
        )
        _atomic_write_json(meta_path, meta_obj)

        return {
            "status": "ok",
            "collection_id": str(collection_id),
            "shard_id": str(shard_id),
            "doc_id": str(doc_id),
            "pdf_kind": str(pdfkind),
            "page_count": int(page_count_total),
            "used_ocr": bool(used_ocr),
            "raw_text_path": str(raw_txt_path),
            "clean_text_path": str(clean_txt_path) if clean_applied else None,
            "extract_meta_path": str(meta_path),
            "ocr_pdf_filename": str(ocr_pdf_filename),
            "clean_applied": bool(clean_applied),
            "processing_status_path": str(processing_status_path),
        }

    except Exception as e:  # noqa: BLE001
        finished_at = dt.datetime.now().replace(microsecond=0).isoformat()

        meta_obj = _build_extract_meta_obj(
            source_pdf_filename=str(target_pdf_path.name),
            source_pdf_sha256=str(pdf_sha256),
            raw_text_filename=REPORT_RAW_TXT_NAME,
            clean_text_filename="",
            ocr_pdf_filename="",
            pdf_kind=str(pdfkind),
            page_count_total=int(page_count_total),
            pages_processed=int(page_count_total),
            used_ocr=bool(pdfkind == "image"),
            ocr_lang=str(ocr_lang or ""),
            started_at=str(started_at),
            finished_at=str(finished_at),
            status="error",
            error_message=str(e),
            clean_applied=False,
            cleaned_at=None,
        )
        _atomic_write_json(meta_path, meta_obj)

        upsert_error_status(
            archive_root,
            collection_id=collection_id,
            shard_id=shard_id,
            doc_id=doc_id,
            source_pdf_filename=str(target_pdf_path.name),
            source_pdf_sha256=str(pdf_sha256),
            pdf_kind=str(pdfkind),
            page_count=int(page_count_total),
            done_by=str(done_by),
            error_message=str(e),
        )
        raise


# ============================================================
# public（OCR pipeline：複数件）
# ============================================================
def run_generic_ocr_pipeline_for_selected_docs(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    selected_doc_ids: list[str],
    done_by: str,
    ocr_lang: str = "jpn+eng",
    do_clean_text: bool = True,
    force_rerun: bool = False,
) -> tuple[str, list[str]]:
    # ------------------------------------------------------------
    # generic PDF 複数件に対して OCR / text抽出 / clean保存 を実行する
    # ------------------------------------------------------------
    target_doc_ids = set(str(x) for x in (selected_doc_ids or []))

    if not target_doc_ids:
        return "OCR実行: 対象 0 件", []

    records = list_source_pdfs_by_shard(
        archive_root,
        collection_id=str(collection_id),
        shard_id=str(shard_id),
    )

    ok_count = 0
    skip_count = 0
    error_lines: list[str] = []

    for rec in records:
        try:
            if str(rec.doc_id) not in target_doc_ids:
                continue

            raw_txt_path = get_raw_text_path(
                archive_root,
                collection_id=str(collection_id),
                shard_id=str(shard_id),
                doc_id=str(rec.doc_id),
            )
            clean_txt_path = get_clean_text_path(
                archive_root,
                collection_id=str(collection_id),
                shard_id=str(shard_id),
                doc_id=str(rec.doc_id),
            )

            # ----------------------------------------------------
            # 再実行しない場合は既存成果物でスキップ
            # ----------------------------------------------------
            if not bool(force_rerun):
                if raw_txt_path.exists():
                    if (not do_clean_text) or clean_txt_path.exists():
                        skip_count += 1
                        continue

            run_generic_ocr_pipeline(
                archive_root,
                collection_id=str(collection_id),
                shard_id=str(shard_id),
                doc_id=str(rec.doc_id),
                pdf_filename=str(rec.pdf_filename),
                done_by=str(done_by),
                ocr_lang=str(ocr_lang or "jpn+eng"),
                do_clean_text=bool(do_clean_text),
            )
            ok_count += 1

        except Exception as e:
            error_lines.append(f"{rec.doc_id} | {e}")

    msg = f"OCR実行: ok {ok_count} 件 / skip {skip_count} 件 / error {len(error_lines)} 件"
    return msg, error_lines