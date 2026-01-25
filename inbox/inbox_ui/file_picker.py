# -*- coding: utf-8 -*-
# common_lib/inbox/inbox_ui/file_picker.py

from __future__ import annotations

# ============================================================
# 📥 Inbox ファイルピッカー（UI部品）
# ============================================================
# 目的：
# - inbox_items.db を参照して「一覧 → 選択 → 読み込み」を共通UI化する
# - 画像/PDF/text/zip/その他すべてを raw bytes で返す（加工しない）
#
# やること：
# - kind 絞り込み（任意）
# - ページング（prev/next）
# - 選択（radio：未選択可）
# - stored_rel → user_root 配下の安全検証 → bytes 読み込み
#
# やらないこと：
# - session_state の更新（呼び出し側がやる）
# - last_viewed 更新（要件次第。ここでは触らない）
# - 画像PNG正規化 / text decode（用途ごとに呼び出し側で）
# ============================================================

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import streamlit as st

# ============================================================
# ✅ パス規約（正本）：common_lib 側を使う
# ============================================================
from common_lib.inbox.inbox_common.paths import (
    resolve_inbox_root,
    items_db_path,
    user_root,
    resolve_file_path,
)

# ============================================================
# 返却データ（呼び出し側が受け取る結果）
# ============================================================
@dataclass
class InboxPickedFile:
    # ----------------------------
    # 実データ（生bytes）
    # ----------------------------
    data_bytes: bytes

    # ----------------------------
    # DBメタ（ログ/トレース用）
    # ----------------------------
    item_id: str
    kind: str
    original_name: str
    stored_rel: str
    added_at: str


# ============================================================
# DB：一覧（ページ）取得
# ============================================================
def _query_inbox_items_page(
    *,
    inbox_root: Path,
    user_sub: str,
    limit: int,
    offset: int,
    kinds: Optional[Sequence[str]],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    inbox_items を added_at desc でページ取得する。

    kinds:
      - None: 全件
      - ["image"] / ["pdf","text"] のように指定：該当 kind のみ
    """
    db_path = items_db_path(inbox_root, user_sub)
    if not db_path.exists():
        return [], 0

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()

        # ----------------------------
        # ① 件数（total）
        # ----------------------------
        if kinds and len(kinds) > 0:
            ph = ",".join(["?"] * len(kinds))
            cur.execute(
                f"SELECT COUNT(1) FROM inbox_items WHERE kind IN ({ph})",
                tuple(kinds),
            )
        else:
            cur.execute("SELECT COUNT(1) FROM inbox_items")
        total = int(cur.fetchone()[0] or 0)

        # ----------------------------
        # ② ページ取得
        # ----------------------------
        if kinds and len(kinds) > 0:
            ph = ",".join(["?"] * len(kinds))
            cur.execute(
                f"""
                SELECT item_id, kind, original_name, stored_rel, added_at
                FROM inbox_items
                WHERE kind IN ({ph})
                ORDER BY added_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple(kinds) + (int(limit), int(offset)),
            )
        else:
            cur.execute(
                """
                SELECT item_id, kind, original_name, stored_rel, added_at
                FROM inbox_items
                ORDER BY added_at DESC
                LIMIT ? OFFSET ?
                """,
                (int(limit), int(offset)),
            )

        rows: List[Dict[str, Any]] = []
        for item_id, kind, original_name, stored_rel, added_at in cur.fetchall():
            rows.append(
                {
                    "item_id": str(item_id),
                    "kind": str(kind or ""),
                    "original_name": str(original_name or ""),
                    "stored_rel": str(stored_rel or ""),
                    "added_at": str(added_at or ""),
                }
            )

        return rows, total

    finally:
        con.close()


# ============================================================
# stored_rel → 実ファイルの安全解決 → bytes 読み込み
# ============================================================
def _safe_read_inbox_file_bytes(
    *,
    inbox_root: Path,
    user_sub: str,
    stored_rel: str,
) -> bytes:
    """
    stored_rel を user_root 配下に安全に解決して bytes を返す。
    - resolve() した結果が user_root の外に出ないことを検証する（パストラバーサル対策）
    """
    ur = user_root(inbox_root, user_sub).resolve()

    # resolve_file_path は「規約上の解決」：ここで resolve() して安全検証
    p = resolve_file_path(inbox_root, user_sub, stored_rel).resolve()

    # ----------------------------
    # ① user_root の外に出ていないか検証
    # ----------------------------
    if p != ur and ur not in p.parents:
        raise ValueError("Invalid stored_rel (path traversal detected).")

    # ----------------------------
    # ② 実ファイル存在チェック
    # ----------------------------
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    # ----------------------------
    # ③ raw bytes として読む（加工しない）
    # ----------------------------
    return p.read_bytes()


