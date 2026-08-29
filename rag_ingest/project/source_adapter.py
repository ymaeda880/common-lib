# common_lib/rag_ingest/project/source_adapter.py
# =============================================================================
# RAG ingest : project（報告書）用 source adapter
#
# 役割：
# - 報告書1件を、共通 ingest 基盤で扱える IngestSource に変換する
# - project 固有の source 解決ロジックをここに閉じ込める
#
# project 固有で扱うもの：
# - project_year / project_no
# - pdf_filename
# - pdf_kind（text / image / mixed）
# - pdf_lock_flag
# - OCR済みか
# - report_pages.json
# - project 用 collection_id / shard_id / doc_id / attrs
#
# 設計方針：
# - collection_id は "project"
# - shard_id は str(year)
# - doc_id は "<year>/<pno>/<pdf_filename>"
# - attrs に year / pno / ocr を入れる
#
# 入力元テキストの基本方針：
# - 正本は text/report_pages.json
# - text / image / mixed の区別にかかわらず pages[].text を使用する
# - image頁はOCR後に pages[].text が更新される
# - RAG側では report_pages.json から全文とページ境界を構築する
#
# 注意：
# - path は原則として Archive/project ルート相対で保持する
#   例：
#     2019/009/pdf/xxx.pdf
#     2019/009/text/report_pages.json
# - project_master.db の path はここでは扱わない
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from common_lib.project_master import read_processing_status
from common_lib.storage.external_ssd_root import resolve_storage_subdir_root_v2

from ..manifest_ops import build_doc_id, build_file_name_from_file
from ..models import IngestSource


# =============================================================================
# 定数
# =============================================================================
COLLECTION_ID = "project"

REPORT_PAGES_JSON_NAME = "report_pages.json"


# =============================================================================
# source resolve result
# =============================================================================
@dataclass(slots=True)
class ProjectSourceResolveResult:
    # -----------------------------------------------------------------------------
    # 報告書1件の source 解決結果
    #
    # ok=False の場合は skip 理由を message に入れる
    # ok=True の場合は source が入る
    # -----------------------------------------------------------------------------
    ok: bool
    message: str

    project_year: int
    project_no: str
    pdf_filename: str

    pdf_kind: str
    pdf_lock_flag: int
    ocr_done: bool

    source: Optional[IngestSource] = None

    source_pdf_path: Optional[str] = None
    source_text_path: Optional[str] = None
    source_pages_path: Optional[str] = None
    source_text_kind: Optional[str] = None
    sha256: Optional[str] = None

    def to_dict(self) -> dict:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return {
            "ok": self.ok,
            "message": self.message,
            "project_year": self.project_year,
            "project_no": self.project_no,
            "pdf_filename": self.pdf_filename,
            "pdf_kind": self.pdf_kind,
            "pdf_lock_flag": self.pdf_lock_flag,
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
def _normalize_pno(project_no: object) -> str:
    # -----------------------------------------------------------------------------
    # pno を 3桁ゼロ埋め文字列に正規化する
    # -----------------------------------------------------------------------------
    s = str(project_no or "").strip()
    if not s:
        raise ValueError("project_no が空です。")
    return s.zfill(3)


def _report_root_relative_dir(project_year: int, project_no: str) -> str:
    # -----------------------------------------------------------------------------
    # Archive/project ルート相対の案件ディレクトリ
    #
    # 例：
    #   2019/009
    # -----------------------------------------------------------------------------
    y = int(project_year)
    p = _normalize_pno(project_no)
    return f"{y}/{p}"


def _archive_project_root(projects_root: Path) -> Path:
    # -----------------------------------------------------------------------------
    # Archive/project の実体ルート
    # -----------------------------------------------------------------------------
    archive_root = resolve_storage_subdir_root_v2(
        Path(projects_root),
        subdir="Archive",
        role="main",
    )

    return Path(archive_root) / "project"

def _report_project_dir(projects_root: Path, project_year: int, project_no: str) -> Path:
    # -----------------------------------------------------------------------------
    # 実ファイルシステム上の案件ディレクトリ
    #
    # 想定：
    #   <ARCHIVE_ROOT>/project/<year>/<pno>/
    # -----------------------------------------------------------------------------
    rel = _report_root_relative_dir(project_year, project_no)

    return _archive_project_root(projects_root) / rel


def _pdf_dir(projects_root: Path, project_year: int, project_no: str) -> Path:
    # -----------------------------------------------------------------------------
    # pdf ディレクトリ
    # -----------------------------------------------------------------------------
    return _report_project_dir(projects_root, project_year, project_no) / "pdf"


def _text_dir(projects_root: Path, project_year: int, project_no: str) -> Path:
    # -----------------------------------------------------------------------------
    # text ディレクトリ
    # -----------------------------------------------------------------------------
    return _report_project_dir(projects_root, project_year, project_no) / "text"


def _relative_pdf_path(project_year: int, project_no: str, pdf_filename: str) -> str:
    # -----------------------------------------------------------------------------
    # Archive/project ルート相対の pdf path
    #
    # 例：
    #   2019/009/pdf/xxx.pdf
    # -----------------------------------------------------------------------------
    rel = _report_root_relative_dir(project_year, project_no)
    return f"{rel}/pdf/{pdf_filename}"


def _relative_report_pages_path(project_year: int, project_no: str) -> str:
    # -----------------------------------------------------------------------------
    # Archive/project ルート相対の report_pages.json path
    #
    # 例：
    #   2019/009/text/report_pages.json
    # -----------------------------------------------------------------------------
    rel = _report_root_relative_dir(project_year, project_no)
    return f"{rel}/text/{REPORT_PAGES_JSON_NAME}"


def _read_report_pages_input_text(path: Path) -> str:
    # -----------------------------------------------------------------------------
    # report_pages.json の pages[].text をPDFページ順に連結する。
    #
    # 後続のRAG処理と同じくページ間には区切り文字を追加しない。
    # 実際のchunk化・ページ境界計算は後続処理がsource_pages_pathから行う。
    # -----------------------------------------------------------------------------
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"report_pages.json 読込失敗: {path} : {e}") from e

    pages = payload.get("pages", [])
    if not isinstance(pages, list):
        raise RuntimeError("report_pages.json の pages がlistではありません。")

    page_rows = []
    for row in pages:
        if not isinstance(row, dict):
            continue

        try:
            page_no = int(row.get("page_no", 0) or 0)
        except Exception:
            page_no = 0

        if page_no <= 0:
            continue

        page_rows.append((page_no, str(row.get("text", "") or "")))

    page_rows.sort(key=lambda x: x[0])
    return "".join(text for _, text in page_rows)


