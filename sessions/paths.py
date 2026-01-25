# -*- coding: utf-8 -*-
# common_lib/sessions/paths.py
from __future__ import annotations

from pathlib import Path


def resolve_sessions_db_path(projects_root: Path, storages_root: Path | None = None) -> Path:
    """
    sessions.db の正本パスを返す。

    方針（重要）：
    - このモジュールは「importしただけで streamlit 依存に落ちない」ことを優先する。
    - storages_root を渡せば、純粋にパス計算だけ（CLI/worker/testでも安全）。
    - storages_root が未指定のときだけ、遅延 import により resolve を試みる。
      （Streamlit 実行時を想定）
    - 旧来の projects_root/Storages が存在して、resolve結果とズレる場合は
      main が二重化しているので例外で停止する（黙って進ませない）。
    """
    if not isinstance(projects_root, Path):
        raise TypeError("projects_root must be pathlib.Path")

    if storages_root is None:
        # 遅延 import（paths.py import 時には storages_config/env/config を読まない）
        try:
            from common_lib.storage.external_ssd_root import resolve_storage_subdir_root  # 遅延
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "resolve_sessions_db_path: could not import resolve_storage_subdir_root. "
                "Pass storages_root explicitly."
            ) from e

        storages_root = resolve_storage_subdir_root(
            projects_root=projects_root,
            subdir="Storages",
            role="main",
        )

    if not isinstance(storages_root, Path):
        raise TypeError("storages_root must be pathlib.Path")

    # 移行期ガード：legacy な projects_root/Storages が存在してズレるなら停止
    legacy = projects_root / "Storages"
    if legacy.exists() and legacy.is_dir():
        if legacy.resolve() != storages_root.resolve():
            raise RuntimeError(
                "\n".join(
                    [
                        "Storages root mismatch detected (main is split).",
                        f"- legacy:   {legacy.resolve()}",
                        f"- resolved: {storages_root.resolve()}",
                        "対処：projects_root/Storages の残骸を整理するか、"
                        "全アプリが同じ storages_root を参照していることを確認してください。",
                    ]
                )
            )

    return storages_root / "_admin" / "sessions" / "sessions.db"
