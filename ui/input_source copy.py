# common_lib/ui/input_source.py
# ============================================================
# Input source UI
#
# 機能：
# - paste / upload / inbox の入力UIを共通描画する
# - ファイル内容は抽出せず、そのまま bytes / text として返す
# - PDF抽出・OCR・AI処理は page 側で行う
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import streamlit as st

from common_lib.inbox.inbox_ui.file_picker import (
    InboxPickedFile,
    render_inbox_file_picker_no_toggle,
)


# ============================================================
# types
# ============================================================
InputSourceType = Literal["paste", "upload", "inbox"]


# ============================================================
# result
# ============================================================
@dataclass(frozen=True)
class InputSourceResult:
    source_type: str
    confirmed: bool
    text: str
    data_bytes: bytes
    file_name: str
    suffix: str
    kind: str


# ============================================================
# helper：空 result
# ============================================================
def empty_input_source_result() -> InputSourceResult:
    return InputSourceResult(
        source_type="",
        confirmed=False,
        text="",
        data_bytes=b"",
        file_name="",
        suffix="",
        kind="",
    )


# ============================================================
# helper：suffix
# ============================================================
def _suffix_of(name: str) -> str:
    return Path(name or "").suffix.lower()


# ============================================================
# helper：method labels
# ============================================================
def _source_label(source: str) -> str:
    if source == "paste":
        return "📝 貼り付けテキスト"
    if source == "upload":
        return "📁 ファイルから"
    if source == "inbox":
        return "📥 Inboxから"
    return source