def _pdf_kind_label(rec) -> str:
    # -----------------------------------------------------------------------------
    # processing_status から pdf_kind を正規化する
    # -----------------------------------------------------------------------------
    v = str(getattr(rec, "pdf_kind", "") or "").strip().lower()
    if v in ("text", "image", "mixed"):
        return v
    return ""


def _ocr_done_flag(rec) -> bool:
    # -----------------------------------------------------------------------------
    # processing_status から OCR済み判定
    # -----------------------------------------------------------------------------
    return bool(getattr(rec, "ocr_done", False))


def _sha256_from_processing_status(rec) -> str:
    # -----------------------------------------------------------------------------
    # processing_status から source pdf の sha256 を取得
    # -----------------------------------------------------------------------------
    v = str(getattr(rec, "source_pdf_sha256", "") or "").strip()
    return v


# =============================================================================
# public helpers
# =============================================================================
def build_project_doc_id(
    *,
    project_year: int,
    project_no: str,
    pdf_filename: str,
) -> str:
    # -----------------------------------------------------------------------------
    # project 用 doc_id を作る
    #
    # 形式：
    #   <year>/<pno>/<pdf_filename>
    # -----------------------------------------------------------------------------
    y = str(int(project_year))
    p = _normalize_pno(project_no)
    fn = str(pdf_filename or "").strip()
    if not fn:
        raise ValueError("pdf_filename が空です。")

    return build_doc_id(y, p, fn)


def build_project_attrs(
    *,
    project_year: int,
    project_no: str,
    ocr_done: bool,
) -> dict:
    # -----------------------------------------------------------------------------
    # project 用 attrs
    # -----------------------------------------------------------------------------
    return {
        "year": int(project_year),
        "pno": _normalize_pno(project_no),
        "ocr": "yes" if bool(ocr_done) else "no",
    }


