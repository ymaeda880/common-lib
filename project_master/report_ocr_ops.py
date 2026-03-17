# -*- coding: utf-8 -*-
# common_lib/project_master/report_ocr_ops.py
# ============================================================
# Project Master: 報告書 OCR / text / clean オペレーション（正本API）
#
# 役割：
# - 報告書PDFに対する OCR 実行
# - OCR済みPDFの保存
# - raw text / clean text / extract_meta.json の保存
# - clean後ページテキストの report_clean_pages.json 保存
# - text/processing_status.json の更新
#
# 設計方針：
# - PDF本体の保存 / 削除 / ロックは report_pdf_ops.py 側に残す
# - 本ファイルは派生物（ocr / text / meta / pages_json）だけを扱う
# - path解決は common_lib.project_master.paths を正本として使う
# - OCR / text抽出のエンジン本体は common_lib.pdf_tools.text_extract.extract を使う
# - OCR時に clean を行う場合は、clean後ページ単位テキストから
#   report_clean_pages.json を作成する
# - 判定・処理状態の正本は text/processing_status.json
# - pdf/pdf_status.json は登録情報のみであり、本ファイルでは更新しない

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import datetime as dt
import json
import shutil
from pathlib import Path

# ============================================================
# imports（common_lib/project_master）
# ============================================================
from common_lib.project_master.projects_repo import get_project
from common_lib.project_master.paths import (
    normalize_year_4digits,
    normalize_pno_3digits,
    get_project_ocr_dir,
    get_project_text_dir,
)
from common_lib.project_master.report_pdf_ops import get_report_pdf_path
from common_lib.project_master.processing_status_ops import (
    read_processing_status,
    upsert_pdf_info_status,
    mark_ocr_done,
    mark_text_extracted,
    mark_cleaned,
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
    decode_text_bytes,
)

from common_lib.pdf_tools.pages_json import (
    create_clean_pages_json,
)

# ============================================================
# constants（text artifacts）
# ============================================================
REPORT_RAW_TXT_NAME = "report_raw.txt"
REPORT_CLEAN_TXT_NAME = "report_clean.txt"
EXTRACT_META_JSON_NAME = "extract_meta.json"
OCR_PDF_SUFFIX = "_ocr.pdf"


# ============================================================
# helpers（project / lock）
# ============================================================
def _require_project(projects_root: Path, *, year: int, pno3: str, role: str):
    # ------------------------------------------------------------
    # projects テーブル上の対象プロジェクト存在確認
    # ------------------------------------------------------------
    p = get_project(projects_root, project_year=year, project_no=pno3, role=role)
    if p is None:
        raise RuntimeError(
            "projects に対象プロジェクトが未登録です（先にプロジェクトを作成してください）。"
        )
    return p


def _is_locked(project) -> bool:
    # ------------------------------------------------------------
    # PDFロック状態
    # ------------------------------------------------------------
    return int(project.pdf_lock_flag or 0) == 1


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


def _read_json_dict(path: Path) -> dict:
    # ------------------------------------------------------------
    # json dict 読み込み
    # - 無ければ {}
    # - 壊れていても {} に倒す（meta再生成用）
    # ------------------------------------------------------------
    if not path.exists():
        return {}

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return obj
        return {}
    except Exception:
        return {}


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
def _get_report_raw_txt_path(*, text_dir: Path) -> Path:
    # ------------------------------------------------------------
    # raw txt path
    # ------------------------------------------------------------
    return text_dir / REPORT_RAW_TXT_NAME


def _get_report_clean_txt_path(*, text_dir: Path) -> Path:
    # ------------------------------------------------------------
    # clean txt path
    # ------------------------------------------------------------
    return text_dir / REPORT_CLEAN_TXT_NAME


