# common_lib/rag_ingest/generic/source_adapter.py
# =============================================================================
# RAG ingest : generic（汎用PDF）用 source adapter
#
# 役割：
# - 汎用PDF 1件を、共通 ingest 基盤で扱える IngestSource に変換する
# - generic 固有の source 解決ロジックをここに閉じ込める
#
# generic で扱うもの：
# - collection_id / shard_id / doc_id
# - pdf_filename
# - pdf_kind（text / image）
# - OCR済みか
# - report_raw.txt / report_clean.txt
# - report_raw_pages.json / report_clean_pages.json
# - generic 用 collection_id / shard_id / doc_id / attrs
#
# 設計方針：
# - collection_id は呼び出し側から受け取る
# - shard_id は呼び出し側から受け取る
# - doc_id は呼び出し側から受け取る
# - attrs に collection_id / shard_id / doc_id / ocr を入れる
#
# 入力元テキストの基本方針：
# - image PDF の場合：
#     report_clean.txt を使う
# - text PDF の場合：
#     clean があれば clean を使える設計
#     少なくとも clean が無ければ raw を使う
#
# page JSON の基本方針：
# - source_text_kind == "clean" の場合：
#     report_clean_pages.json を使う
# - source_text_kind == "raw" の場合：
#     report_raw_pages.json を使う
#
# 注意：
# - path は原則として PROJECTS_ROOT ルート相対で保持する
#   例：
#     Archive/<collection_id>/pdfs/<shard_id>/<doc_id>.pdf
#     Archive/<collection_id>/<shard_id>/<doc_id>/text/report_raw.txt
#     Archive/<collection_id>/<shard_id>/<doc_id>/text/report_raw_pages.json
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from common_lib.pdf_catalog import (
    get_source_pdf_path,
)
from common_lib.pdf_catalog.processing_status_ops import (
    read_processing_status,
)

from ..manifest_ops import build_doc_id, build_file_name_from_file
from ..models import IngestSource


# =============================================================================
# 定数
# =============================================================================
REPORT_RAW_TXT_NAME = "report_raw.txt"
REPORT_CLEAN_TXT_NAME = "report_clean.txt"

REPORT_RAW_PAGES_JSON_NAME = "report_raw_pages.json"
REPORT_CLEAN_PAGES_JSON_NAME = "report_clean_pages.json"


# =============================================================================
# source resolve result
# =============================================================================
@dataclass(slots=True)
class GenericSourceResolveResult:
    # -------------------------------------------------------------------------
    # 汎用PDF 1件の source 解決結果
    #
    # ok=False の場合は skip 理由を message に入れる
    # ok=True の場合は source が入る
    # -------------------------------------------------------------------------
    ok: bool
    message: str

    collection_id: str
    shard_id: str
    doc_id: str
    pdf_filename: str

    pdf_kind: str
    ocr_done: bool

    source: Optional[IngestSource] = None

    source_pdf_path: Optional[str] = None
    source_text_path: Optional[str] = None
    source_pages_path: Optional[str] = None
    source_text_kind: Optional[str] = None
    sha256: Optional[str] = None

    def to_dict(self) -> dict:
        # ---------------------------------------------------------------------
        # dict 変換
        # ---------------------------------------------------------------------
        return {
            "ok": self.ok,
            "message": self.message,
            "collection_id": self.collection_id,
            "shard_id": self.shard_id,
            "doc_id": self.doc_id,
            "pdf_filename": self.pdf_filename,
            "pdf_kind": self.pdf_kind,
            "ocr_done": self.ocr_done,
            "source_pdf_path": self.source_pdf_path,
            "source_text_path": self.source_text_path,
            "source_pages_path": self.source_pages_path,
            "source_text_kind": self.source_text_kind,
            "sha256": self.sha256,
            "source": self.source.to_dict() if self.source is not None else None,
        }


# =============================================================================
# internal helpers
# =============================================================================
def _normalize_collection_id(collection_id: object) -> str:
    # -------------------------------------------------------------------------
    # collection_id を文字列正規化
    # -------------------------------------------------------------------------
    s = str(collection_id or "").strip()
    if not s:
        raise ValueError("collection_id が空です。")
    return s


def _normalize_shard_id(shard_id: object) -> str:
    # -------------------------------------------------------------------------
    # shard_id を文字列正規化
    # -------------------------------------------------------------------------
    s = str(shard_id or "").strip()
    if not s:
        raise ValueError("shard_id が空です。")
    return s


def _normalize_doc_id(doc_id: object) -> str:
    # -------------------------------------------------------------------------
    # doc_id を文字列正規化
    # -------------------------------------------------------------------------
    s = str(doc_id or "").strip()
    if not s:
        raise ValueError("doc_id が空です。")
    return s


