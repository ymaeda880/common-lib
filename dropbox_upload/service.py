# -*- coding: utf-8 -*-
# common_lib/dropbox_upload/service.py
# ============================================================
# Dropboxファイル保存サービス
#
# 機能：
# - auth_portal_appのsecrets.tomlからDropbox OAuth設定を取得する
# - Dropbox接続を確認する
# - 保存先フォルダーを必要に応じて作成する
# - ファイルの存在を確認する
# - 通常アップロードと大容量アップロードを切り替える
# - 上書き可否を指定してファイルを保存する
#
# 方針：
# - OAuth認証情報は画面やログへ出力しない
# - 150MiB未満は通常アップロードを使用する
# - 大容量ファイルはアップロードセッションを使用する
# - 同名ファイルは明示的にoverwrite=Trueの場合だけ置き換える
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any

# ============================================================
# imports（3rd party）
# ============================================================
import dropbox

from dropbox.exceptions import (
    ApiError,
    AuthError,
    BadInputError,
    HttpError,
)
from dropbox.files import (
    CommitInfo,
    FileMetadata,
    FolderMetadata,
    UploadSessionCursor,
    WriteMode,
)


# ============================================================
# constants
# ============================================================
DROPBOX_APP_KEY_SECRET_KEY = "app_key"
DROPBOX_APP_SECRET_SECRET_KEY = "app_secret"
DROPBOX_REFRESH_TOKEN_SECRET_KEY = "refresh_token"

# ------------------------------------------------------------
# auth_portal_app secrets.toml
# ------------------------------------------------------------
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[2]

AUTH_PORTAL_SECRETS_PATH = (
    PROJECTS_ROOT
    / "auth_portal_project"
    / "auth_portal_app"
    / ".streamlit"
    / "secrets.toml"
)

# files_uploadでは150MiBを超えるファイルを扱わない
SIMPLE_UPLOAD_LIMIT_BYTES = 150 * 1024 * 1024

# アップロードセッションの1回当たりの送信サイズ
UPLOAD_SESSION_CHUNK_SIZE = 8 * 1024 * 1024

# ============================================================
# exceptions
# ============================================================
class DropboxUploadError(RuntimeError):
    """
    Dropbox保存処理で発生したエラー．
    """


class DropboxConfigurationError(DropboxUploadError):
    """
    Dropbox接続設定に関するエラー．
    """


class DropboxFileAlreadyExistsError(DropboxUploadError):
    """
    上書きを許可していない状態で同名ファイルが存在するエラー．
    """


# ============================================================
# result
# ============================================================
@dataclass(frozen=True)
class DropboxUploadResult:
    """
    Dropboxアップロード結果．
    """

    path_display: str
    filename: str
    size: int
    revision: str
    content_hash: str
    overwritten: bool


# ============================================================
# secrets
# ============================================================
def _read_dropbox_oauth_settings() -> tuple[str, str, str]:
    """
    auth_portal_appのsecrets.tomlから
    Dropbox OAuth設定を取得する．

    読込対象：

        [dropbox]
        app_key = "..."
        app_secret = "..."
        refresh_token = "..."
    """

    secrets_path = AUTH_PORTAL_SECRETS_PATH

    if not secrets_path.is_file():
        raise DropboxConfigurationError(
            "Dropbox接続設定ファイルが見つかりません．"
            f"設定先を確認してください：{secrets_path}"
        )

    try:
        with secrets_path.open("rb") as file:
            secrets_data = tomllib.load(file)

    except tomllib.TOMLDecodeError as exc:
        raise DropboxConfigurationError(
            "Dropbox接続設定ファイルのTOML形式が正しくありません．"
            f"設定先：{secrets_path}"
        ) from exc

    except OSError as exc:
        raise DropboxConfigurationError(
            "Dropbox接続設定ファイルを読み込めませんでした．"
            f"設定先：{secrets_path}"
        ) from exc

    dropbox_section = secrets_data.get(
        "dropbox",
        {},
    )

    if not isinstance(
        dropbox_section,
        dict,
    ):
        raise DropboxConfigurationError(
            "Dropbox接続設定の[dropbox]セクションが正しくありません．"
            f"設定先：{secrets_path}"
        )

    app_key = str(
        dropbox_section.get(
            DROPBOX_APP_KEY_SECRET_KEY,
            "",
        )
        or ""
    ).strip()

    app_secret = str(
        dropbox_section.get(
            DROPBOX_APP_SECRET_SECRET_KEY,
            "",
        )
        or ""
    ).strip()

    refresh_token = str(
        dropbox_section.get(
            DROPBOX_REFRESH_TOKEN_SECRET_KEY,
            "",
        )
        or ""
    ).strip()

    missing_keys: list[str] = []

    if not app_key:
        missing_keys.append("app_key")

    if not app_secret:
        missing_keys.append("app_secret")

    if not refresh_token:
        missing_keys.append("refresh_token")

    if missing_keys:
        raise DropboxConfigurationError(
            "Dropbox OAuth設定が不足しています："
            + "，".join(missing_keys)
            + f"．設定先：{secrets_path}"
        )

    return (
        app_key,
        app_secret,
        refresh_token,
    )


