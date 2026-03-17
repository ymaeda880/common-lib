# common_lib/pdf_tools/pages_json/__init__.py
# ============================================================
# pages_json パッケージ公開API
#
# 目的：
# - report_raw_pages.json / report_clean_pages.json の
#   正本APIを re-export する
# ============================================================

from __future__ import annotations

# ============================================================
# schema
# ============================================================
from .schema import (
    PageTextRecord,
    ReportPagesJson,
)

# ============================================================
# ops
# ============================================================
from .pages_json_ops import (
    PAGES_JSON_VERSION,
    RAW_PAGES_FILENAME,
    CLEAN_PAGES_FILENAME,
    KIND_RAW,
    KIND_CLEAN,
    get_report_raw_pages_json_path,
    get_report_clean_pages_json_path,
    exists_report_raw_pages_json,
    exists_report_clean_pages_json,
    write_pages_json,
    create_raw_pages_json,
    create_clean_pages_json,
    read_pages_json,
    read_report_raw_pages_json,
    read_report_clean_pages_json,
    resolve_report_pages_json_path,
    resolve_report_pages_json,
)