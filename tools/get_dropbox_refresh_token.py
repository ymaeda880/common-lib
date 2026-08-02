# -*- coding: utf-8 -*-
# get_dropbox_refresh_token.py
# ============================================================
# Dropbox Refresh token取得
#
# 取得後は，このファイルを削除する．
# ============================================================

from __future__ import annotations

import getpass

import dropbox


# ============================================================
# OAuth認証
# ============================================================
def main() -> None:
    app_key = input(
        "Dropbox App key："
    ).strip()

    app_secret = getpass.getpass(
        "Dropbox App secret："
    ).strip()

    if not app_key:
        raise RuntimeError(
            "App keyが入力されていません．"
        )

    if not app_secret:
        raise RuntimeError(
            "App secretが入力されていません．"
        )

    auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(
        app_key,
        app_secret,
        token_access_type="offline",
    )

    authorize_url = auth_flow.start()

    print()
    print("次のURLをブラウザーで開いてください．")
    print()
    print(authorize_url)
    print()
    print("Dropboxで許可した後，表示された認証コードを")
    print("このターミナルへ貼り付けてください．")
    print()

    authorization_code = input(
        "認証コード："
    ).strip()

    if not authorization_code:
        raise RuntimeError(
            "認証コードが入力されていません．"
        )

    oauth_result = auth_flow.finish(
        authorization_code,
    )

    refresh_token = str(
        oauth_result.refresh_token
        or ""
    ).strip()

    if not refresh_token:
        raise RuntimeError(
            "Refresh tokenを取得できませんでした．"
        )

    print()
    print("========================================")
    print("Refresh token取得成功")
    print("========================================")
    print()
    print(refresh_token)
    print()
    print("この値をsecrets.tomlのrefresh_tokenへ保存してください．")


if __name__ == "__main__":
    main()