# -*- coding: utf-8 -*-
# common_lib/ragbot/evidence_preview.py
# ============================================================
# RAG根拠報告書プレビュー
#
# 機能：
# - RAGで参照された報告書PDFをページ単位で表示する
# - PDFページに対応するRAG入力元テキストを表示する
# - PDFとテキストのページ移動を同期する
# - 根拠チャンクに該当するテキストをハイライトする
#
# 方針：
# - rag_builder_app / project_hub_app など特定appへ依存しない
# - ページ対応テキストは report_*_pages.json を正本とする
# - source_text_kind に応じて clean / raw を自動選択する
# - pages JSONがない場合は曖昧な40行分割へfallbackしない
# - chunk生成時と同じ normalize_text_for_chunking() を使用する
# - 類似一致・曖昧一致は行わない
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================

import hashlib
import html
import json
from pathlib import Path

# ============================================================
# imports（3rd party）
# ============================================================

import streamlit as st

# ============================================================
# common_lib（report）
# ============================================================

from common_lib.project_master import (
    get_report_pdf_path,
)

from common_lib.project_master.report_pages_v2_ops import (
    read_report_pages,
)

# ============================================================
# common_lib（preview）
# ============================================================

from common_lib.preview.file_preview import (
    get_pdf_page_count,
    render_pdf_page_only,
)

# ============================================================
# common_lib（chunk正本）
# ============================================================

from common_lib.rag_ingest.chunk_ops import (
    normalize_text_for_chunking,
    split_text_into_sentence_like_units,
)


# ============================================================
# constants
# ============================================================

PDF_PREVIEW_WIDTH = 650
TEXT_PREVIEW_HEIGHT = 850


# ============================================================
# session_state key
# ============================================================

def _state_key(
    state_prefix: str,
    name: str,
) -> str:
    # ------------------------------------------------------------
    # 呼び出し元ごとのSession Stateキー
    # ------------------------------------------------------------

    prefix = str(
        state_prefix
        or "evidence_preview"
    ).strip()

    return (
        f"{prefix}"
        f"__evidence_preview__"
        f"{name}"
    )


# ============================================================
# pages JSON
# ============================================================

def _read_pages_json(
    path: Path,
) -> dict[int, str]:
    # ------------------------------------------------------------
    # report_*_pages.json
    #
    # {
    #     "pages": [
    #         {
    #             "page": 1,
    #             "text": "..."
    #         }
    #     ]
    # }
    #
    # を
    #
    # {
    #     1: "...",
    # }
    #
    # に変換する
    # ------------------------------------------------------------

    if not path.exists():
        return {}

    data = json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )

    if isinstance(
        data,
        dict,
    ):
        pages = list(
            data.get(
                "pages",
                [],
            )
            or []
        )

    elif isinstance(
        data,
        list,
    ):
        pages = list(
            data
        )

    else:
        pages = []

    out: dict[int, str] = {}

    for row in pages:

        if not isinstance(
            row,
            dict,
        ):
            continue

        try:
            page_no = int(
                row.get(
                    "page",
                    row.get(
                        "page_no",
                        0,
                    ),
                )
                or 0
            )
        except Exception:
            page_no = 0

        if page_no <= 0:
            continue

        out[
            page_no
        ] = str(
            row.get(
                "text",
                "",
            )
            or ""
        )

    return out




# ============================================================
# text match helpers
# ============================================================