# ============================================================
# client
# ============================================================
def create_dropbox_client() -> dropbox.Dropbox:
    """
    Refresh tokenを使用してDropboxクライアントを生成する．
    """

    (
        app_key,
        app_secret,
        refresh_token,
    ) = _read_dropbox_oauth_settings()

    client = dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
        timeout=120,
    )

    # ===== DEBUG START =====
    # client.check_and_refresh_access_token()
    # ===== DEBUG END =====

    return client

# ============================================================
# connection check
# ============================================================
def check_dropbox_connection(
    client: dropbox.Dropbox,
) -> str:
    """
    Dropboxへの接続と認証状態を確認する．

    Returns:
        Dropboxアカウントの表示名．
    """

    try:
        account = client.users_get_current_account()

    except AuthError as exc:
        raise DropboxConfigurationError(
            "Dropboxの認証に失敗しました．"
            "App Key・App Secret・Refresh Tokenを確認してください．"
        ) from exc

    except HttpError as exc:
        raise DropboxUploadError(
            "Dropboxへの通信に失敗しました．"
            "ネットワーク接続を確認してください．"
        ) from exc

    except BadInputError as exc:
        raise DropboxUploadError(
            "Dropboxへの接続設定が正しくありません．"
        ) from exc

    except Exception as exc:
        raise DropboxUploadError(
            f"Dropboxへの接続確認に失敗しました：{exc}"
        ) from exc

    display_name = str(
        getattr(
            getattr(account, "name", None),
            "display_name",
            "",
        )
        or ""
    ).strip()

    if display_name:
        return display_name

    return str(
        getattr(
            account,
            "email",
            "",
        )
        or "Dropbox"
    )


# ============================================================
# path helpers
# ============================================================
def _normalize_dropbox_path(path: object) -> str:
    """
    Dropbox APIへ渡すパスを正規化する．
    """

    normalized = str(path or "").strip()

    if not normalized:
        raise ValueError("Dropboxパスが空です．")

    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    while "//" in normalized:
        normalized = normalized.replace("//", "/")

    if len(normalized) > 1:
        normalized = normalized.rstrip("/")

    return normalized


def _build_parent_paths(path: str) -> list[str]:
    """
    指定パスまでの親フォルダーパスを順番に生成する．

    Example:
        /PAIS/2026001/pdf

        [
            "/PAIS",
            "/PAIS/2026001",
            "/PAIS/2026001/pdf",
        ]
    """

    normalized = _normalize_dropbox_path(path)

    parts = [
        part
        for part in normalized.split("/")
        if part
    ]

    parent_paths: list[str] = []
    current = ""

    for part in parts:
        current = f"{current}/{part}"
        parent_paths.append(current)

    return parent_paths


# ============================================================
# metadata
# ============================================================
def get_dropbox_metadata(
    client: dropbox.Dropbox,
    path: object,
) -> FileMetadata | FolderMetadata | Any | None:
    """
    Dropbox上のファイルまたはフォルダー情報を取得する．

    対象が存在しない場合はNoneを返す．
    """

    normalized_path = _normalize_dropbox_path(path)

    try:
        return client.files_get_metadata(
            normalized_path,
        )

    except ApiError as exc:
        # --------------------------------------------------------
        # path/not_foundの場合だけ「存在しない」として扱う
        # --------------------------------------------------------
        try:
            if exc.error.is_path():
                path_error = exc.error.get_path()

                if path_error.is_not_found():
                    return None
        except Exception:
            pass

        raise DropboxUploadError(
            f"{type(exc).__name__}: {exc}"
        ) from exc

    except AuthError as exc:
        raise DropboxConfigurationError(
            "Dropboxの認証に失敗しました．"
            "App Key・App Secret・Refresh Tokenを確認してください．"
        ) from exc

    except HttpError as exc:
        raise DropboxUploadError(
            f"{type(exc).__name__}: {exc}"
        ) from exc


