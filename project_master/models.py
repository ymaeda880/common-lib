# common_lib/project_master/models.py
# ============================================================
# Report Master: DBモデル（projects）
# - projects テーブル行を扱うデータモデル
# - ISO文字列（date/datetime）を TEXT として保持する前提
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from dataclasses import dataclass
from typing import Any, Dict, Optional


# ============================================================
# Project（projects row）
# ============================================================
@dataclass
class Project:
    # ------------------------------------------------------------
    # 主キー
    # ------------------------------------------------------------
    project_year: int
    project_no: str  # 3桁固定（001形式）

    # ------------------------------------------------------------
    # 基本情報
    # ------------------------------------------------------------
    project_name: str
    client_name: str
    main_department: str
    contract_amount: int  # 円単位

    # ------------------------------------------------------------
    # 監査/入力情報
    # ------------------------------------------------------------
    input_user_id: str
    input_date: str          # ISO date (YYYY-MM-DD)
    update_user_id: str
    update_date: str         # ISO date (YYYY-MM-DD)

    # ------------------------------------------------------------
    # PDF確定ロック
    # ------------------------------------------------------------
    pdf_lock_flag: int                 # 0 / 1
    pdf_locked_at: Optional[str]       # ISO datetime
    pdf_locked_by: Optional[str]

    # ------------------------------------------------------------
    # 報告書PDFメタ（A案：projectsに保持）
    # - 未登録時は None（または空）を許容
    # - saved_at は ISO datetime
    # ------------------------------------------------------------
    report_pdf_original_filename: Optional[str] = None
    report_pdf_stored_filename: Optional[str] = None
    report_pdf_hash_sha256: Optional[str] = None
    report_pdf_size_bytes: Optional[int] = None
    report_pdf_saved_at: Optional[str] = None
    report_pdf_saved_by: Optional[str] = None

    # ============================================================
    # conversions
    # ============================================================
    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Project":
        # ------------------------------------------------------------
        # sqlite row(dict) -> Project
        # ------------------------------------------------------------
        return cls(
            project_year=int(row["project_year"]),
            project_no=str(row["project_no"]),

            project_name=str(row.get("project_name") or ""),
            client_name=str(row.get("client_name") or ""),
            main_department=str(row.get("main_department") or ""),
            contract_amount=int(row.get("contract_amount") or 0),

            input_user_id=str(row.get("input_user_id") or ""),
            input_date=str(row.get("input_date") or ""),
            update_user_id=str(row.get("update_user_id") or ""),
            update_date=str(row.get("update_date") or ""),

            pdf_lock_flag=int(row.get("pdf_lock_flag") or 0),
            pdf_locked_at=row.get("pdf_locked_at"),
            pdf_locked_by=row.get("pdf_locked_by"),

            report_pdf_original_filename=row.get("report_pdf_original_filename"),
            report_pdf_stored_filename=row.get("report_pdf_stored_filename"),
            report_pdf_hash_sha256=row.get("report_pdf_hash_sha256"),
            report_pdf_size_bytes=(
                int(row["report_pdf_size_bytes"])
                if row.get("report_pdf_size_bytes") is not None
                else None
            ),
            report_pdf_saved_at=row.get("report_pdf_saved_at"),
            report_pdf_saved_by=row.get("report_pdf_saved_by"),
        )

    def to_row_dict(self) -> Dict[str, Any]:
        # ------------------------------------------------------------
        # Project -> sqlite parameter dict
        # ------------------------------------------------------------
        return {
            "project_year": int(self.project_year),
            "project_no": str(self.project_no),

            "project_name": str(self.project_name),
            "client_name": str(self.client_name),
            "main_department": str(self.main_department),
            "contract_amount": int(self.contract_amount),

            "input_user_id": str(self.input_user_id),
            "input_date": str(self.input_date),
            "update_user_id": str(self.update_user_id),
            "update_date": str(self.update_date),

            "pdf_lock_flag": int(self.pdf_lock_flag),
            "pdf_locked_at": self.pdf_locked_at,
            "pdf_locked_by": self.pdf_locked_by,

            "report_pdf_original_filename": self.report_pdf_original_filename,
            "report_pdf_stored_filename": self.report_pdf_stored_filename,
            "report_pdf_hash_sha256": self.report_pdf_hash_sha256,
            "report_pdf_size_bytes": self.report_pdf_size_bytes,
            "report_pdf_saved_at": self.report_pdf_saved_at,
            "report_pdf_saved_by": self.report_pdf_saved_by,
        }