# -*- coding: utf-8 -*-
# common_lib/ui/page_processing_history.py
# ============================================================
# PDFページ処理履歴 表示UI
# ============================================================

from __future__ import annotations

from typing import Any

import streamlit as st


def _display_value(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "-"


def _replacement_text(replacements: list[Any]) -> str:
    parts: list[str] = []

    for row in replacements:
        if not isinstance(row, dict):
            continue

        target = str(row.get("target", "") or "")
        count = int(row.get("count", 0) or 0)

        source_counts = row.get("source_counts")
        if isinstance(source_counts, dict):
            for source, source_count in source_counts.items():
                parts.append(
                    f"「{source}」→「{target}」 "
                    f"{int(source_count or 0):,}文字"
                )
            continue

        source = str(row.get("source", "") or "")
        if source:
            parts.append(
                f"「{source}」→「{target}」 {count:,}文字"
            )

    return " ／ ".join(parts) if parts else "-"


def render_page_processing_history(
    history: dict[str, Any],
) -> None:
    page_no = int(history.get("page_no", 0) or 0)

    st.markdown("---")
    st.subheader(
        f"表示ページの処理履歴　PDF Page {page_no}"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "ページ種別",
            _display_value(history.get("page_kind")),
        )

    with c2:
        st.metric(
            "白紙認定",
            "あり" if history.get("blank_page") else "なし",
        )

    with c3:
        st.metric(
            "通常OCR",
            "済み" if history.get("ocr_done") else "未実施",
        )

    with c4:
        st.metric(
            "OCR方式",
            _display_value(history.get("ocr_method")),
        )

    ocr_at = _display_value(history.get("ocr_at"))
    ocr_by = _display_value(history.get("ocr_by"))

    if history.get("ocr_done"):
        st.caption(
            f"OCR日時：{ocr_at}　／　実行者：{ocr_by}"
        )

    hallucination = list(
        history.get("hallucination", []) or []
    )

    with st.expander(
        f"ハルシネーション履歴（{len(hallucination):,}件）",
        expanded=False,
    ):
        if not hallucination:
            st.caption("履歴なし")
        else:
            for row in hallucination:
                status = (
                    row.get("review_status")
                    or row.get("action")
                    or "suspected"
                )
                st.markdown(
                    f"- {_display_value(row.get('time'))}　"
                    f"**{status}**　"
                    f"model={_display_value(row.get('model'))}　"
                    f"実行者={_display_value(row.get('user'))}"
                )
                if row.get("reason"):
                    st.caption(str(row["reason"]))

    replacements = list(
        history.get("abnormal_char_replacement", []) or []
    )

    with st.expander(
        f"異常文字置換履歴（{len(replacements):,}件）",
        expanded=False,
    ):
        if not replacements:
            st.caption("履歴なし")
        else:
            for row in replacements:
                st.markdown(
                    f"- {_display_value(row.get('time'))}　"
                    f"{int(row.get('replacement_count', 0) or 0):,}文字　"
                    f"実行者={_display_value(row.get('user'))}"
                )
                st.caption(
                    _replacement_text(
                        list(row.get("replacements", []) or [])
                    )
                )

    abnormal_ocr = list(
        history.get("abnormal_text_processing", []) or []
    )

    with st.expander(
        f"異常文字OCR・本文処理履歴（{len(abnormal_ocr):,}件）",
        expanded=False,
    ):
        if not abnormal_ocr:
            st.caption("履歴なし")
        else:
            for row in abnormal_ocr:
                st.markdown(
                    f"- {_display_value(row.get('time'))}　"
                    f"**{_display_value(row.get('action'))}**　"
                    f"model={_display_value(row.get('model'))}　"
                    f"実行者={_display_value(row.get('user'))}"
                )