def dropbox_path_exists(
    client: dropbox.Dropbox,
    path: object,
) -> bool:
    """
    Dropbox上に指定パスが存在するか確認する．
    """

    return get_dropbox_metadata(
        client,
        path,
    ) is not None


def dropbox_file_exists(
    client: dropbox.Dropbox,
    path: object,
) -> bool:
    """
    Dropbox上に指定ファイルが存在するか確認する．
    """

    metadata = get_dropbox_metadata(
        client,
        path,
    )

    return isinstance(
        metadata,
        FileMetadata,
    )


def dropbox_folder_exists(
    client: dropbox.Dropbox,
    path: object,
) -> bool:
    """
    Dropbox上に指定フォルダーが存在するか確認する．
    """

    metadata = get_dropbox_metadata(
        client,
        path,
    )

    return isinstance(
        metadata,
        FolderMetadata,
    )


# ============================================================
# folder creation
# ============================================================
def ensure_dropbox_folder(
    client: dropbox.Dropbox,
    folder_path: object,
) -> None:
    """
    Dropbox上にフォルダーを作成する．

    親フォルダーから順番に確認し，
    存在しないフォルダーだけを作成する．
    """

    normalized_path = _normalize_dropbox_path(
        folder_path,
    )

    for current_path in _build_parent_paths(
        normalized_path,
    ):
        metadata = get_dropbox_metadata(
            client,
            current_path,
        )

        if isinstance(metadata, FolderMetadata):
            continue

        if metadata is not None:
            raise DropboxUploadError(
                "Dropbox上に同名のファイルが存在するため，"
                f"フォルダーを作成できません：{current_path}"
            )

        try:
            client.files_create_folder_v2(
                current_path,
                autorename=False,
            )

        except ApiError as exc:
            # ----------------------------------------------------
            # 並行処理などにより直前に作成された可能性を再確認
            # ----------------------------------------------------
            metadata_after_error = get_dropbox_metadata(
                client,
                current_path,
            )

            if isinstance(
                metadata_after_error,
                FolderMetadata,
            ):
                continue

            raise DropboxUploadError(
                f"Dropboxフォルダーを作成できませんでした：{current_path}"
            ) from exc

        except AuthError as exc:
            raise DropboxConfigurationError(
                f"{type(exc).__name__}: {exc}"
            ) from exc

        except HttpError as exc:
            raise DropboxUploadError(
                f"{type(exc).__name__}: {exc}"
            ) from exc


# ============================================================
# upload mode
# ============================================================
def _build_write_mode(
    *,
    overwrite: bool,
) -> WriteMode:
    """
    Dropboxアップロード時の書き込みモードを生成する．
    """

    if overwrite:
        return WriteMode.overwrite

    return WriteMode.add


# ============================================================
# simple upload
# ============================================================
def _upload_small_file(
    client: dropbox.Dropbox,
    *,
    file_bytes: bytes,
    destination_path: str,
    overwrite: bool,
) -> FileMetadata:
    """
    150MiB未満のファイルを通常アップロードする．
    """

    mode = _build_write_mode(
        overwrite=overwrite,
    )

    return client.files_upload(
        file_bytes,
        destination_path,
        mode=mode,
        autorename=False,
        mute=False,
        strict_conflict=True,
    )


# ============================================================
# upload session
# ============================================================
def _upload_large_file(
    client: dropbox.Dropbox,
    *,
    file_bytes: bytes,
    destination_path: str,
    overwrite: bool,
) -> FileMetadata:
    """
    大容量ファイルをアップロードセッションで保存する．
    """

    file_size = len(file_bytes)

    if file_size == 0:
        return _upload_small_file(
            client,
            file_bytes=file_bytes,
            destination_path=destination_path,
            overwrite=overwrite,
        )

    mode = _build_write_mode(
        overwrite=overwrite,
    )

    first_chunk_end = min(
        UPLOAD_SESSION_CHUNK_SIZE,
        file_size,
    )

    first_chunk = file_bytes[
        0:first_chunk_end
    ]

    session_start = client.files_upload_session_start(
        first_chunk,
        close=False,
    )

    cursor = UploadSessionCursor(
        session_id=session_start.session_id,
        offset=len(first_chunk),
    )

    commit = CommitInfo(
        path=destination_path,
        mode=mode,
        autorename=False,
        mute=False,
        strict_conflict=True,
    )

    while cursor.offset < file_size:
        remaining = file_size - cursor.offset

        if remaining <= UPLOAD_SESSION_CHUNK_SIZE:
            final_chunk = file_bytes[
                cursor.offset:file_size
            ]

            return client.files_upload_session_finish(
                final_chunk,
                cursor,
                commit,
            )

        next_offset = (
            cursor.offset
            + UPLOAD_SESSION_CHUNK_SIZE
        )

        next_chunk = file_bytes[
            cursor.offset:next_offset
        ]

        client.files_upload_session_append_v2(
            next_chunk,
            cursor,
            close=False,
        )

        cursor.offset = next_offset

    # ------------------------------------------------------------
    # 通常はwhile内のfinishでreturnする
    # 念のため空データで確定する
    # ------------------------------------------------------------
    return client.files_upload_session_finish(
        b"",
        cursor,
        commit,
    )


