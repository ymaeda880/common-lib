# common_lib/ui/input_source.py
# ============================================================
# Input source UI
#
# 機能：
# - paste / upload / inbox / internal の入力UIを共通描画する
# - ファイル内容は抽出せず、そのまま bytes / text として返す
# - PDF抽出・OCR・AI処理は page 側で行う
# - internal の具体的な読み込み先・一覧表示・検証は page 側 renderer に委譲する
# - 本処理（解析/OCR/AI実行）は page 側が行う
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import streamlit as st

from common_lib.inbox.inbox_ui.file_picker import (
    InboxPickedFile,
    render_inbox_file_picker_no_toggle,
)


# ============================================================
# types
# ============================================================
InputSourceType = Literal[
    "paste",
    "upload",
    "inbox",
    "internal",
    "sample",
]


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
# internal renderer type
# ============================================================
InternalInputRenderer = Callable[[], InputSourceResult]
SampleInputRenderer = Callable[[], InputSourceResult]

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

    if source == "internal":
        return "💾 内部保存から"
    
    if source == "sample":
        return "🧪 サンプルから"

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
    inbox_extensions: list[str] | None = None,
    internal_renderer: InternalInputRenderer | None = None,
    sample_renderer: SampleInputRenderer | None = None,
    input_label: str = "入力方法",
    paste_label: str = "ここに本文を貼り付け",
    upload_label: str = "ファイルをアップロード",
    inbox_page_size: int = 8,
) -> InputSourceResult:

    # ------------------------------------------------------------
    # 入力方式チェック
    # ------------------------------------------------------------
    if not allowed_sources:
        st.error("allowed_sources が空です。")
        return empty_input_source_result()

    # ------------------------------------------------------------
    # internal renderer チェック
    # ------------------------------------------------------------
    if (
        "internal" in allowed_sources
        and internal_renderer is None
    ):
        st.error(
            "allowed_sources に internal が含まれていますが、"
            "internal_renderer が指定されていません。"
        )
        return empty_input_source_result()

    # ------------------------------------------------------------
    # sample renderer チェック
    # ------------------------------------------------------------
    if (
        "sample" in allowed_sources
        and sample_renderer is None
    ):
        st.error(
            "allowed_sources に sample が含まれていますが、"
            "sample_renderer が指定されていません。"
        )
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
    st.session_state.setdefault(
        k_method,
        allowed_sources[0],
    )

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
    # 入力方式変更時は状態をクリア
    # ------------------------------------------------------------
    if st.session_state.get(k_source) != source:
        st.session_state[k_source] = source

        st.session_state[k_confirmed] = False
        st.session_state[k_text] = ""
        st.session_state[k_bytes] = b""
        st.session_state[k_name] = ""
        st.session_state[k_kind] = ""

    # ============================================================
    # paste
    # ============================================================
    if source == "paste":
        pasted = st.text_area(
            paste_label,
            key=f"{key_prefix}__paste_area",
            height=260,
        )

        # ------------------------------------------------------------
        # paste confirm
        # ------------------------------------------------------------
        load_clicked = st.button(
            "📝 貼り付けテキストを確定",
            key=f"{key_prefix}__confirm_paste",
        )

        if load_clicked:
            if not str(pasted or "").strip():
                st.warning("テキストを入力してください。")
            else:
                st.session_state[k_text] = str(pasted or "")
                st.session_state[k_bytes] = b""
                st.session_state[k_name] = "pasted_text.txt"
                st.session_state[k_kind] = "text"
                st.session_state[k_confirmed] = True

                st.success(
                    "✅ 貼り付けテキストを確定しました"
                )

    # ============================================================
    # upload
    # ============================================================
    elif source == "upload":
        uploaded = st.file_uploader(
            upload_label,
            type=None,
            key=f"{key_prefix}__uploader",
        )

        # ------------------------------------------------------------
        # upload extension allowed set
        # ------------------------------------------------------------
        if upload_types:
            allowed_suffixes = {
                f".{str(x).lower().lstrip('.')}"
                for x in upload_types
            }
        else:
            allowed_suffixes = set()

        # ------------------------------------------------------------
        # upload load button
        # ------------------------------------------------------------
        load_clicked = st.button(
            "📥 選択ファイルを読み込む",
            disabled=(uploaded is None),
            key=f"{key_prefix}__load_upload",
        )

        # ------------------------------------------------------------
        # upload load
        # ------------------------------------------------------------
        if load_clicked:
            if uploaded is None:
                st.warning(
                    "ファイルを選択してください。"
                )

            else:
                file_name = (
                    uploaded.name
                    or "uploaded_file"
                )

                suffix = _suffix_of(file_name)

                # ------------------------------------------------------------
                # extension check
                # ------------------------------------------------------------
                if (
                    allowed_suffixes
                    and suffix not in allowed_suffixes
                ):
                    st.error(
                        "このページで使えるファイルは "
                        + " / ".join(
                            sorted(allowed_suffixes)
                        )
                        + " だけです。"
                    )

                    st.info(
                        f"選択されたファイル：{file_name}\n\n"
                        "このページで指定された形式の"
                        "ファイルを選び直してください。"
                    )

                    st.session_state[k_text] = ""
                    st.session_state[k_bytes] = b""
                    st.session_state[k_name] = ""
                    st.session_state[k_kind] = ""
                    st.session_state[k_confirmed] = False

                else:
                    data = uploaded.getvalue()

                    if not data:
                        st.warning(
                            "ファイルの読み込みに失敗しました（0バイト）。"
                        )

                        st.session_state[k_confirmed] = False

                    else:
                        st.session_state[k_text] = ""

                        st.session_state[k_bytes] = data

                        st.session_state[k_name] = file_name

                        st.session_state[k_kind] = (
                            suffix.lstrip(".")
                        )

                        st.session_state[k_confirmed] = True

                        st.success(
                            f"✅ ファイルを読み込みました：{file_name}"
                        )

    # ============================================================
    # inbox
    # ============================================================
    elif source == "inbox":
        picked: InboxPickedFile | None = (
            render_inbox_file_picker_no_toggle(
                projects_root=projects_root,
                user_sub=user_sub,
                key_prefix=f"{key_prefix}__inbox_picker",
                page_size=inbox_page_size,
                kinds=inbox_kinds,
                show_kind_in_label=True,
                show_added_at_in_label=True,
            )
        )

        # ------------------------------------------------------------
        # inbox extension allowed set
        # ------------------------------------------------------------
        if inbox_extensions:
            allowed_inbox_suffixes = {
                f".{str(x).lower().lstrip('.')}"
                for x in inbox_extensions
            }

        else:
            allowed_inbox_suffixes = set()

        # ------------------------------------------------------------
        # inbox picked file
        # ------------------------------------------------------------
        if picked is not None:
            file_name = (
                picked.original_name
                or "inbox_file"
            )

            suffix = _suffix_of(file_name)

            # ------------------------------------------------------------
            # extension check
            # ------------------------------------------------------------
            if (
                allowed_inbox_suffixes
                and suffix not in allowed_inbox_suffixes
            ):
                st.error(
                    "このページで使える Inbox ファイルは "
                    + " / ".join(
                        sorted(
                            allowed_inbox_suffixes
                        )
                    )
                    + " だけです。"
                )

                st.info(
                    f"選択されたファイル：{file_name}\n\n"
                    "このページで指定された形式の"
                    "ファイルを選び直してください。"
                )

                st.session_state[k_text] = ""
                st.session_state[k_bytes] = b""
                st.session_state[k_name] = ""
                st.session_state[k_kind] = ""
                st.session_state[k_confirmed] = False

            else:
                st.session_state[k_bytes] = (
                    picked.data_bytes or b""
                )

                st.session_state[k_name] = file_name

                st.session_state[k_kind] = (
                    picked.kind
                    or suffix.lstrip(".")
                )

                st.session_state[k_text] = ""

                st.session_state[k_confirmed] = True

                st.success(
                    f"✅ Inbox から読み込みました：{file_name}"
                )

    # ============================================================
    # internal
    # ============================================================
    elif source == "internal":
        if internal_renderer is None:
            st.error(
                "internal_renderer が指定されていません。"
            )

            return empty_input_source_result()

        result = internal_renderer()

        st.session_state[k_text] = (
            result.text or ""
        )

        st.session_state[k_bytes] = (
            result.data_bytes or b""
        )

        st.session_state[k_name] = (
            result.file_name or ""
        )

        st.session_state[k_kind] = (
            result.kind or ""
        )

        st.session_state[k_confirmed] = bool(
            result.confirmed
        )

        return InputSourceResult(
            source_type="internal",
            confirmed=bool(result.confirmed),
            text=result.text or "",
            data_bytes=result.data_bytes or b"",
            file_name=result.file_name or "",
            suffix=_suffix_of(
                result.file_name or ""
            ),
            kind=result.kind or "",
        )

    # ============================================================
    # sample
    # ============================================================
    elif source == "sample":
        if sample_renderer is None:
            st.error(
                "sample_renderer が指定されていません。"
            )

            return empty_input_source_result()

        result = sample_renderer()

        st.session_state[k_text] = (
            result.text or ""
        )

        st.session_state[k_bytes] = (
            result.data_bytes or b""
        )

        st.session_state[k_name] = (
            result.file_name or ""
        )

        st.session_state[k_kind] = (
            result.kind or ""
        )

        st.session_state[k_confirmed] = bool(
            result.confirmed
        )

        return InputSourceResult(
            source_type="sample",
            confirmed=bool(result.confirmed),
            text=result.text or "",
            data_bytes=result.data_bytes or b"",
            file_name=result.file_name or "",
            suffix=_suffix_of(
                result.file_name or ""
            ),
            kind=result.kind or "",
        )


    # ============================================================
    # invalid source
    # ============================================================
    else:
        st.error(
            f"未対応の入力方式です: {source}"
        )

        return empty_input_source_result()

    # ============================================================
    # result
    # ============================================================
    file_name = str(
        st.session_state.get(k_name) or ""
    )

    return InputSourceResult(
        source_type=str(source),
        confirmed=bool(
            st.session_state.get(k_confirmed)
        ),
        text=str(
            st.session_state.get(k_text) or ""
        ),
        data_bytes=(
            st.session_state.get(k_bytes, b"")
            or b""
        ),
        file_name=file_name,
        suffix=_suffix_of(file_name),
        kind=str(
            st.session_state.get(k_kind) or ""
        ),
    )