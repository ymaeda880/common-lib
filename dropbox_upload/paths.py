# -*- coding: utf-8 -*-
# common_lib/dropbox_upload/paths.py
# ============================================================
# Dropbox保存先パス生成
#
# 機能：
# - 年度とプロジェクト番号を正規化する
# - Dropbox上の案件IDを生成する
# - 報告書PDFと関連書類の保存先パスを生成する
#
# 方針：
# - Dropbox上の作業ルートは /PAIS とする
# - プロジェクト番号は3桁へゼロ埋めする
# - Dropboxパスは常に / から始める
# ============================================================

from __future__ import annotations

# ============================================================
# constants
# ============================================================
DROPBOX_ROOT_DIR = "/PAIS"

PROJECT_YEAR_MIN = 1972
PROJECT_YEAR_MAX = 9999

PROJECT_NO_MIN = 1
PROJECT_NO_MAX = 999


# ============================================================
# 年度正規化
# ============================================================
def normalize_project_year(value: object) -> int:
    """
    年度を4桁の整数として正規化する．

    Raises:
        ValueError:
            年度が整数へ変換できない場合，
            または許容範囲外の場合．
    """

    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("年度は4桁の整数で入力してください．") from exc

    if year < PROJECT_YEAR_MIN or year > PROJECT_YEAR_MAX:
        raise ValueError(
            f"年度は{PROJECT_YEAR_MIN}から{PROJECT_YEAR_MAX}の範囲で入力してください．"
        )

    if len(str(year)) != 4:
        raise ValueError("年度は4桁で入力してください．")

    return year


# ============================================================
# プロジェクト番号正規化
# ============================================================
def normalize_project_no(value: object) -> str:
    """
    プロジェクト番号を3桁の文字列へ正規化する．

    Examples:
        1   -> "001"
        12  -> "012"
        123 -> "123"

    Raises:
        ValueError:
            プロジェクト番号が整数へ変換できない場合，
            または1から999の範囲外の場合．
    """

    try:
        project_no = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "プロジェクト番号は1から999の整数で入力してください．"
        ) from exc

    if project_no < PROJECT_NO_MIN or project_no > PROJECT_NO_MAX:
        raise ValueError(
            f"プロジェクト番号は"
            f"{PROJECT_NO_MIN}から{PROJECT_NO_MAX}の範囲で入力してください．"
        )

    return f"{project_no:03d}"


# ============================================================
# 案件ID生成
# ============================================================
def build_project_id(
    *,
    year: object,
    project_no: object,
) -> str:
    """
    年度とプロジェクト番号から7桁の案件IDを生成する．

    Examples:
        year=2026, project_no=1 -> "2026001"
    """

    normalized_year = normalize_project_year(year)
    normalized_project_no = normalize_project_no(project_no)

    return f"{normalized_year}{normalized_project_no}"


# ============================================================
# 案件フォルダーパス
# ============================================================
def build_project_folder_path(
    *,
    year: object,
    project_no: object,
) -> str:
    """
    Dropbox上の案件フォルダーパスを生成する．

    Example:
        /PAIS/2026001
    """

    project_id = build_project_id(
        year=year,
        project_no=project_no,
    )

    return f"{DROPBOX_ROOT_DIR}/{project_id}"


# ============================================================
# 報告書PDFフォルダーパス
# ============================================================
def build_pdf_folder_path(
    *,
    year: object,
    project_no: object,
) -> str:
    """
    Dropbox上の報告書PDF保存フォルダーパスを生成する．

    Example:
        /PAIS/2026001/pdf
    """

    project_folder_path = build_project_folder_path(
        year=year,
        project_no=project_no,
    )

    return f"{project_folder_path}/pdf"


# ============================================================
# 関連書類フォルダーパス
# ============================================================
def build_others_folder_path(
    *,
    year: object,
    project_no: object,
) -> str:
    """
    Dropbox上の関連書類保存フォルダーパスを生成する．

    Example:
        /PAIS/2026001/others
    """

    project_folder_path = build_project_folder_path(
        year=year,
        project_no=project_no,
    )

    return f"{project_folder_path}/others"


# ============================================================
# 報告書PDFファイル名
# ============================================================
def build_report_pdf_filename(
    *,
    year: object,
    project_no: object,
) -> str:
    """
    Dropboxへ保存する報告書PDFファイル名を生成する．

    Example:
        2026001.pdf
    """

    project_id = build_project_id(
        year=year,
        project_no=project_no,
    )

    return f"{project_id}.pdf"


# ============================================================
# 報告書PDF保存パス
# ============================================================
def build_report_pdf_path(
    *,
    year: object,
    project_no: object,
) -> str:
    """
    Dropbox上の報告書PDF保存先パスを生成する．

    Example:
        /PAIS/2026001/pdf/2026001.pdf
    """

    folder_path = build_pdf_folder_path(
        year=year,
        project_no=project_no,
    )

    filename = build_report_pdf_filename(
        year=year,
        project_no=project_no,
    )

    return f"{folder_path}/{filename}"


# ============================================================
# Dropboxファイル名正規化
# ============================================================
def normalize_dropbox_filename(filename: object) -> str:
    """
    関連書類として保存するファイル名を検証する．

    Dropbox上では元のファイル名をそのまま使用するが，
    パス区切り文字を含むファイル名は許可しない．

    Raises:
        ValueError:
            ファイル名が空の場合，
            またはパス区切り文字を含む場合．
    """

    normalized = str(filename or "").strip()

    if not normalized:
        raise ValueError("ファイル名を取得できませんでした．")

    if "/" in normalized or "\\" in normalized:
        raise ValueError(
            f"ファイル名に使用できない文字が含まれています：{normalized}"
        )

    if normalized in {".", ".."}:
        raise ValueError(
            f"使用できないファイル名です：{normalized}"
        )

    return normalized


# ============================================================
# 関連書類保存パス
# ============================================================
def build_other_file_path(
    *,
    year: object,
    project_no: object,
    filename: object,
) -> str:
    """
    Dropbox上の関連書類保存先パスを生成する．

    Example:
        /PAIS/2026001/others/打合せ記録.docx
    """

    folder_path = build_others_folder_path(
        year=year,
        project_no=project_no,
    )

    normalized_filename = normalize_dropbox_filename(filename)

    return f"{folder_path}/{normalized_filename}"