# ============================================================
# public upload API
# ============================================================
def upload_bytes_to_dropbox(
    client: dropbox.Dropbox,
    *,
    file_bytes: bytes,
    destination_path: object,
    overwrite: bool = False,
) -> DropboxUploadResult:
    """
    バイト列をDropboxへアップロードする．

    Args:
        client:
            Dropboxクライアント．

        file_bytes:
            アップロードするファイル内容．

        destination_path:
            Dropbox上の保存先フルパス．

        overwrite:
            Trueの場合は既存ファイルを置き換える．
            Falseの場合は既存ファイルがあればエラーにする．
    """

    if not isinstance(
        file_bytes,
        bytes,
    ):
        raise TypeError(
            "file_bytesはbytesで指定してください．"
        )

    normalized_path = _normalize_dropbox_path(
        destination_path,
    )

    # ------------------------------------------------------------
    # 親フォルダー確認
    # ------------------------------------------------------------
    parent_path = normalized_path.rsplit(
        "/",
        1,
    )[0]

    if not parent_path:
        parent_path = "/"

    if parent_path != "/":
        ensure_dropbox_folder(
            client,
            parent_path,
        )

    # ------------------------------------------------------------
    # 既存状態確認
    # ------------------------------------------------------------
    existing_metadata = get_dropbox_metadata(
        client,
        normalized_path,
    )

    file_already_exists = isinstance(
        existing_metadata,
        FileMetadata,
    )

    if isinstance(
        existing_metadata,
        FolderMetadata,
    ):
        raise DropboxUploadError(
            "保存先と同名のフォルダーが存在するため，"
            f"ファイルを保存できません：{normalized_path}"
        )

    if file_already_exists and not overwrite:
        raise DropboxFileAlreadyExistsError(
            f"Dropbox上に同名ファイルが存在します：{normalized_path}"
        )

    # ------------------------------------------------------------
    # upload
    # ------------------------------------------------------------
    try:
        if len(file_bytes) < SIMPLE_UPLOAD_LIMIT_BYTES:
            metadata = _upload_small_file(
                client,
                file_bytes=file_bytes,
                destination_path=normalized_path,
                overwrite=overwrite,
            )

        else:
            metadata = _upload_large_file(
                client,
                file_bytes=file_bytes,
                destination_path=normalized_path,
                overwrite=overwrite,
            )

    except ApiError as exc:
        raise DropboxUploadError(
            f"Dropboxへのアップロードに失敗しました：{normalized_path}"
        ) from exc

    except AuthError as exc:
        raise DropboxConfigurationError(
            "Dropboxの認証に失敗しました．"
            "App Key・App Secret・Refresh Tokenを確認してください．"
        ) from exc

    except HttpError as exc:
        raise DropboxUploadError(
            "Dropboxへの通信に失敗しました．"
            "ネットワーク接続を確認してください．"
        ) from exc

    except BadInputError as exc:
        raise DropboxUploadError(
            "Dropboxへ送信した保存条件が正しくありません．"
        ) from exc

    except DropboxUploadError:
        raise

    except Exception as exc:
        raise DropboxUploadError(
            f"Dropboxへのアップロード中にエラーが発生しました：{exc}"
        ) from exc

    # ------------------------------------------------------------
    # result
    # ------------------------------------------------------------
    path_display = str(
        getattr(
            metadata,
            "path_display",
            "",
        )
        or normalized_path
    )

    filename = str(
        getattr(
            metadata,
            "name",
            "",
        )
        or normalized_path.rsplit("/", 1)[-1]
    )

    size = int(
        getattr(
            metadata,
            "size",
            len(file_bytes),
        )
        or 0
    )

    revision = str(
        getattr(
            metadata,
            "rev",
            "",
        )
        or ""
    )

    content_hash = str(
        getattr(
            metadata,
            "content_hash",
            "",
        )
        or ""
    )

    return DropboxUploadResult(
        path_display=path_display,
        filename=filename,
        size=size,
        revision=revision,
        content_hash=content_hash,
        overwritten=file_already_exists,
    )