# ============================================================
# UIコア：Inbox から選択→読み込み（toggle有無を切替）
# ============================================================
def _render_inbox_file_picker_core(
    *,
    projects_root: Path,
    user_sub: str,
    key_prefix: str,
    # ----------------------------
    # toggle 制御
    # ----------------------------
    enable_toggle: bool,
    toggle_label: str,
    toggle_default: bool,
    # ----------------------------
    # 表示・操作パラメータ
    # ----------------------------
    page_size: int,
    # ----------------------------
    # kind 絞り込み（None で全件）
    # ----------------------------
    kinds: Optional[Sequence[str]],
    # ----------------------------
    # 表示ラベル設定
    # ----------------------------
    show_kind_in_label: bool,
    show_added_at_in_label: bool,
) -> Optional[InboxPickedFile]:
    """
    戻り値：
      - 読み込み確定＆成功：InboxPickedFile
      - それ以外：None（未操作/未選択/失敗）
    """

    # ============================================================
    # 0) Inbox ルート解決（正本 resolver）
    # ============================================================
    inbox_root = resolve_inbox_root(projects_root)

    # ============================================================
    # 1) toggle（enable_toggle=True のときだけ描画）
    # ============================================================
    if enable_toggle:
        use_inbox = st.toggle(toggle_label, value=toggle_default, key=f"{key_prefix}_toggle")
        if not use_inbox:
            return None

    # ============================================================
    # 2) Inbox ルート存在確認（落とさず案内のみ）
    # ============================================================
    if not inbox_root.exists():
        st.info(f"InBoxStorages が見つかりません: {inbox_root}")
        return None

    # ============================================================
    # 3) ページング state（key_prefix 必須で衝突回避）
    # ============================================================
    K_PAGE = f"{key_prefix}_page"
    K_SELECTED = f"{key_prefix}_selected_item_id"

    if K_PAGE not in st.session_state:
        st.session_state[K_PAGE] = 0

    page_index = int(st.session_state[K_PAGE])
    offset = page_index * int(page_size)

    # ============================================================
    # 4) DB から当該ページ取得（rows + total）
    # ============================================================
    rows, total = _query_inbox_items_page(
        inbox_root=inbox_root,
        user_sub=user_sub,
        limit=int(page_size),
        offset=int(offset),
        kinds=kinds,
    )

    if total <= 0 or not rows:
        st.caption("Inbox に対象ファイルがありません。")
        return None

    # ============================================================
    # 5) last_page 補正（はみ出しを自動補正）
    # ============================================================
    last_page = max(0, (total - 1) // int(page_size))
    if page_index > last_page:
        page_index = last_page
        st.session_state[K_PAGE] = last_page
        offset = page_index * int(page_size)
        rows, total = _query_inbox_items_page(
            inbox_root=inbox_root,
            user_sub=user_sub,
            limit=int(page_size),
            offset=int(offset),
            kinds=kinds,
        )

    # ============================================================
    # 6) UI：ページ移動（移動時は選択クリア＝事故防止）
    # ============================================================
    def _clear_selection() -> None:
        if K_SELECTED in st.session_state:
            st.session_state.pop(K_SELECTED, None)

    nav1, nav2, nav3, nav4 = st.columns([1, 1, 3.2, 4.8])
    with nav1:
        if st.button("⬅ 前へ", disabled=(page_index <= 0), key=f"{key_prefix}_prev"):
            st.session_state[K_PAGE] = max(page_index - 1, 0)
            _clear_selection()
            st.rerun()
    with nav2:
        if st.button("次へ ➡", disabled=(page_index >= last_page), key=f"{key_prefix}_next"):
            st.session_state[K_PAGE] = min(page_index + 1, last_page)
            _clear_selection()
            st.rerun()
    with nav3:
        start = offset + 1
        end = min(offset + int(page_size), total)
        st.caption(f"件数: {total} ／ ページ: {page_index + 1}/{last_page + 1}（{start}–{end}）")
    with nav4:
        #st.caption("※ ページ移動時は選択がクリアされます（事故防止）")
        pass

    # ============================================================
    # 7) UI：選択（radio：未選択OK）
    # ============================================================
    options = [r["item_id"] for r in rows]

    label_map: Dict[str, str] = {}
    for r in rows:
        head = (r["original_name"] or r["item_id"]).strip()
        tail_parts = []
        if show_kind_in_label:
            tail_parts.append(f"kind={r['kind']}")
        if show_added_at_in_label and r.get("added_at"):
            tail_parts.append(f"added_at={r['added_at']}")
        if tail_parts:
            label_map[r["item_id"]] = f"{head}  （" + " / ".join(tail_parts) + "）"
        else:
            label_map[r["item_id"]] = head

    def _fmt(item_id: str) -> str:
        return label_map.get(str(item_id), str(item_id))

    selected_item_id = st.radio(
        "ファイルを選択（original_name）",
        options=options,
        index=None,
        format_func=_fmt,
        key=K_SELECTED,
    )

    # ============================================================
    # 8) UI：読み込み確定（押した時だけ実ファイルを読む）
    # ============================================================
    cbtn1, cbtn2 = st.columns([2, 8])
    with cbtn1:
        load_clicked = st.button("📥 選択ファイルを読み込む", key=f"{key_prefix}_load")
    with cbtn2:
        #st.caption("※ 押した時点で stored_rel を解決し、bytes を読み込んで返します。")
        pass

    if not load_clicked:
        return None

    # ============================================================
    # 9) 未選択チェック
    # ============================================================
    if not selected_item_id:
        st.warning("先にファイルを選択してください。")
        return None

    # ============================================================
    # 10) 選択行を確定（stored_rel が必要）
    # ============================================================
    picked_row: Optional[Dict[str, Any]] = None
    for r in rows:
        if str(r.get("item_id")) == str(selected_item_id):
            picked_row = r
            break

    if not picked_row:
        st.error("選択されたファイルの情報が見つかりません（ページ更新の可能性）。")
        return None

    # ============================================================
    # 11) 実ファイル読み込み（安全検証→bytes→返却）
    # ============================================================
    try:
        data = _safe_read_inbox_file_bytes(
            inbox_root=inbox_root,
            user_sub=user_sub,
            stored_rel=str(picked_row.get("stored_rel") or ""),
        )
        st.caption("Inbox から読み込みました。")

        return InboxPickedFile(
            data_bytes=data,
            item_id=str(picked_row.get("item_id") or ""),
            kind=str(picked_row.get("kind") or ""),
            original_name=str(picked_row.get("original_name") or ""),
            stored_rel=str(picked_row.get("stored_rel") or ""),
            added_at=str(picked_row.get("added_at") or ""),
        )

    except Exception as e:
        st.error(f"Inbox ファイルの読み込みに失敗しました: {e}")
        return None


# ============================================================
# UI：Inbox から選択→読み込み（公開関数：トグルあり）
# ============================================================
def render_inbox_file_picker(
    *,
    projects_root: Path,
    user_sub: str,
    key_prefix: str,
    # ----------------------------
    # 表示・操作パラメータ
    # ----------------------------
    toggle_label: str = "📥 Inboxから読み込む",
    toggle_default: bool = False,
    page_size: int = 10,
    # ----------------------------
    # kind 絞り込み（None で全件）
    # ----------------------------
    kinds: Optional[Sequence[str]] = None,
    # ----------------------------
    # 表示ラベル設定
    # ----------------------------
    show_kind_in_label: bool = True,
    show_added_at_in_label: bool = False,
) -> Optional[InboxPickedFile]:
    """
    戻り値：
      - 読み込み確定＆成功：InboxPickedFile
      - それ以外：None（未操作/未選択/失敗）
    """
    return _render_inbox_file_picker_core(
        projects_root=projects_root,
        user_sub=user_sub,
        key_prefix=key_prefix,
        enable_toggle=True,
        toggle_label=toggle_label,
        toggle_default=toggle_default,
        page_size=page_size,
        kinds=kinds,
        show_kind_in_label=show_kind_in_label,
        show_added_at_in_label=show_added_at_in_label,
    )


# ============================================================
# UI：Inbox から選択→読み込み（公開関数：トグルなし）
# ============================================================
def render_inbox_file_picker_no_toggle(
    *,
    projects_root: Path,
    user_sub: str,
    key_prefix: str,
    page_size: int = 10,
    kinds: Optional[Sequence[str]] = None,
    show_kind_in_label: bool = True,
    show_added_at_in_label: bool = False,
) -> Optional[InboxPickedFile]:
    """
    トグル無し版：
      - 「タブの中に置く」等、トグルが不要なUIで使う
      - 中身（ページング/選択/読み込み）は常に表示
    """
    return _render_inbox_file_picker_core(
        projects_root=projects_root,
        user_sub=user_sub,
        key_prefix=key_prefix,
        enable_toggle=False,
        toggle_label="",
        toggle_default=True,
        page_size=page_size,
        kinds=kinds,
        show_kind_in_label=show_kind_in_label,
        show_added_at_in_label=show_added_at_in_label,
    )