def _projects_root_from_archive_root(archive_root: Path) -> Path:
    # -------------------------------------------------------------------------
    # archive_root（.../Archive）から PROJECTS_ROOT を得る
    # -------------------------------------------------------------------------
    return Path(archive_root).parent


def _generic_collection_root(archive_root: Path, collection_id: str) -> Path:
    # -------------------------------------------------------------------------
    # Archive/<collection_id> ルート
    # -------------------------------------------------------------------------
    return Path(archive_root) / str(collection_id)


def _generic_doc_root(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # 実ファイルシステム上の doc ルート
    #
    # 想定：
    #   <archive_root>/<collection_id>/<shard_id>/<doc_id>/
    # -------------------------------------------------------------------------
    return _generic_collection_root(archive_root, collection_id) / str(shard_id) / str(doc_id)


def _text_dir(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> Path:
    # -------------------------------------------------------------------------
    # text ディレクトリ
    # -------------------------------------------------------------------------
    return _generic_doc_root(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    ) / "text"


def _relative_pdf_path(
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
) -> str:
    # -------------------------------------------------------------------------
    # PROJECTS_ROOT ルート相対の pdf path
    #
    # 例：
    #   Archive/boj_minutes/pdfs/2000/boj_minutes_2000-01-22_23.pdf
    # -------------------------------------------------------------------------
    return f"Archive/{str(collection_id)}/pdfs/{str(shard_id)}/{str(doc_id)}.pdf"


def _relative_text_path(
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    txt_name: str,
) -> str:
    # -------------------------------------------------------------------------
    # PROJECTS_ROOT ルート相対の text path
    #
    # 例：
    #   Archive/boj_minutes/2000/boj_minutes_2000-01-22_23/text/report_raw.txt
    # -------------------------------------------------------------------------
    return f"Archive/{str(collection_id)}/{str(shard_id)}/{str(doc_id)}/text/{txt_name}"


def _relative_pages_path(
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    json_name: str,
) -> str:
    # -------------------------------------------------------------------------
    # PROJECTS_ROOT ルート相対の pages json path
    #
    # 例：
    #   Archive/boj_minutes/2000/boj_minutes_2000-01-22_23/text/report_raw_pages.json
    # -------------------------------------------------------------------------
    return f"Archive/{str(collection_id)}/{str(shard_id)}/{str(doc_id)}/text/{json_name}"


def _read_text_file(path: Path) -> str:
    # -------------------------------------------------------------------------
    # UTF-8 前提で txt を読む
    # -------------------------------------------------------------------------
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"テキスト読込失敗: {path} : {e}") from e


def _pdf_kind_label(rec) -> str:
    # -------------------------------------------------------------------------
    # processing_status から pdf_kind を正規化する
    # -------------------------------------------------------------------------
    v = str(getattr(rec, "pdf_kind", "") or "").strip().lower()
    if v in ("text", "image"):
        return v
    return ""


def _ocr_done_flag(rec) -> bool:
    # -------------------------------------------------------------------------
    # processing_status から OCR済み判定
    # -------------------------------------------------------------------------
    return bool(getattr(rec, "ocr_done", False))


def _sha256_from_processing_status(rec) -> str:
    # -------------------------------------------------------------------------
    # processing_status から source pdf の sha256 を取得
    # -------------------------------------------------------------------------
    v = str(getattr(rec, "source_pdf_sha256", "") or "").strip()
    return v


def _choose_text_source_for_generic(
    *,
    archive_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    pdf_kind: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    # -------------------------------------------------------------------------
    # generic の入力元テキストを決める
    #
    # 戻り値：
    #   (source_text_kind, source_text_relpath, message)
    #
    # 正常時：
    #   ("raw" or "clean", "Archive/<collection_id>/<shard_id>/<doc_id>/text/....txt", None)
    #
    # 異常時：
    #   (None, None, "理由")
    #
    # ルール：
    # - image PDF -> report_clean.txt 必須
    # - text PDF  -> clean があれば clean を使う
    #                なければ raw
    # -------------------------------------------------------------------------
    text_dir = _text_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    clean_path = text_dir / REPORT_CLEAN_TXT_NAME
    raw_path = text_dir / REPORT_RAW_TXT_NAME

    clean_exists = clean_path.exists()
    raw_exists = raw_path.exists()

    if pdf_kind == "image":
        if clean_exists:
            return (
                "clean",
                _relative_text_path(
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=doc_id,
                    txt_name=REPORT_CLEAN_TXT_NAME,
                ),
                None,
            )
        return (None, None, "image PDF ですが report_clean.txt が存在しません。")

    if pdf_kind == "text":
        if clean_exists:
            return (
                "clean",
                _relative_text_path(
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=doc_id,
                    txt_name=REPORT_CLEAN_TXT_NAME,
                ),
                None,
            )
        if raw_exists:
            return (
                "raw",
                _relative_text_path(
                    collection_id=collection_id,
                    shard_id=shard_id,
                    doc_id=doc_id,
                    txt_name=REPORT_RAW_TXT_NAME,
                ),
                None,
            )
        return (None, None, "text PDF ですが report_raw.txt / report_clean.txt が存在しません。")

    return (None, None, "pdf_kind が未判定です。")


def _choose_pages_source_for_generic(
    *,
    archive_root: Path,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    source_text_kind: str,
) -> tuple[Optional[str], Optional[str]]:
    # -------------------------------------------------------------------------
    # source_text_kind に対応する pages json を決める
    #
    # 戻り値：
    #   (source_pages_relpath, message)
    # -------------------------------------------------------------------------
    text_dir = _text_dir(
        archive_root,
        collection_id=collection_id,
        shard_id=shard_id,
        doc_id=doc_id,
    )

    kind = str(source_text_kind or "").strip().lower()

    if kind == "clean":
        rel = _relative_pages_path(
            collection_id=collection_id,
            shard_id=shard_id,
            doc_id=doc_id,
            json_name=REPORT_CLEAN_PAGES_JSON_NAME,
        )
        abs_path = text_dir / REPORT_CLEAN_PAGES_JSON_NAME
        if abs_path.exists():
            return (rel, None)
        return (None, "source_text_kind=clean ですが report_clean_pages.json が存在しません。")

    if kind == "raw":
        rel = _relative_pages_path(
            collection_id=collection_id,
            shard_id=shard_id,
            doc_id=doc_id,
            json_name=REPORT_RAW_PAGES_JSON_NAME,
        )
        abs_path = text_dir / REPORT_RAW_PAGES_JSON_NAME
        if abs_path.exists():
            return (rel, None)
        return (None, "source_text_kind=raw ですが report_raw_pages.json が存在しません。")

    return (None, f"未対応の source_text_kind です: {source_text_kind}")


# =============================================================================
# public helpers
# =============================================================================
def build_generic_doc_id(
    *,
    shard_id: str,
    doc_id: str,
    pdf_filename: str,
) -> str:
    # -------------------------------------------------------------------------
    # generic 用 doc_id を作る
    #
    # 形式：
    #   <shard_id>/<doc_id>/<pdf_filename>
    # -------------------------------------------------------------------------
    s = _normalize_shard_id(shard_id)
    d = _normalize_doc_id(doc_id)
    fn = str(pdf_filename or "").strip()
    if not fn:
        raise ValueError("pdf_filename が空です。")

    return build_doc_id(s, d, fn)


def build_generic_attrs(
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    ocr_done: bool,
) -> dict:
    # -------------------------------------------------------------------------
    # generic 用 attrs
    # -------------------------------------------------------------------------
    return {
        "collection_id": _normalize_collection_id(collection_id),
        "shard_id": _normalize_shard_id(shard_id),
        "doc_id": _normalize_doc_id(doc_id),
        "ocr": "yes" if bool(ocr_done) else "no",
    }


# =============================================================================
# main
# =============================================================================
def resolve_generic_pdf_source(
    archive_root: Path,
    *,
    collection_id: str,
    shard_id: str,
    doc_id: str,
    pdf_filename: str,
    embed_model: str,
) -> GenericSourceResolveResult:
    # -------------------------------------------------------------------------
    # 汎用PDF 1件を IngestSource に変換する
    #
    # 引数：
    # - archive_root:
    #     <PROJECTS_ROOT>/Archive
    #
    # - collection_id / shard_id / doc_id / pdf_filename:
    #     対象PDF
    #
    # - embed_model:
    #     使用予定の embedding model
    #
    # 戻り値：
    # - ok=False:
    #     source 解決不可。message に skip理由
    #
    # - ok=True:
    #     source に IngestSource が入る
    # -------------------------------------------------------------------------
    c = _normalize_collection_id(collection_id)
    s = _normalize_shard_id(shard_id)
    d = _normalize_doc_id(doc_id)
    fn = str(pdf_filename or "").strip()
    if not fn:
        raise ValueError("pdf_filename が空です。")

    projects_root = _projects_root_from_archive_root(Path(archive_root))

    rec = read_processing_status(
        archive_root,
        collection_id=c,
        shard_id=s,
        doc_id=d,
    )

    pdf_kind = _pdf_kind_label(rec)
    ocr_done = _ocr_done_flag(rec)
    sha256 = _sha256_from_processing_status(rec)

    if not pdf_kind:
        return GenericSourceResolveResult(
            ok=False,
            message="pdf_kind が未判定です。先に汎用OCRを実行してください。",
            collection_id=c,
            shard_id=s,
            doc_id=d,
            pdf_filename=fn,
            pdf_kind="",
            ocr_done=ocr_done,
        )

    # -------------------------------------------------------------------------
    # source text 解決
    # -------------------------------------------------------------------------
    source_text_kind, source_text_relpath, msg = _choose_text_source_for_generic(
        archive_root=Path(archive_root),
        collection_id=c,
        shard_id=s,
        doc_id=d,
        pdf_kind=pdf_kind,
    )

    if not source_text_kind or not source_text_relpath:
        return GenericSourceResolveResult(
            ok=False,
            message=str(msg or "入力元テキストを解決できませんでした。"),
            collection_id=c,
            shard_id=s,
            doc_id=d,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            ocr_done=ocr_done,
            sha256=sha256 or None,
        )

    source_text_abs = projects_root / source_text_relpath
    if not source_text_abs.exists():
        return GenericSourceResolveResult(
            ok=False,
            message=f"入力元テキストが存在しません: {source_text_relpath}",
            collection_id=c,
            shard_id=s,
            doc_id=d,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            ocr_done=ocr_done,
            source_text_kind=source_text_kind,
            source_text_path=source_text_relpath,
            sha256=sha256 or None,
        )

    input_text = _read_text_file(source_text_abs)
    if not str(input_text).strip():
        return GenericSourceResolveResult(
            ok=False,
            message=f"入力元テキストが空です: {source_text_relpath}",
            collection_id=c,
            shard_id=s,
            doc_id=d,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            ocr_done=ocr_done,
            source_text_kind=source_text_kind,
            source_text_path=source_text_relpath,
            sha256=sha256 or None,
        )

    # -------------------------------------------------------------------------
    # source pages 解決
    # -------------------------------------------------------------------------
    source_pages_relpath, pages_msg = _choose_pages_source_for_generic(
        archive_root=Path(archive_root),
        collection_id=c,
        shard_id=s,
        doc_id=d,
        source_text_kind=str(source_text_kind),
    )

    if not source_pages_relpath:
        return GenericSourceResolveResult(
            ok=False,
            message=str(pages_msg or "pages json を解決できませんでした。"),
            collection_id=c,
            shard_id=s,
            doc_id=d,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            ocr_done=ocr_done,
            source_text_kind=source_text_kind,
            source_text_path=source_text_relpath,
            sha256=sha256 or None,
        )

    source_pages_abs = projects_root / source_pages_relpath
    if not source_pages_abs.exists():
        return GenericSourceResolveResult(
            ok=False,
            message=f"pages json が存在しません: {source_pages_relpath}",
            collection_id=c,
            shard_id=s,
            doc_id=d,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            ocr_done=ocr_done,
            source_text_kind=source_text_kind,
            source_text_path=source_text_relpath,
            source_pages_path=source_pages_relpath,
            sha256=sha256 or None,
        )

    source_pdf_abs = get_source_pdf_path(
        Path(archive_root),
        collection_id=c,
        shard_id=s,
        doc_id=d,
    )
    source_pdf_relpath = _relative_pdf_path(
        collection_id=c,
        shard_id=s,
        doc_id=d,
    )

    if not source_pdf_abs.exists():
        return GenericSourceResolveResult(
            ok=False,
            message=f"元PDFが存在しません: {source_pdf_relpath}",
            collection_id=c,
            shard_id=s,
            doc_id=d,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            ocr_done=ocr_done,
            source_text_kind=source_text_kind,
            source_text_path=source_text_relpath,
            source_pages_path=source_pages_relpath,
            source_pdf_path=source_pdf_relpath,
            sha256=sha256 or None,
        )

    final_doc_id = build_generic_doc_id(
        shard_id=s,
        doc_id=d,
        pdf_filename=fn,
    )

    attrs = build_generic_attrs(
        collection_id=c,
        shard_id=s,
        doc_id=d,
        ocr_done=ocr_done,
    )

    source = IngestSource(
        collection_id=c,
        shard_id=s,
        doc_id=final_doc_id,
        file=final_doc_id,
        file_name=build_file_name_from_file(final_doc_id),
        source_pdf_path=source_pdf_relpath,
        source_text_path=source_text_relpath,
        source_pages_path=source_pages_relpath,
        source_text_kind=source_text_kind,
        input_text=input_text,
        sha256=str(sha256 or ""),
        embed_model=str(embed_model or "").strip(),
        attrs=attrs,
    )

    return GenericSourceResolveResult(
        ok=True,
        message="ok",
        collection_id=c,
        shard_id=s,
        doc_id=d,
        pdf_filename=fn,
        pdf_kind=pdf_kind,
        ocr_done=ocr_done,
        source=source,
        source_pdf_path=source_pdf_relpath,
        source_text_path=source_text_relpath,
        source_pages_path=source_pages_relpath,
        source_text_kind=source_text_kind,
        sha256=str(sha256 or ""),
    )