# ============================================================
# input source UI
# ============================================================
def render_input_source(
    *,
    projects_root: Path,
    user_sub: str,
    page_name: str,
    key_prefix: str,
    allowed_sources: list[InputSourceType],
    upload_types: list[str] | None = None,
    inbox_kinds: list[str] | None = None,
    input_label: str = "入力方法",
    paste_label: str = "ここに本文を貼り付け",
    upload_label: str = "ファイルをアップロード",
    confirm_button_label: str = "① 確定",
    inbox_page_size: int = 8,
) -> InputSourceResult:
    # ------------------------------------------------------------
    # 入力方式チェック
    # ------------------------------------------------------------
    if not allowed_sources:
        st.error("allowed_sources が空です。")
        return empty_input_source_result()

    # ------------------------------------------------------------
    # session keys
    # ------------------------------------------------------------
    k_method = f"{key_prefix}__input_method"
    k_text = f"{key_prefix}__text"
    k_bytes = f"{key_prefix}__bytes"
    k_name = f"{key_prefix}__name"
    k_kind = f"{key_prefix}__kind"
    k_source = f"{key_prefix}__source"
    k_confirmed = f"{key_prefix}__confirmed"

    # ------------------------------------------------------------
    # session 初期化
    # ------------------------------------------------------------
    st.session_state.setdefault(k_method, allowed_sources[0])
    st.session_state.setdefault(k_text, "")
    st.session_state.setdefault(k_bytes, b"")
    st.session_state.setdefault(k_name, "")
    st.session_state.setdefault(k_kind, "")
    st.session_state.setdefault(k_source, "")
    st.session_state.setdefault(k_confirmed, False)

    # ------------------------------------------------------------
    # 入力方式
    # ------------------------------------------------------------
    source = st.radio(
        input_label,
        options=allowed_sources,
        format_func=_source_label,
        key=k_method,
        horizontal=True,
    )

    # ------------------------------------------------------------
    # 入力方式変更時は確定状態を解除
    # ------------------------------------------------------------
    if st.session_state.get(k_source) != source:
        st.session_state[k_source] = source
        st.session_state[k_confirmed] = False
        st.session_state[k_text] = ""
        st.session_state[k_bytes] = b""
        st.session_state[k_name] = ""
        st.session_state[k_kind] = ""

    # ------------------------------------------------------------
    # paste
    # ------------------------------------------------------------
    if source == "paste":
        pasted = st.text_area(
            paste_label,
            key=f"{key_prefix}__paste_area",
            height=260,
        )

        if st.button(
            confirm_button_label,
            type="primary",
            key=f"{key_prefix}__confirm_paste",
        ):
            if not str(pasted or "").strip():
                st.warning("テキストを入力してください。")
            else:
                st.session_state[k_text] = str(pasted or "")
                st.session_state[k_bytes] = b""
                st.session_state[k_name] = "pasted_text.txt"
                st.session_state[k_kind] = "text"
                st.session_state[k_confirmed] = True

    # ------------------------------------------------------------
    # upload
    # ------------------------------------------------------------
    elif source == "upload":
        # uploaded = st.file_uploader(
        #     upload_label,
        #     type=upload_types,
        #     key=f"{key_prefix}__uploader",
        # )

        uploaded = st.file_uploader(
            upload_label,
            type=None,
            key=f"{key_prefix}__uploader",
        )

        if upload_types:
            allowed_suffixes = {
                f".{str(x).lower().lstrip('.')}"
                for x in upload_types
            }
        else:
            allowed_suffixes = set()

        if st.button(
            confirm_button_label,
            type="primary",
            disabled=(uploaded is None),
            key=f"{key_prefix}__confirm_upload",
        ):
            # if uploaded is None:
            #     st.warning("ファイルを選択してください。")
            # else:
            #     data = uploaded.getvalue()


            if uploaded is None:
                st.warning("ファイルを選択してください。")
            else:
                file_name = uploaded.name or "uploaded_file"
                suffix = _suffix_of(file_name)

                if allowed_suffixes and suffix not in allowed_suffixes:
                    st.error(
                        "このページで使えるファイルは "
                        + " / ".join(sorted(allowed_suffixes))
                        + " だけです。"
                    )
                    st.info(
                        f"選択されたファイル：{file_name}\n\n"
                        "PDF、Word（.docx）、テキスト（.txt）など、"
                        "このページで指定された形式のファイルを選び直してください。"
                    )
                    st.session_state[k_confirmed] = False
                    return empty_input_source_result()

                data = uploaded.getvalue()



                if not data:
                    st.warning("ファイルの読み込みに失敗しました（0バイト）。")
                else:
                    st.session_state[k_text] = ""
                    st.session_state[k_bytes] = data
                    st.session_state[k_name] = uploaded.name or "uploaded_file"
                    st.session_state[k_kind] = "upload"
                    st.session_state[k_confirmed] = True

    # ------------------------------------------------------------
    # inbox
    # ------------------------------------------------------------
    elif source == "inbox":
        picked: InboxPickedFile | None = render_inbox_file_picker_no_toggle(
            projects_root=projects_root,
            user_sub=user_sub,
            key_prefix=f"{key_prefix}__inbox_picker",
            page_size=inbox_page_size,
            kinds=inbox_kinds,
            show_kind_in_label=True,
            show_added_at_in_label=True,
        )

        if picked is not None:
            st.session_state[k_bytes] = picked.data_bytes or b""
            st.session_state[k_name] = picked.original_name or "inbox_file"
            st.session_state[k_kind] = picked.kind or ""
            st.session_state[k_text] = ""
            st.session_state[k_confirmed] = False
            st.success("✅ Inbox から読み込みました")

        if st.button(
            confirm_button_label,
            type="primary",
            disabled=(not bool(st.session_state.get(k_bytes, b""))),
            key=f"{key_prefix}__confirm_inbox",
        ):
            if not bool(st.session_state.get(k_bytes, b"")):
                st.warning("Inbox からファイルを選択してください。")
            else:
                st.session_state[k_confirmed] = True

    # ------------------------------------------------------------
    # 不正 source
    # ------------------------------------------------------------
    else:
        st.error(f"未対応の入力方式です: {source}")
        return empty_input_source_result()

    # ------------------------------------------------------------
    # result
    # ------------------------------------------------------------
    file_name = str(st.session_state.get(k_name) or "")

    return InputSourceResult(
        source_type=str(source),
        confirmed=bool(st.session_state.get(k_confirmed)),
        text=str(st.session_state.get(k_text) or ""),
        data_bytes=st.session_state.get(k_bytes, b"") or b"",
        file_name=file_name,
        suffix=_suffix_of(file_name),
        kind=str(st.session_state.get(k_kind) or ""),
    )