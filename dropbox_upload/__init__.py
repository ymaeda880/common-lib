# -*- coding: utf-8 -*-
# common_lib/dropbox_upload/__init__.py
# ============================================================
# Dropbox保存 共通API
#
# 機能：
# - Dropbox保存先パス生成機能を公開する
# - Dropbox接続・アップロード機能を公開する
# ============================================================

from __future__ import annotations

# ============================================================
# paths
# ============================================================
from .paths import (
    DROPBOX_ROOT_DIR,
    PROJECT_NO_MAX,
    PROJECT_NO_MIN,
    PROJECT_YEAR_MAX,
    PROJECT_YEAR_MIN,
    build_other_file_path,
    build_others_folder_path,
    build_pdf_folder_path,
    build_project_folder_path,
    build_project_id,
    build_report_pdf_filename,
    build_report_pdf_path,
    normalize_dropbox_filename,
    normalize_project_no,
    normalize_project_year,
)

# ============================================================
# service
# ============================================================
from .service import (
    SIMPLE_UPLOAD_LIMIT_BYTES,
    UPLOAD_SESSION_CHUNK_SIZE,
    DropboxConfigurationError,
    DropboxFileAlreadyExistsError,
    DropboxUploadError,
    DropboxUploadResult,
    check_dropbox_connection,
    create_dropbox_client,
    dropbox_file_exists,
    dropbox_folder_exists,
    dropbox_path_exists,
    ensure_dropbox_folder,
    get_dropbox_metadata,
    upload_bytes_to_dropbox,
)


# ============================================================
# public API
# ============================================================
__all__ = [
    # --------------------------------------------------------
    # constants
    # --------------------------------------------------------
    "DROPBOX_ROOT_DIR",
    "PROJECT_YEAR_MIN",
    "PROJECT_YEAR_MAX",
    "PROJECT_NO_MIN",
    "PROJECT_NO_MAX",
    "SIMPLE_UPLOAD_LIMIT_BYTES",
    "UPLOAD_SESSION_CHUNK_SIZE",

    # --------------------------------------------------------
    # exceptions
    # --------------------------------------------------------
    "DropboxUploadError",
    "DropboxConfigurationError",
    "DropboxFileAlreadyExistsError",

    # --------------------------------------------------------
    # result
    # --------------------------------------------------------
    "DropboxUploadResult",

    # --------------------------------------------------------
    # path functions
    # --------------------------------------------------------
    "normalize_project_year",
    "normalize_project_no",
    "normalize_dropbox_filename",
    "build_project_id",
    "build_project_folder_path",
    "build_pdf_folder_path",
    "build_others_folder_path",
    "build_report_pdf_filename",
    "build_report_pdf_path",
    "build_other_file_path",

    # --------------------------------------------------------
    # Dropbox functions
    # --------------------------------------------------------
    "create_dropbox_client",
    "check_dropbox_connection",
    "get_dropbox_metadata",
    "dropbox_path_exists",
    "dropbox_file_exists",
    "dropbox_folder_exists",
    "ensure_dropbox_folder",
    "upload_bytes_to_dropbox",
]