def _get_extract_meta_path(*, text_dir: Path) -> Path:
    # ------------------------------------------------------------
    # meta path
    # ------------------------------------------------------------
    return text_dir / EXTRACT_META_JSON_NAME


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
# public（OCR pipeline）
# ============================================================
def run_report_ocr_pipeline(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
    ocr_lang: str = "jpn+eng",
    do_clean_text: bool = True,
    role: str = "main",
) -> dict[str, object]:
    # ------------------------------------------------------------
    # 報告書1件に対して OCR / text抽出 / clean保存 を実行する
    #
    # 出力：
    # - ocr/<stem>_ocr.pdf        （image PDF の場合）
    # - text/report_raw.txt
    # - text/report_clean.txt     （do_clean_text=True の場合）
    # - text/extract_meta.json
    # - text/processing_status.json 更新
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    # ------------------------------------------------------------
    # project / PDF存在確認
    # ------------------------------------------------------------
    project = _require_project(projects_root, year=y, pno3=pno3, role=role)

    pdf_path = get_report_pdf_path(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    if pdf_path is None or (not pdf_path.exists()):
        raise RuntimeError(f"報告書PDFが存在しません。 year={y} pno={pno3}")

    pdf_bytes = pdf_path.read_bytes()
    pdf_sha256 = sha256_bytes(pdf_bytes)

    # ------------------------------------------------------------
    # dirs
    # ------------------------------------------------------------
    ocr_dir = get_project_ocr_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    text_dir = get_project_text_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
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
        projects_root,
        project_year=y,
        project_no=pno3,
        source_pdf_filename=str(pdf_path.name),
        source_pdf_sha256=str(pdf_sha256),
        pdf_kind=str(pdfkind),
        page_count=int(page_count_total),
        done_by=str(done_by),
    )

    # ------------------------------------------------------------
    # paths
    # ------------------------------------------------------------
    raw_txt_path = _get_report_raw_txt_path(text_dir=text_dir)
    clean_txt_path = _get_report_clean_txt_path(text_dir=text_dir)
    meta_path = _get_extract_meta_path(text_dir=text_dir)

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
            projects_root,
            project_year=y,
            project_no=pno3,
            source_pdf_filename=str(pdf_path.name),
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
        # image PDF：ロック済みのみ OCR 実行
        # --------------------------------------------------------   
        elif pdfkind == "image":
            if not _is_locked(project):
                raise RuntimeError("画像PDFですがロック未済のため OCR 実行できません。")

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
                original_pdf_filename=str(pdf_path.name),
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

            mark_ocr_done(
                projects_root,
                project_year=y,
                project_no=pno3,
                done_by=str(done_by),
            )

        else:
            raise RuntimeError(f"pdf_kind が不正です。 pdf_kind={pdfkind}")

        # --------------------------------------------------------
        # raw text 保存
        # --------------------------------------------------------
        _atomic_write_text(raw_txt_path, str(raw_text or ""))

        mark_text_extracted(
            projects_root,
            project_year=y,
            project_no=pno3,
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
                    projects_root,
                    project_year=int(y),
                    project_no=str(pno3),
                    pdf_filename=str(pdf_path.name),
                    source_pdf_sha256=str(pdf_sha256),
                    pages_text_list=clean_page_texts,
                    role=role,
                )

                mark_cleaned(
                    projects_root,
                    project_year=y,
                    project_no=pno3,
                    done_by=str(done_by),
                )

                clean_applied = True
                cleaned_at = dt.datetime.now().replace(microsecond=0).isoformat()

        finished_at = dt.datetime.now().replace(microsecond=0).isoformat()

        # --------------------------------------------------------
        # meta 保存
        # --------------------------------------------------------
        meta_obj = _build_extract_meta_obj(
            source_pdf_filename=str(pdf_path.name),
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

        rec = read_processing_status(
            projects_root,
            project_year=y,
            project_no=pno3,
        )

        return {
            "status": "ok",
            "project_year": int(y),
            "project_no": str(pno3),
            "pdf_kind": str(pdfkind),
            "page_count": int(page_count_total),
            "used_ocr": bool(used_ocr),
            "raw_text_path": str(raw_txt_path),
            "clean_text_path": str(clean_txt_path) if clean_applied else None,
            "extract_meta_path": str(meta_path),
            "ocr_pdf_filename": str(ocr_pdf_filename),
            "clean_applied": bool(clean_applied),
            "processing_status_path": str(rec.path),
        }

    except Exception as e:  # noqa: BLE001
        finished_at = dt.datetime.now().replace(microsecond=0).isoformat()

        meta_obj = _build_extract_meta_obj(
            source_pdf_filename=str(pdf_path.name),
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
        raise


# ============================================================
# public（clean only）
# ============================================================
def run_report_clean_only(
    projects_root: Path,
    *,
    project_year: int | str,
    project_no: int | str,
    done_by: str,
    role: str = "main",
) -> dict[str, object]:
    # ------------------------------------------------------------
    # raw text から clean text のみ再生成する
    # - processing_status.json の cleaned 系も更新する
    # ------------------------------------------------------------
    y = normalize_year_4digits(project_year)
    pno3 = normalize_pno_3digits(project_no)

    text_dir = get_project_text_dir(
        projects_root,
        project_year=y,
        project_no=pno3,
        role=role,
    )
    _require_existing_dir(dir_path=text_dir, name="text_dir")

    raw_txt_path = _get_report_raw_txt_path(text_dir=text_dir)
    clean_txt_path = _get_report_clean_txt_path(text_dir=text_dir)
    meta_path = _get_extract_meta_path(text_dir=text_dir)

    if not raw_txt_path.exists():
        raise RuntimeError(f"{REPORT_RAW_TXT_NAME} が存在しません。 path={raw_txt_path}")

    raw_text = decode_text_bytes(raw_txt_path.read_bytes())

    clean_options = _build_default_clean_options()
    clean_text, _clean_report = clean_ocr_text(raw_text, clean_options)
    _atomic_write_text(clean_txt_path, str(clean_text or ""))

    mark_cleaned(
        projects_root,
        project_year=y,
        project_no=pno3,
        done_by=str(done_by),
    )

    meta_obj = _read_json_dict(meta_path)
    if not isinstance(meta_obj, dict):
        meta_obj = {}

    meta_obj["cleaning"] = {
        "clean_applied": True,
        "cleaned_at": dt.datetime.now().replace(microsecond=0).isoformat(),
    }
    meta_obj["clean_text_filename"] = REPORT_CLEAN_TXT_NAME
    _atomic_write_json(meta_path, meta_obj)

    rec = read_processing_status(
        projects_root,
        project_year=y,
        project_no=pno3,
    )

    return {
        "status": "ok",
        "project_year": int(y),
        "project_no": str(pno3),
        "raw_text_path": str(raw_txt_path),
        "clean_text_path": str(clean_txt_path),
        "extract_meta_path": str(meta_path),
        "processing_status_path": str(rec.path),
    }