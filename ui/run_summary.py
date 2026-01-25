# common_lib/ui/run_summary.py
# =============================================================================
# run summary UI（Streamlit）
# - タイトル無しで「直近ラン」をコンパクト表示（縦を増やさない）
# - ai_runs.db（get_run）を正本として start/end/elapsed/status を表示
# - 費用・tokens は「渡されたら表示」（計算しない / 推計しない）
# =============================================================================

from __future__ import annotations

from typing import Any, Optional


def render_run_summary_compact(
    *,
    projects_root: Any,
    run_id: str,
    model: str,
    in_tokens: Optional[int] = None,
    out_tokens: Optional[int] = None,
    cost: Any = None,
    note: str = "",
    show_divider: bool = True,
) -> None:
    """
    タイトル無しのコンパクト表示（縦を増やさない）。

    表示：
    - 1行目：費用(JPY/USD) / tokens(in/out) / elapsed（metrics）
    - 2行目：model / start / end / status / run_id（caption 1行）
    - note（あれば caption）

    方針：
    - cost は計算しない（cost.usd / cost.jpy を getattr で読むだけ）
    - tokens は推計しない（渡された値だけ）
    - run は ai_runs.db を正本として get_run で取得
    """
    try:
        import streamlit as st  # type: ignore
    except Exception as e:
        raise RuntimeError("render_run_summary_compact は Streamlit 環境でのみ利用できます") from e

    from common_lib.busy import get_run
    from common_lib.ui.time_format import format_jst_iso_ja

    rid = str(run_id or "").strip()
    if not rid:
        if show_divider:
            st.divider()
        st.info("まだ実行がありません。")
        return

    row = get_run(projects_root=projects_root, run_id=rid)
    if not row:
        if show_divider:
            st.divider()
        st.caption(f"ai_runs.db に run が見つかりません（run_id: {rid}）")
        return

    if show_divider:
        st.divider()

    # ---- caption の行間を詰める（このUIだけ）----
    st.markdown(
        """
        <style>
        .stCaption {
            margin-top: 0.10rem !important;
            margin-bottom: 0.10rem !important;
            line-height: 1.20 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
        

    # ---- time（ai_runs.db 正本）----
    started_at = row.get("started_at") or "—"
    finished_at = row.get("finished_at") or "—"
    elapsed_ms = row.get("elapsed_ms")

    elapsed_sec = None
    try:
        if elapsed_ms is not None:
            elapsed_sec = float(elapsed_ms) / 1000.0
    except Exception:
        elapsed_sec = None

    # ---- cost（計算しない：あれば読むだけ）----
    jpy = getattr(cost, "jpy", None) if cost is not None else None
    usd = getattr(cost, "usd", None) if cost is not None else None

     # ---- 表示（B：タイトル無し・2行でコンパクト）----
    jpy_str = f"¥{float(jpy):.2f}" if isinstance(jpy, (int, float)) else "—"
    usd_str = f"${float(usd):.6f}" if isinstance(usd, (int, float)) else "—"

    tok_str = "—"
    if isinstance(in_tokens, int) and isinstance(out_tokens, int):
        tok_str = f"in={in_tokens} out={out_tokens}"

    el_str = f"{elapsed_sec:.2f}s" if isinstance(elapsed_sec, (int, float)) else "—"

    # 1行目：主要サマリ（省略されない）
    st.write(f"**費用** {jpy_str} / {usd_str}　　**トークン数** {tok_str}　　**AI使用時間** {el_str}")

    # 2行目：メタ（短く）
    st.caption(f"モデル {model or '—'}・状態 {row.get('status')}")
    st.caption(f"開始 {format_jst_iso_ja(str(started_at))}・終了 {format_jst_iso_ja(str(finished_at))}")
   
    n = (note or "").strip()
    if n:
        st.caption(f"run_id {rid}　　note: {n}")
    else:
        st.caption(f"run_id {rid}")


   

# ============================================================
# 内部ヘルパ（run summary 共通）
# ============================================================
def _apply_caption_compact_style() -> None:
    """
    caption の行間を詰める（このUIだけ）
    """
    import streamlit as st  # type: ignore

    st.markdown(
        "<style>"
        ".stCaption{margin-top:0.10rem !important;margin-bottom:0.10rem !important;line-height:1.20 !important;}"
        "</style>",
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# row から audio_seconds を拾う（推計しない）
# ------------------------------------------------------------
def _pick_audio_sec_from_row(row: dict) -> Optional[float]:
    """
    ai_runs.db の row から audio_seconds を拾う。
    - 直接カラムがあればそれを優先
    - 無ければ meta から拾う（audio_sec / audio_seconds / total_audio_sec）
    """
    # 直接カラム
    v = row.get("audio_sec")
    if isinstance(v, (int, float)):
        return float(v)

    # meta（dict or json文字列）を試す
    meta = row.get("meta")
    if isinstance(meta, str):
        try:
            import json
            meta = json.loads(meta)
        except Exception:
            meta = None

    if isinstance(meta, dict):
        for key in ("audio_sec", "audio_seconds", "total_audio_sec"):
            vv = meta.get(key)
            if isinstance(vv, (int, float)):
                return float(vv)

    return None


# ------------------------------------------------------------
# row から cost を拾う（推計しない）
# ------------------------------------------------------------
def _pick_cost_from_row(row: dict) -> Any:
    """
    ai_runs.db の row から cost を拾う（推計しない）。

    優先順位：
    1) cost_usd / cost_jpy（あなたのDBの実カラム）
    2) total_usd / total_jpy（別実装の可能性に備える）
    3) total_cost_usd / total_cost_jpy（念のため）

    戻り値：
    - 表示用に .usd / .jpy を持つ簡易オブジェクト（None なら拾えなかった）
    """
    # ------------------------------------------------------------
    # 1) cost_usd / cost_jpy
    # ------------------------------------------------------------
    usd = row.get("cost_usd")
    jpy = row.get("cost_jpy")
    if isinstance(usd, (int, float)) and isinstance(jpy, (int, float)):
        from types import SimpleNamespace
        return SimpleNamespace(usd=float(usd), jpy=float(jpy))

    # ------------------------------------------------------------
    # 2) total_usd / total_jpy
    # ------------------------------------------------------------
    usd = row.get("total_usd")
    jpy = row.get("total_jpy")
    if isinstance(usd, (int, float)) and isinstance(jpy, (int, float)):
        from types import SimpleNamespace
        return SimpleNamespace(usd=float(usd), jpy=float(jpy))

    # ------------------------------------------------------------
    # 3) total_cost_usd / total_cost_jpy
    # ------------------------------------------------------------
    usd = row.get("total_cost_usd")
    jpy = row.get("total_cost_jpy")
    if isinstance(usd, (int, float)) and isinstance(jpy, (int, float)):
        from types import SimpleNamespace
        return SimpleNamespace(usd=float(usd), jpy=float(jpy))

    return None

# ============================================================
# run summary（Image）
# ============================================================
def render_run_summary_image_compact(
    *,
    projects_root: Any,
    run_id: str,
    model: str,
    cost: Any = None,
    note: str = "",
    show_divider: bool = True,
) -> None:
    """
    Image 専用のコンパクト実行サマリ（縦を増やさない）。

    表示：
    - 1行目：費用(JPY/USD) / AI使用時間
    - 2行目：model / status
    - 3行目：start / end
    - 4行目：run_id（note があれば同一行で併記）

    方針：
    - cost は計算しない（渡されたら getattr で読む / 無ければ row から拾う）
    - run は ai_runs.db を正本として get_run で取得
    - tokens は扱わない（画像は基本取れない前提）
    """
    try:
        import streamlit as st  # type: ignore
    except Exception as e:
        raise RuntimeError("render_run_summary_image_compact は Streamlit 環境でのみ利用できます") from e

    from common_lib.busy import get_run
    from common_lib.ui.time_format import format_jst_iso_ja

    rid = str(run_id or "").strip()
    if not rid:
        if show_divider:
            st.divider()
        st.info("まだ実行がありません。")
        return

    row = get_run(projects_root=projects_root, run_id=rid)
    if not row:
        if show_divider:
            st.divider()
        st.caption(f"ai_runs.db に run が見つかりません（run_id: {rid}）")
        return

    if show_divider:
        st.divider()
    _apply_caption_compact_style()

    # ---- time（ai_runs.db 正本）----
    started_at = row.get("started_at") or "—"
    finished_at = row.get("finished_at") or "—"
    elapsed_ms = row.get("elapsed_ms")

    elapsed_sec: Optional[float] = None
    if isinstance(elapsed_ms, (int, float)):
        try:
            elapsed_sec = float(elapsed_ms) / 1000.0
        except Exception:
            elapsed_sec = None

    # ---- cost（ページから来なければ row から拾う：推計しない）----
    # if cost is None:
    #     cost = _pick_cost_from_row(row)

    # jpy = getattr(cost, "jpy", None) if cost is not None else None
    # usd = getattr(cost, "usd", None) if cost is not None else None

    # jpy_str = f"¥{float(jpy):.2f}" if isinstance(jpy, (int, float)) else "—"
    # usd_str = f"${float(usd):.6f}" if isinstance(usd, (int, float)) else "—"
    el_str = f"{float(elapsed_sec):.2f}s" if isinstance(elapsed_sec, (int, float)) else "—"

    # 1行目：主要サマリ
    #st.write(f"**費用** {jpy_str} / {usd_str}　　**AI使用時間** {el_str}")
    # 1行目：主要サマリ（image は費用を表示しない）
    st.write(f"**AI使用時間** {el_str}")


    # 2〜4行目：メタ（1行ずつ明示）
    st.caption(f"モデル {model or '—'}・状態 {row.get('status')}")
    st.caption(f"開始 {format_jst_iso_ja(str(started_at))}・終了 {format_jst_iso_ja(str(finished_at))}")

    n = (note or "").strip()
    if n:
        st.caption(f"run_id {rid}　　note: {n}")
    else:
        st.caption(f"run_id {rid}")


# ============================================================
# run summary（Transcribe）
# ============================================================
def render_run_summary_transcribe_compact(
    *,
    projects_root: Any,
    run_id: str,
    model: str,
    audio_sec: Optional[float] = None,
    cost: Any = None,
    note: str = "",
    show_divider: bool = True,
) -> None:
    """
    Transcribe 専用のコンパクト実行サマリ（text テンプレと同じ “顔”）。

    表示：
    - 1行目：音声時間 / 費用(JPY/USD) / AI使用時間
    - 2行目：model / status
    - 3行目：start / end
    - 4行目：run_id
    - note（あれば caption）
    """
    # ------------------------------------------------------------
    # Streamlit import
    # ------------------------------------------------------------
    try:
        import streamlit as st  # type: ignore
    except Exception as e:
        raise RuntimeError("render_run_summary_transcribe_compact は Streamlit 環境でのみ利用できます") from e

    # ------------------------------------------------------------
    # 正本：ai_runs.db
    # ------------------------------------------------------------
    from common_lib.busy import get_run
    from common_lib.ui.time_format import format_jst_iso_ja

    # ------------------------------------------------------------
    # ガード：run_id
    # ------------------------------------------------------------
    rid = str(run_id or "").strip()
    if not rid:
        if show_divider:
            st.divider()
        st.info("まだ実行がありません。")
        return

    row = get_run(projects_root=projects_root, run_id=rid)
    if not row:
        if show_divider:
            st.divider()
        st.caption(f"ai_runs.db に run が見つかりません（run_id: {rid}）")
        return

    # ------------------------------------------------------------
    # divider / caption style
    # ------------------------------------------------------------
    if show_divider:
        st.divider()
    _apply_caption_compact_style()

    # ------------------------------------------------------------
    # time（ai_runs.db）
    # ------------------------------------------------------------
    started_at = row.get("started_at") or "—"
    finished_at = row.get("finished_at") or "—"
    elapsed_ms = row.get("elapsed_ms")

    elapsed_sec: Optional[float] = None
    if isinstance(elapsed_ms, (int, float)):
        try:
            elapsed_sec = float(elapsed_ms) / 1000.0
        except Exception:
            elapsed_sec = None

    # ------------------------------------------------------------
    # audio_seconds（ページから来なければ row から拾う）
    # ------------------------------------------------------------
    if audio_sec is None:
        audio_sec = _pick_audio_sec_from_row(row)

    audio_str = "—"
    if isinstance(audio_sec, (int, float)):
        audio_str = f"{float(audio_sec):.1f}s"

    # ------------------------------------------------------------
    # cost（ページから来なければ row から拾う）
    # ------------------------------------------------------------
    if cost is None:
        cost = _pick_cost_from_row(row)

    jpy = getattr(cost, "jpy", None) if cost is not None else None
    usd = getattr(cost, "usd", None) if cost is not None else None

    jpy_str = f"¥{float(jpy):.2f}" if isinstance(jpy, (int, float)) else "—"
    usd_str = f"${float(usd):.6f}" if isinstance(usd, (int, float)) else "—"

    el_str = f"{float(elapsed_sec):.2f}s" if isinstance(elapsed_sec, (int, float)) else "—"

    # ------------------------------------------------------------
    # 1行目：主要サマリ（text テンプレと同じ並び）
    # ------------------------------------------------------------
    st.write(
        f"**音声時間** {audio_str}　　"
        f"**費用** {jpy_str} / {usd_str}　　"
        f"**AI使用時間** {el_str}"
    )

    # ------------------------------------------------------------
    # 2〜4行目：メタ（1行ずつ明示）
    # ------------------------------------------------------------
    st.caption(f"モデル {model or '—'}・状態 {row.get('status')}")
    st.caption(f"開始 {format_jst_iso_ja(str(started_at))}・終了 {format_jst_iso_ja(str(finished_at))}")

    # ------------------------------------------------------------
    # note（条件付き）
    # ------------------------------------------------------------
    n = (note or "").strip()
    if n:
        st.caption(f"run_id {rid}　　note: {n}")
    else:
        st.caption(f"run_id {rid}")

    

