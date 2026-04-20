# common_lib/rag_ingest/embedding_ops.py
# =============================================================================
# RAG ingest : embedding 実行 正本
#
# 役割：
# - common_lib.ai の正本 API を使って embedding を実行する
# - provider 直叩きを禁止し、共通基盤から同一方式で埋込を行う
# - busy_run を使って ai_runs.db へ実行記録を残す
# - token / cost は「返ってきた範囲のみ」反映する（推計しない）
#
# 準拠元：
# - toolkit_app/pages/108_ベクトル埋込（テンプレ）.py
#
# 方針：
# - embed_text は common_lib.ai の正本のみを使う
# - usage は extract_embedding_token_usage を使う
# - cost は apply_embedding_result_to_busy を使う
# - 返却値は EmbeddingRunResult にまとめる
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from pathlib import Path
from typing import Any, Iterable, List, Sequence, Tuple

from .models import EmbeddingRunResult

# =============================================================================
# common_lib.busy
# =============================================================================
from common_lib.busy import busy_run
from common_lib.busy.apply_embedding_result import apply_embedding_result_to_busy

# =============================================================================
# common_lib.ai
# =============================================================================
try:
    from common_lib.ai import embed_text
    from common_lib.ai.usage_extract.extract_tokens import extract_embedding_token_usage
except Exception as e:
    raise RuntimeError(
        "common_lib.ai の embedding API が利用できません。"
        " common_lib.ai.embed_text / extract_embedding_token_usage を確認してください。"
    ) from e


# =============================================================================
# helper
# =============================================================================
def parse_model_key(model_key: str) -> tuple[str, str]:
    # -----------------------------------------------------------------------------
    # model_key を provider / model に分解する
    #
    # 想定：
    # - "openai:text-embedding-3-large"
    # - "text-embedding-3-large" の場合は provider=openai とみなす
    # -----------------------------------------------------------------------------
    s = str(model_key or "").strip()

    if not s:
        raise ValueError("model_key が空です。")

    if ":" not in s:
        return ("openai", s)

    prov, mdl = s.split(":", 1)
    provider = str(prov or "").strip()
    model = str(mdl or "").strip()

    if not provider:
        raise ValueError("provider が空です。")
    if not model:
        raise ValueError("model が空です。")

    return (provider, model)


def normalize_inputs(inputs: Sequence[str]) -> list[str]:
    # -----------------------------------------------------------------------------
    # embedding 入力列を正規化する
    #
    # 方針：
    # - None を受けない
    # - 空白のみ要素は除外する
    # -----------------------------------------------------------------------------
    out: list[str] = []

    for x in inputs:
        s = str(x or "")
        if s.strip():
            out.append(s)

    return out


def _calc_vector_dimension(vectors: list[list[float]]) -> int:
    # -----------------------------------------------------------------------------
    # ベクトル次元数
    # -----------------------------------------------------------------------------
    if not vectors:
        return 0

    first = vectors[0]
    return len(first) if isinstance(first, list) else 0


# =============================================================================
# main
# =============================================================================
def run_embedding(
    *,
    projects_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    model_key: str,
    inputs: Sequence[str],
    feature: str = "rag_ingest_embedding",
    meta: dict | None = None,
) -> EmbeddingRunResult:
    # -----------------------------------------------------------------------------
    # embedding を実行して EmbeddingRunResult を返す
    #
    # 引数：
    # - projects_root:
    #     busy_run 用
    #
    # - user_sub:
    #     実行ユーザー
    #
    # - app_name / page_name:
    #     ai_runs.db 記録用
    #
    # - model_key:
    #     "provider:model" 形式を想定
    #
    # - inputs:
    #     埋込対象のテキスト列
    #
    # - feature:
    #     busy meta に入れる feature 名
    #
    # - meta:
    #     追加 meta
    #
    # 返却：
    # - EmbeddingRunResult
    #
    # 注意：
    # - token / cost は返ってきた範囲のみ反映
    # - 推計しない
    # -----------------------------------------------------------------------------
    provider, model = parse_model_key(model_key)
    norm_inputs = normalize_inputs(inputs)

    if not norm_inputs:
        raise ValueError("embedding 対象テキストが空です。")

    run_meta = {
        "feature": str(feature),
        "n_items": len(norm_inputs),
        "prompt_chars": sum(len(x) for x in norm_inputs),
    }
    if isinstance(meta, dict):
        run_meta.update(meta)

    try:
        with busy_run(
            projects_root=projects_root,
            user_sub=str(user_sub),
            app_name=str(app_name),
            page_name=str(page_name),
            task_type="embedding",
            provider=str(provider),
            model=str(model),
            meta=run_meta,
        ) as br:
            run_id = br.run_id

            res = embed_text(
                provider=provider,
                model=model,
                inputs=norm_inputs,
            )

            vectors: List[List[float]] = getattr(res, "vectors", []) or []
            dim = _calc_vector_dimension(vectors)

            # -----------------------------------------------------------------
            # token usage（推計しない）
            # -----------------------------------------------------------------
            tu = extract_embedding_token_usage(
                res=res,
                provider=str(provider),
            )

            in_tokens = tu.input_tokens
            out_tokens = None

            # busy に input token だけ反映できる実装がある場合のみ使う
            if isinstance(in_tokens, int) and hasattr(br, "set_usage_input_only"):
                br.set_usage_input_only(int(in_tokens))

            # -----------------------------------------------------------------
            # cost（推計しない）
            # -----------------------------------------------------------------
            pp_cost = apply_embedding_result_to_busy(
                br=br,
                res=res,
                note_ok_cost="ok_cost",
                note_no_cost="no_cost",
            )

            br.add_finish_meta(note="ok")

    except Exception as e:
        raise RuntimeError(f"embedding 実行エラー: {e}") from e

    return EmbeddingRunResult(
        provider=str(provider),
        model=str(model),
        vectors=vectors,
        dimension=int(dim),
        n_items=len(vectors),
        run_id=str(run_id) if run_id is not None else None,
        in_tokens=in_tokens if isinstance(in_tokens, int) else None,
        out_tokens=out_tokens,
        cost_obj=getattr(pp_cost, "cost_obj", None),
    )


# =============================================================================
# convenience
# =============================================================================
def run_embedding_for_chunks(
    *,
    projects_root: Path,
    user_sub: str,
    app_name: str,
    page_name: str,
    model_key: str,
    chunk_texts: Sequence[str],
    feature: str = "rag_ingest_embedding_chunks",
    meta: dict | None = None,
) -> EmbeddingRunResult:
    # -----------------------------------------------------------------------------
    # chunk テキスト列を embedding するための簡易関数
    # -----------------------------------------------------------------------------
    return run_embedding(
        projects_root=projects_root,
        user_sub=user_sub,
        app_name=app_name,
        page_name=page_name,
        model_key=model_key,
        inputs=chunk_texts,
        feature=feature,
        meta=meta,
    )