def _merge_ranges(
    ranges: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    # ------------------------------------------------------------
    # 重複・接続している文字範囲をまとめる
    # ------------------------------------------------------------

    if not ranges:
        return []

    ordered = sorted(
        (
            (
                int(start),
                int(end),
            )
            for start, end in ranges
            if int(end) > int(start)
        ),
        key=lambda x: (
            x[0],
            x[1],
        ),
    )

    if not ordered:
        return []

    merged: list[
        tuple[int, int]
    ] = [
        ordered[0]
    ]

    for start, end in ordered[1:]:

        prev_start, prev_end = (
            merged[-1]
        )

        if start <= prev_end:

            merged[-1] = (
                prev_start,
                max(
                    prev_end,
                    end,
                ),
            )

        else:

            merged.append(
                (
                    start,
                    end,
                )
            )

    return merged


def _build_evidence_candidates(
    evidence_text: str,
) -> list[str]:
    # ------------------------------------------------------------
    # チャンク本文からページ内検索候補を作る
    #
    # chunk生成では文単位を改行で結合しているため，
    # まず改行単位を優先する．
    #
    # さらに文単位分割も候補へ加える．
    # ------------------------------------------------------------

    normalized = normalize_text_for_chunking(
        evidence_text
    )

    if not normalized:
        return []

    candidates: list[str] = []

    # ------------------------------------------------------------
    # 1. 改行単位
    # ------------------------------------------------------------

    for line in normalized.splitlines():

        text = str(
            line
            or ""
        ).strip()

        if text:
            candidates.append(
                text
            )

    # ------------------------------------------------------------
    # 2. chunk正本と同じ文単位
    # ------------------------------------------------------------

    for unit in (
        split_text_into_sentence_like_units(
            normalized
        )
    ):

        text = str(
            unit
            or ""
        ).strip()

        if text:
            candidates.append(
                text
            )

    # ------------------------------------------------------------
    # 重複除去
    # ------------------------------------------------------------

    unique: list[str] = []
    seen: set[str] = set()

    for text in candidates:

        if text in seen:
            continue

        seen.add(
            text
        )

        unique.append(
            text
        )

    # ------------------------------------------------------------
    # 長い候補を優先
    # ------------------------------------------------------------

    unique.sort(
        key=len,
        reverse=True,
    )

    return unique


def _find_evidence_ranges(
    *,
    page_text: str,
    evidence_text: str,
) -> tuple[
    str,
    list[tuple[int, int]],
    str,
]:
    # ------------------------------------------------------------
    # 現在ページ中の根拠範囲を探す
    #
    # 戻り値：
    # - 表示用の正規化済みページ本文
    # - ハイライト範囲
    # - match種別
    #
    # match種別：
    # - exact
    # - partial
    # - none
    # ------------------------------------------------------------

    normalized_page = (
        normalize_text_for_chunking(
            page_text
        )
    )

    normalized_evidence = (
        normalize_text_for_chunking(
            evidence_text
        )
    )

    if (
        not normalized_page
        or not normalized_evidence
    ):
        return (
            normalized_page,
            [],
            "none",
        )

    # ------------------------------------------------------------
    # STEP 1
    # チャンク全文が現在ページ内に完全一致するか
    # ------------------------------------------------------------

    exact_pos = normalized_page.find(
        normalized_evidence
    )

    if exact_pos >= 0:

        return (
            normalized_page,
            [
                (
                    exact_pos,
                    exact_pos
                    + len(
                        normalized_evidence
                    ),
                )
            ],
            "exact",
        )

    # ------------------------------------------------------------
    # STEP 2
    # 複数ページchunkを想定し，
    # chunkを構成する部分文字列を現在ページから探す
    #
    # 曖昧一致はしない．
    # ------------------------------------------------------------

    candidates = (
        _build_evidence_candidates(
            normalized_evidence
        )
    )

    ranges: list[
        tuple[int, int]
    ] = []

    for candidate in candidates:

        # --------------------------------------------------------
        # 極端に短い断片は誤一致防止のため使用しない
        #
        # 句読点は文字数に含めない。
        #
        # 例：
        # - 「ている。」   → 実質3文字 → 除外
        # - 「栃木県」     → 3文字     → 除外
        # - 「那須高原」   → 4文字     → 採用
        # - 「自然学校」   → 4文字     → 採用
        # - 「連絡協議会」 → 5文字     → 採用
        # --------------------------------------------------------

        effective_candidate = candidate.rstrip(
            "。！？!?、，．,. "
        )

        if len(
            effective_candidate
        ) < 4:
            continue

        search_pos = 0

        while True:

            pos = normalized_page.find(
                candidate,
                search_pos,
            )

            if pos < 0:
                break

            ranges.append(
                (
                    pos,
                    pos
                    + len(
                        candidate
                    ),
                )
            )

            search_pos = (
                pos
                + len(
                    candidate
                )
            )

    merged = _merge_ranges(
        ranges
    )

    if merged:

        return (
            normalized_page,
            merged,
            "partial",
        )

    return (
        normalized_page,
        [],
        "none",
    )


# ============================================================
# highlight HTML
# ============================================================
def _build_highlight_html(
    *,
    text: str,
    ranges: list[tuple[int, int]],
    font_size: int = 15,
) -> str:
    # ------------------------------------------------------------
    # テキストの該当範囲をmarkタグで囲む
    # ------------------------------------------------------------

    if not ranges:

        safe_text = html.escape(
            text
        )

        return (
            "<pre "
            "style='"
            "white-space:pre-wrap;"
            "word-break:break-word;"
            "font-family:monospace;"
            f"font-size:{int(font_size)}px;"
            "line-height:1.6;"
            "margin:0;"
            "'>"
            f"{safe_text}"
            "</pre>"
        )

    parts: list[str] = []

    cursor = 0

    for start, end in ranges:

        start_safe = max(
            0,
            min(
                int(start),
                len(text),
            ),
        )

        end_safe = max(
            start_safe,
            min(
                int(end),
                len(text),
            ),
        )

        if start_safe > cursor:

            parts.append(
                html.escape(
                    text[
                        cursor:start_safe
                    ]
                )
            )

        parts.append(
            "<mark "
            "style='"
            "background:#fff59d;"
            "padding:1px 0;"
            "'>"
            + html.escape(
                text[
                    start_safe:end_safe
                ]
            )
            + "</mark>"
        )

        cursor = end_safe

    if cursor < len(
        text
    ):

        parts.append(
            html.escape(
                text[
                    cursor:
                ]
            )
        )

    body = "".join(
        parts
    )

    return (
        "<pre "
        "style='"
        "white-space:pre-wrap;"
        "word-break:break-word;"
        "font-family:monospace;"
        f"font-size:{int(font_size)}px;"
        "line-height:1.6;"
        "margin:0;"
        "'>"
        f"{body}"
        "</pre>"
    )

# ============================================================
# selection signature
# ============================================================

def _build_selection_signature(
    *,
    project_year: int,
    project_no: str,
    page_start: int,
    page_end: int,
    evidence_text: str,
) -> str:
    # ------------------------------------------------------------
    # 根拠切替判定用signature
    # ------------------------------------------------------------

    evidence_hash = hashlib.sha256(
        str(
            evidence_text
            or ""
        ).encode(
            "utf-8"
        )
    ).hexdigest()[
        :16
    ]

    return (
        f"{int(project_year)}"
        f"/{str(project_no).zfill(3)}"
        f"/{int(page_start)}"
        f"-{int(page_end)}"
        f"/{evidence_hash}"
    )


# ============================================================
# state init / evidence change
# ============================================================

def _init_preview_state(
    *,
    state_prefix: str,
    page_start: int,
    selection_signature: str,
) -> None:
    # ------------------------------------------------------------
    # 根拠が変わったときだけpage_startへ移動する
    # ------------------------------------------------------------

    sig_key = _state_key(
        state_prefix,
        "selection_signature",
    )

    page_key = _state_key(
        state_prefix,
        "page",
    )

    page_input_key = _state_key(
        state_prefix,
        "page_input",
    )

    current_sig = str(
        st.session_state.get(
            sig_key,
            "",
        )
        or ""
    )

    if (
        current_sig
        != selection_signature
    ):

        initial_page = max(
            1,
            int(
                page_start
            ),
        )

        st.session_state[
            sig_key
        ] = selection_signature

        st.session_state[
            page_key
        ] = initial_page

        st.session_state[
            page_input_key
        ] = initial_page

        return

    st.session_state.setdefault(
        page_key,
        max(
            1,
            int(
                page_start
            ),
        ),
    )

    st.session_state.setdefault(
        page_input_key,
        int(
            st.session_state[
                page_key
            ]
        ),
    )


# ============================================================
# page navigation callbacks
# ============================================================

def _set_page(
    *,
    state_prefix: str,
    page_no: int,
    total_pages: int,
) -> None:

    page_safe = max(
        1,
        min(
            int(
                page_no
            ),
            max(
                1,
                int(
                    total_pages
                ),
            ),
        ),
    )

    st.session_state[
        _state_key(
            state_prefix,
            "page",
        )
    ] = page_safe

    st.session_state[
        _state_key(
            state_prefix,
            "page_input",
        )
    ] = page_safe


def _go_previous(
    state_prefix: str,
    total_pages: int,
) -> None:

    current = int(
        st.session_state.get(
            _state_key(
                state_prefix,
                "page",
            ),
            1,
        )
        or 1
    )

    _set_page(
        state_prefix=state_prefix,
        page_no=current - 1,
        total_pages=total_pages,
    )


def _go_next(
    state_prefix: str,
    total_pages: int,
) -> None:

    current = int(
        st.session_state.get(
            _state_key(
                state_prefix,
                "page",
            ),
            1,
        )
        or 1
    )

    _set_page(
        state_prefix=state_prefix,
        page_no=current + 1,
        total_pages=total_pages,
    )


def _page_input_changed(
    state_prefix: str,
    total_pages: int,
) -> None:

    page_input = int(
        st.session_state.get(
            _state_key(
                state_prefix,
                "page_input",
            ),
            1,
        )
        or 1
    )

    _set_page(
        state_prefix=state_prefix,
        page_no=page_input,
        total_pages=total_pages,
    )


# ============================================================
# page navigation UI
# ============================================================

def _render_page_navigation(
    *,
    state_prefix: str,
    total_pages: int,
) -> int:

    page_key = _state_key(
        state_prefix,
        "page",
    )

    page_input_key = _state_key(
        state_prefix,
        "page_input",
    )

    current_page = int(
        st.session_state.get(
            page_key,
            1,
        )
        or 1
    )

    current_page = max(
        1,
        min(
            current_page,
            int(
                total_pages
            ),
        ),
    )

    st.session_state[
        page_key
    ] = current_page

    if (
        page_input_key
        not in st.session_state
    ):
        st.session_state[
            page_input_key
        ] = current_page

    col_prev, col_next, col_input, col_space, col_info = (
        st.columns(
            [
                1,
                1,
                1,
                1,
                2,
            ]
        )
    )

    with col_prev:

        st.button(
            "⬅ 前へ",
            disabled=(
                current_page
                <= 1
            ),
            key=_state_key(
                state_prefix,
                "previous_button",
            ),
            on_click=_go_previous,
            args=(
                state_prefix,
                int(
                    total_pages
                ),
            ),
        )

    with col_next:

        st.button(
            "次へ ➡",
            disabled=(
                current_page
                >= int(
                    total_pages
                )
            ),
            key=_state_key(
                state_prefix,
                "next_button",
            ),
            on_click=_go_next,
            args=(
                state_prefix,
                int(
                    total_pages
                ),
            ),
        )

    with col_input:

        st.number_input(
            "ページ番号",
            min_value=1,
            max_value=max(
                1,
                int(
                    total_pages
                ),
            ),
            step=1,
            key=page_input_key,
            label_visibility="collapsed",
            on_change=_page_input_changed,
            args=(
                state_prefix,
                int(
                    total_pages
                ),
            ),
        )

    current_page = int(
        st.session_state.get(
            page_key,
            current_page,
        )
        or current_page
    )

    with col_info:

        st.write(
            f"Page: "
            f"{current_page} / "
            f"{int(total_pages)}"
        )

    return current_page


# ============================================================
# public
# ============================================================

def render_evidence_report_preview(
    *,
    projects_root: Path,
    project_year: int,
    project_no: str,
    source_text_kind: str,
    evidence_text: str,
    page_start: int,
    page_end: int,
    state_prefix: str,
    pdf_width: int = PDF_PREVIEW_WIDTH,
    text_height: int = TEXT_PREVIEW_HEIGHT,
    text_font_size: int = 15,
) -> None:
    # ------------------------------------------------------------
    # RAG根拠用
    #
    # 左：
    #   PDF
    #
    # 右：
    #   RAG入力元のページ対応テキスト
    #   ＋根拠ハイライト
    #
    # PDFとテキストは同じpage番号を使う
    # ------------------------------------------------------------

    year = int(
        project_year
    )

    pno = str(
        project_no
    ).zfill(
        3
    )

    start_page = max(
        1,
        int(
            page_start
            or 1
        ),
    )

    end_page = max(
        start_page,
        int(
            page_end
            or start_page
        ),
    )

    # ------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------

    pdf_path = get_report_pdf_path(
        projects_root,
        project_year=year,
        project_no=pno,
        role="main",
    )

    if (
        pdf_path is None
        or not pdf_path.exists()
    ):

        st.error(
            "報告書PDFが存在しません．"
        )

        return

    total_pages = get_pdf_page_count(
        Path(
            pdf_path
        )
    )

    if (
        total_pages is None
        or int(
            total_pages
        ) <= 0
    ):

        st.error(
            "PDFのページ数を"
            "取得できませんでした．"
        )

        return


    # ------------------------------------------------------------
    # report_pages.json
    # ------------------------------------------------------------
    try:
        payload = read_report_pages(
            Path(projects_root),
            project_year=year,
            project_no=pno,
        )
    except Exception as exc:
        st.error(
            "report_pages.json の"
            f"読み込みに失敗しました：{exc}"
        )
        return

    pages_map: dict[int, str] = {}

    for row in payload.get("pages", []):
        if not isinstance(row, dict):
            continue

        try:
            page_no = int(row.get("page_no", 0) or 0)
        except Exception:
            page_no = 0

        if page_no <= 0:
            continue

        pages_map[page_no] = str(
            row.get("text", "") or ""
        )

    if not pages_map:
        st.error(
            "report_pages.json にページ情報がありません．"
        )
        return
        

    # ------------------------------------------------------------
    # 根拠切替時の初期ページ
    # ------------------------------------------------------------

    selection_signature = (
        _build_selection_signature(
            project_year=year,
            project_no=pno,
            page_start=start_page,
            page_end=end_page,
            evidence_text=evidence_text,
        )
    )

    _init_preview_state(
        state_prefix=state_prefix,
        page_start=start_page,
        selection_signature=selection_signature,
    )

    # ------------------------------------------------------------
    # page navigation
    # ------------------------------------------------------------

    selected_page = (
        _render_page_navigation(
            state_prefix=state_prefix,
            total_pages=int(
                total_pages
            ),
        )
    )

    # ------------------------------------------------------------
    # 根拠ページ範囲
    # ------------------------------------------------------------

    if (
        start_page
        == end_page
    ):

        evidence_page_caption = (
            f"根拠ページ: "
            f"{start_page}"
        )

    else:

        evidence_page_caption = (
            f"根拠ページ: "
            f"{start_page}"
            f"–{end_page}"
        )

    st.caption(
        evidence_page_caption
        + "　｜　"
        + "ページ別テキスト: report_pages.json"
    )

    # ------------------------------------------------------------
    # 2 columns
    # ------------------------------------------------------------

    left, right = st.columns(
        [
            1,
            1,
        ]
    )

    # ============================================================
    # left：PDF
    # ============================================================

    with left:

        st.markdown(
            "#### PDF"
        )

        render_pdf_page_only(
            file_path=Path(
                pdf_path
            ),
            page_no=int(
                selected_page
            ),
            max_width=int(
                pdf_width
            ),
        )

    # ============================================================
    # right：page text
    # ============================================================

    with right:

        st.markdown(
            "#### ページ対応テキスト"
        )

        text_font_size = st.slider(
            "文字サイズ",
            min_value=6,
            max_value=18,
            value=10,
            step=1,
            key=_state_key(
                state_prefix,
                "text_font_size",
            ),
        )

        raw_page_text = str(
            pages_map.get(
                int(
                    selected_page
                ),
                "",
            )
            or ""
        )

        if not raw_page_text.strip():

            st.info(
                "このページには"
                "表示できるテキストが"
                "ありません．"
            )

            return

        # --------------------------------------------------------
        # 根拠範囲外
        # --------------------------------------------------------

        if not (
            start_page
            <= int(
                selected_page
            )
            <= end_page
        ):

            display_text = (
                normalize_text_for_chunking(
                    raw_page_text
                )
            )

            highlight_ranges: list[
                tuple[int, int]
            ] = []

            match_kind = (
                "outside"
            )

        else:

            (
                display_text,
                highlight_ranges,
                match_kind,
            ) = _find_evidence_ranges(
                page_text=raw_page_text,
                evidence_text=evidence_text,
            )

        # --------------------------------------------------------
        # match状態
        # --------------------------------------------------------

        if match_kind == "exact":

            st.caption(
                "根拠チャンク全文が"
                "このページで完全一致しました．"
            )

        elif match_kind == "partial":

            st.caption(
                "複数ページ根拠のうち，"
                "このページに含まれる"
                "一致部分を表示しています．"
            )

        elif match_kind == "none":

            st.warning(
                "このページは根拠ページ範囲内ですが，"
                "根拠本文との完全一致部分を"
                "特定できませんでした．"
            )

        elif match_kind == "outside":

            st.caption(
                "現在のページは"
                "選択中の根拠ページ範囲外です．"
            )

        # --------------------------------------------------------
        # HTML
        # --------------------------------------------------------

        highlighted_html = (
            _build_highlight_html(
                text=display_text,
                ranges=highlight_ranges,
                font_size=text_font_size,
            )
        )

        html_content = (
            "<html>"
            "<body style='"
            "margin:0;"
            "padding:12px;"
            "background:white;"
            "'>"
            f"{highlighted_html}"
            "</body>"
            "</html>"
        )

        st.components.v1.html(
            html_content,
            height=int(
                text_height
            ),
            scrolling=True,
        )