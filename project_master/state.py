# common_lib/project_master/state.py
# ============================================================
# Project Master: UI状態判定（S0〜S4）
# - projects 行と current_sub から状態/編集可否/理由を返す
# - 本モジュールは「UI編集可否の正本ロジック」を担う
# ============================================================

# ============================================================
# UI状態定義（S0〜S4）
# ------------------------------------------------------------
# ※ 重要：本システムは「登録者以外も編集可能」。
#    よって、登録者/非登録者で編集可否を分けない（旧S2は廃止）。
#
# S0_NOT_REGISTERED
#   - projects テーブルに該当行が存在しない
#   - 新規登録可能（Insert）
#
# S1_REGISTERED
#   - projects 行が存在
#   - 既存行の更新が可能（Update）
#   - ただし主キー（project_year, project_no）は常に変更不可
#
# S3_PDF_LOCKED
#   - pdf_lock_flag == 1
#   - 「PDFのみ」変更不可（pdf配下の入替/更新/削除等を禁止）
#   - それ以外（プロジェクト情報・others・contract・text）は変更可能
#
# S4_RAG_INGESTED
#   - text/processing_status.json において rag_status == "ingested"
#   - text系成果物（OCR / text抽出 / cleaning / raw/clean txt 等）は変更不可
#   - projects 自体の基本情報更新は禁止しない
#
# 判定優先順位：
#   1. 行なし                    -> S0
#   2. pdf_lock_flag=1           -> S3（PDFだけロック）
#   3. rag_status == "ingested"  -> S4（textだけロック）
#   4. それ以外                  -> S1
#
# 設計思想：
#   - 編集可否は「フォーム全体」ではなく「対象別」に返す
#     (1) 主キー（year/no）は常に変更不可
#     (2) PDFは pdf_lock_flag により変更可否を制御
#     (3) text は processing_status.json の rag_status により変更可否を制御
#     (4) projects の基本情報は RAG取り込み済みでも編集禁止にしない
#
# processing_status の扱い：
#   - 本モジュールは processing_status.json 自体は読まない
#   - 呼び出し元で processing_status.json を読み取り、
#       rag_status / rag_ingested_at / rag_ingested_by
#     を取得して本関数に渡す
#   - rag_status が None の場合は
#     「processing_status.json 不在 または 未取り込み」として扱う
# ============================================================


from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from dataclasses import dataclass
from typing import Optional

# ============================================================
# imports（common_lib/project_master）
# ============================================================
from common_lib.project_master.models import Project


# ============================================================
# constants（state codes）
# ============================================================
STATE_S0_NOT_REGISTERED = "S0_NOT_REGISTERED"
STATE_S1_REGISTERED = "S1_REGISTERED"
STATE_S3_PDF_LOCKED = "S3_PDF_LOCKED"
STATE_S4_RAG_INGESTED = "S4_RAG_INGESTED"


# ============================================================
# result model
# ============================================================
@dataclass(frozen=True)
class StateResult:
    # ------------------------------------------------------------
    # UI状態コード
    # ------------------------------------------------------------
    state: str

    # ------------------------------------------------------------
    # Insert/Update の可否（行単位）
    # ------------------------------------------------------------
    can_insert: bool
    can_update: bool

    # ------------------------------------------------------------
    # 項目別の編集可否（UI制御用）
    # ------------------------------------------------------------
    can_edit_keys: bool        # project_year / project_no（常に False）
    can_edit_fields: bool      # project_name / client_name / main_department / contract_amount 等
    can_edit_pdf: bool         # PDFの入替/更新/削除（pdf_lock_flag で制御）
    can_edit_text: bool        # OCR / text抽出 / cleaning / raw/clean txt 更新（rag_status で制御）

    # ------------------------------------------------------------
    # 表示理由（UIメッセージ）
    # ------------------------------------------------------------
    reason: str


# ============================================================
# helpers
# ============================================================
def _normalize_rag_status(value: Optional[str]) -> Optional[str]:
    # ------------------------------------------------------------
    # rag_status を正規化
    # - None / 空文字は None
    # - 小文字・前後空白除去
    # ------------------------------------------------------------
    if value is None:
        return None

    s = str(value).strip().lower()
    if not s:
        return None
    return s


# ============================================================
# core
# ============================================================
def calc_state(
    project: Optional[Project],
    *,
    current_sub: str,
    rag_status: Optional[str] = None,
    rag_ingested_at: Optional[str] = None,
    rag_ingested_by: Optional[str] = None,
) -> StateResult:
    # ------------------------------------------------------------
    # 重要：
    # - current_sub は将来監査表示等で使う可能性はあるが、
    #   編集可否の分岐には使わない（登録者以外も編集可能のため）。
    # - rag_status は呼び出し元で rag_status.json を読んで渡す。
    # - rag_status が None の場合は「rag_status.json 不在（未取り込み）」扱い。
    # ------------------------------------------------------------
    _ = current_sub  # 現時点では未使用（将来拡張用）

    if project is None:
        return StateResult(
            state=STATE_S0_NOT_REGISTERED,
            can_insert=True,
            can_update=False,
            can_edit_keys=False,
            can_edit_fields=True,
            can_edit_pdf=True,
            can_edit_text=True,
            reason="未登録（新規登録可）",
        )

    pdf_locked = int(project.pdf_lock_flag or 0) == 1
    rag_status_norm = _normalize_rag_status(rag_status)
    rag_ingested = rag_status_norm == "ingested"

    # ------------------------------------------------------------
    # PDFロック：PDFのみ変更不可
    # ------------------------------------------------------------
    if pdf_locked:
        by = (project.pdf_locked_by or "").strip()
        at = (project.pdf_locked_at or "").strip()
        extra = ""
        if by or at:
            extra = f"（locked_by={by or 'N/A'}, locked_at={at or 'N/A'}）"

        return StateResult(
            state=STATE_S3_PDF_LOCKED,
            can_insert=False,
            can_update=True,
            can_edit_keys=False,
            can_edit_fields=True,
            can_edit_pdf=False,
            can_edit_text=True,
            reason=f"PDF確定ロック済み（PDFのみ変更不可）{extra}",
        )

    # ------------------------------------------------------------
    # RAG取り込み済み：textのみ変更不可
    # ------------------------------------------------------------
    if rag_ingested:
        by = (rag_ingested_by or "").strip()
        at = (rag_ingested_at or "").strip()
        extra = ""
        if by or at:
            extra = f"（ingested_by={by or 'N/A'}, ingested_at={at or 'N/A'}）"

        return StateResult(
            state=STATE_S4_RAG_INGESTED,
            can_insert=False,
            can_update=True,
            can_edit_keys=False,
            can_edit_fields=True,
            can_edit_pdf=True,
            can_edit_text=False,
            reason=f"RAG取り込み済み（text変更不可）{extra}",
        )

    # ------------------------------------------------------------
    # 通常：登録済み（編集可）
    # - rag_status が None / not_ingested / failed / 不正値でも
    #   「RAG取り込み済み」ではないため通常状態とする
    # ------------------------------------------------------------
    return StateResult(
        state=STATE_S1_REGISTERED,
        can_insert=False,
        can_update=True,
        can_edit_keys=False,
        can_edit_fields=True,
        can_edit_pdf=True,
        can_edit_text=True,
        reason="登録済み（編集可）",
    )