# =============================================================================
# main
# =============================================================================
def resolve_project_report_source(
    projects_root: Path,
    *,
    project_year: int,
    project_no: str,
    pdf_filename: str,
    embed_model: str,
    pdf_lock_flag: int = 0,
) -> ProjectSourceResolveResult:
    # -----------------------------------------------------------------------------
    # 報告書1件を IngestSource に変換する
    #
    # 引数：
    # - projects_root:
    #     モノレポの root（Archive/ を含む root）
    #
    # - project_year / project_no / pdf_filename:
    #     対象報告書
    #
    # - embed_model:
    #     使用予定の embedding model
    #
    # - pdf_lock_flag:
    #     一覧 item 側が持つ lock flag（無い場合 0）
    #
    # 戻り値：
    # - ok=False:
    #     source 解決不可。message に skip理由
    #
    # - ok=True:
    #     source に IngestSource が入る
    # -----------------------------------------------------------------------------
    year = int(project_year)
    pno = _normalize_pno(project_no)
    fn = str(pdf_filename or "").strip()
    if not fn:
        raise ValueError("pdf_filename が空です。")

    rec = read_processing_status(
        projects_root,
        project_year=year,
        project_no=pno,
    )

    pdf_kind = _pdf_kind_label(rec)
    ocr_done = _ocr_done_flag(rec)
    sha256 = _sha256_from_processing_status(rec)

    if not pdf_kind:
        return ProjectSourceResolveResult(
            ok=False,
            message="pdf_kind が未判定です。先に報告書PDF判定を実行してください。",
            project_year=year,
            project_no=pno,
            pdf_filename=fn,
            pdf_kind="",
            pdf_lock_flag=int(pdf_lock_flag or 0),
            ocr_done=ocr_done,
        )

    # -------------------------------------------------------------------------
    # RAG作成はロック済みPDFのみ対象
    #
    # 未ロックのPDFは変更される可能性があるため，
    # PDF種別にかかわらずRAGのsource解決を行わない。
    # -------------------------------------------------------------------------
    if int(pdf_lock_flag or 0) != 1:
        return ProjectSourceResolveResult(
            ok=False,
            message="PDFがロック未済のため source 解決を行いません。",
            project_year=year,
            project_no=pno,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            pdf_lock_flag=int(pdf_lock_flag or 0),
            ocr_done=ocr_done,
            sha256=sha256 or None,
        )

    # -------------------------------------------------------------------------
    # report_pages.json 解決
    # -------------------------------------------------------------------------
    source_pages_relpath = _relative_report_pages_path(
        year,
        pno,
    )
    source_pages_abs = (
        _archive_project_root(Path(projects_root))
        / source_pages_relpath
    )

    if not source_pages_abs.exists():
        return ProjectSourceResolveResult(
            ok=False,
            message=f"report_pages.json が存在しません: {source_pages_relpath}",
            project_year=year,
            project_no=pno,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            pdf_lock_flag=int(pdf_lock_flag or 0),
            ocr_done=ocr_done,
            source_text_kind="other",
            source_text_path=source_pages_relpath,
            source_pages_path=source_pages_relpath,
            sha256=sha256 or None,
        )

    try:
        input_text = _read_report_pages_input_text(source_pages_abs)
    except Exception as e:
        return ProjectSourceResolveResult(
            ok=False,
            message=str(e),
            project_year=year,
            project_no=pno,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            pdf_lock_flag=int(pdf_lock_flag or 0),
            ocr_done=ocr_done,
            source_text_kind="other",
            source_text_path=source_pages_relpath,
            source_pages_path=source_pages_relpath,
            sha256=sha256 or None,
        )

    if not input_text.strip():
        return ProjectSourceResolveResult(
            ok=False,
            message=f"report_pages.json のテキストが空です: {source_pages_relpath}",
            project_year=year,
            project_no=pno,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            pdf_lock_flag=int(pdf_lock_flag or 0),
            ocr_done=ocr_done,
            source_text_kind="other",
            source_text_path=source_pages_relpath,
            source_pages_path=source_pages_relpath,
            sha256=sha256 or None,
        )

    source_text_kind = "other"
    source_text_relpath = source_pages_relpath

    source_pdf_relpath = _relative_pdf_path(year, pno, fn)
    source_pdf_abs = _archive_project_root(Path(projects_root)) / source_pdf_relpath

    if not source_pdf_abs.exists():
        return ProjectSourceResolveResult(
            ok=False,
            message=f"元PDFが存在しません: {source_pdf_relpath}",
            project_year=year,
            project_no=pno,
            pdf_filename=fn,
            pdf_kind=pdf_kind,
            pdf_lock_flag=int(pdf_lock_flag or 0),
            ocr_done=ocr_done,
            source_text_kind=source_text_kind,
            source_text_path=source_text_relpath,
            source_pages_path=source_pages_relpath,
            source_pdf_path=source_pdf_relpath,
            sha256=sha256 or None,
        )

    doc_id = build_project_doc_id(
        project_year=year,
        project_no=pno,
        pdf_filename=fn,
    )

    attrs = build_project_attrs(
        project_year=year,
        project_no=pno,
        ocr_done=ocr_done,
    )

    source = IngestSource(
        collection_id=COLLECTION_ID,
        shard_id=str(year),
        doc_id=doc_id,
        file=doc_id,
        file_name=build_file_name_from_file(doc_id),
        source_pdf_path=source_pdf_relpath,
        source_text_path=source_text_relpath,
        source_pages_path=source_pages_relpath,
        source_text_kind=source_text_kind,
        input_text=input_text,
        sha256=str(sha256 or ""),
        embed_model=str(embed_model or "").strip(),
        attrs=attrs,
    )

    return ProjectSourceResolveResult(
        ok=True,
        message="ok",
        project_year=year,
        project_no=pno,
        pdf_filename=fn,
        pdf_kind=pdf_kind,
        pdf_lock_flag=int(pdf_lock_flag or 0),
        ocr_done=ocr_done,
        source=source,
        source_pdf_path=source_pdf_relpath,
        source_text_path=source_text_relpath,
        source_pages_path=source_pages_relpath,
        source_text_kind=source_text_kind,
        sha256=str(sha256 or ""),
    )