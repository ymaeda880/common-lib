# common_lib/rag_ingest/chunk_ops.py
# =============================================================================
# RAG ingest : テキスト chunk 化 正本ロジック
#
# 役割：
# - 入力テキストを chunk に分割する
# - chunk_index / span_start / span_end / chunk_len_tokens を付与する
# - 日本語文書向けの「文をなるべく壊さない」chunk 化を提供する
#
# 設計方針：
# - page 番号には依存しない
# - 文の途中で極力切らない
# - まずは安定した初期実装を優先する
# - 将来、より高度なルール（見出し考慮・page復元など）に拡張しやすくする
#
# 初期ルール：
# - 改行をある程度正規化する
# - 文末記号（。！？!?）+ 改行 の境界を優先して分割する
# - 1文が極端に長い場合のみ強制分割する
# - chunk はおおむね max_chars 以内に収める
# - chunk_len_tokens は厳密 tokenization ではなく近似値を返す
#
# 注意：
# - embedding model ごとの厳密 tokenizer はここでは使わない
# - token 数は近似であり、主用途は chunk サイズの目安
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .models import ChunkRecord


# =============================================================================
# 定数
# =============================================================================
DEFAULT_MAX_CHARS = 1200
DEFAULT_MIN_CHARS = 400
DEFAULT_HARD_MAX_CHARS = 1800

# 文末候補
_SENT_END_CHARS = "。！？!?\n"

# 文分割用正規表現
_SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?])")


# =============================================================================
# option
# =============================================================================
@dataclass(slots=True)
class ChunkOptions:
    # -----------------------------------------------------------------------------
    # chunk 化オプション
    # -----------------------------------------------------------------------------
    max_chars: int = DEFAULT_MAX_CHARS
    min_chars: int = DEFAULT_MIN_CHARS
    hard_max_chars: int = DEFAULT_HARD_MAX_CHARS

    def __post_init__(self) -> None:
        # -------------------------------------------------------------------------
        # 値の最低限チェック
        # -------------------------------------------------------------------------
        self.max_chars = max(1, int(self.max_chars))
        self.min_chars = max(1, int(self.min_chars))
        self.hard_max_chars = max(self.max_chars, int(self.hard_max_chars))


# =============================================================================
# text normalize
# =============================================================================
def normalize_text_for_chunking(text: str) -> str:
    # -----------------------------------------------------------------------------
    # chunk 化前の軽い正規化
    #
    # 方針：
    # - 改行コード統一
    # - タブを半角空白へ
    # - 連続3個以上の改行は2個へ
    # - 行頭/行末の過剰空白を整える
    #
    # 注意：
    # - OCR の内容を壊しすぎないよう、過度な正規化はしない
    # -----------------------------------------------------------------------------
    s = str(text or "")

    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\t", " ")

    # 行ごとの末尾空白を削る
    lines = [ln.rstrip() for ln in s.split("\n")]
    s = "\n".join(lines)

    # 連続空行を少し圧縮
    s = re.sub(r"\n{3,}", "\n\n", s)

    # 先頭末尾の余分な空白除去
    s = s.strip()

    return s


# =============================================================================
# token estimate
# =============================================================================
def estimate_token_count(text: str) -> int:
    # -----------------------------------------------------------------------------
    # token 数の近似値
    #
    # 初期実装として、かなり軽い近似を返す。
    #
    # 考え方：
    # - 日本語は 1文字 ≒ 1 token では大きすぎる
    # - 英数字列はまとめて 1語として数える
    # - ざっくり「日本語文字数 + 英単語数」を混ぜて見積もる
    #
    # これは厳密ではないが、chunk サイズ制御の目安には使える。
    # -----------------------------------------------------------------------------
    s = str(text or "")
    if not s:
        return 0

    # 英数字の単語
    latin_words = re.findall(r"[A-Za-z0-9_]+", s)

    # 英数字を除いた残り
    rest = re.sub(r"[A-Za-z0-9_]+", "", s)

    # 空白を除いた残り文字数
    jp_chars = len(re.sub(r"\s+", "", rest))

    # 英単語は1語=1 token では過小になりがちなので少し重め
    est = jp_chars + int(len(latin_words) * 1.3)

    return max(1, est)


# =============================================================================
# sentence split
# =============================================================================
def split_text_into_sentence_like_units(text: str) -> list[str]:
    # -----------------------------------------------------------------------------
    # テキストを「文らしき単位」に分割する
    #
    # ルール：
    # - 基本は 。！？!? の直後で切る
    # - 改行だけの区切りも保持する
    # - 空要素は除く
    #
    # 注意：
    # - 完全な文解析ではない
    # - 初期実装として安定性を優先
    # -----------------------------------------------------------------------------
    s = str(text or "")
    if not s:
        return []

    parts: list[str] = []

    # まず段落レベルで分ける（空行は意味を持ちやすい）
    paragraphs = s.split("\n\n")

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # 段落内は文末記号ベースで分割
        segs = _SENT_SPLIT_RE.split(para)
        for seg in segs:
            ss = seg.strip()
            if ss:
                parts.append(ss)

    return parts


# =============================================================================
# long unit split
# =============================================================================
def split_long_unit(unit: str, hard_max_chars: int) -> list[str]:
    # -----------------------------------------------------------------------------
    # 1文が長すぎる場合の強制分割
    #
    # 優先順位：
    # 1. 改行
    # 2. 読点や句読点
    # 3. hard_max_chars 固定
    # -----------------------------------------------------------------------------
    s = str(unit or "").strip()
    if not s:
        return []

    hmax = max(1, int(hard_max_chars))

    if len(s) <= hmax:
        return [s]

    out: list[str] = []
    rest = s

    while len(rest) > hmax:
        cut = _find_soft_cut(rest, hmax)
        head = rest[:cut].strip()
        if head:
            out.append(head)
        rest = rest[cut:].strip()

    if rest:
        out.append(rest)

    return out


def _find_soft_cut(s: str, limit: int) -> int:
    # -----------------------------------------------------------------------------
    # できるだけ自然な切れ目を探す
    # -----------------------------------------------------------------------------
    if len(s) <= limit:
        return len(s)

    window = s[:limit]

    # 改行を優先
    pos = window.rfind("\n")
    if pos >= max(1, limit // 2):
        return pos + 1

    # 句読点や区切り記号
    for ch in ["。", "、", "；", "：", ";", ":", "）", ")", " "]:
        pos = window.rfind(ch)
        if pos >= max(1, limit // 2):
            return pos + 1

    return limit


# =============================================================================
# chunk build
# =============================================================================
def build_chunks_from_units(
    units: Sequence[str],
    *,
    options: ChunkOptions,
) -> list[str]:
    # -----------------------------------------------------------------------------
    # 文単位リストから chunk 文字列のリストを作る
    #
    # ルール：
    # - max_chars を超えない範囲でできるだけ結合
    # - ただし min_chars 未満で終わりそうな時は少し抱き合わせる
    # - 1 unit が hard_max_chars を超える場合は事前分割を前提とする
    # -----------------------------------------------------------------------------
    chunks: list[str] = []
    buf = ""

    for unit in units:
        u = str(unit or "").strip()
        if not u:
            continue

        if not buf:
            buf = u
            continue

        cand = f"{buf}\n{u}"

        # max_chars 以下なら結合
        if len(cand) <= options.max_chars:
            buf = cand
            continue

        # すでに buf が十分長いならここで確定
        if len(buf) >= options.min_chars:
            chunks.append(buf.strip())
            buf = u
            continue

        # buf が短い場合、次の unit を含めても hard_max を超えないなら抱き合わせ
        if len(cand) <= options.hard_max_chars:
            buf = cand
            continue

        # それでも厳しい場合は buf を確定
        chunks.append(buf.strip())
        buf = u

    if buf.strip():
        chunks.append(buf.strip())

    return [c for c in chunks if c]


# =============================================================================
# span restore
# =============================================================================
def attach_spans_from_chunks(
    original_text: str,
    chunk_texts: Sequence[str],
) -> list[ChunkRecord]:
    # -----------------------------------------------------------------------------
    # chunk文字列列を元の全文中の span に対応付ける
    #
    # 方針：
    # - normalize 後の original_text に対して前方探索
    # - 同一 chunk 文が重複しても、前回終了位置以降を優先して探す
    #
    # 注意：
    # - 完全一致が取れない場合はフォールバック検索を行う
    # -----------------------------------------------------------------------------
    src = str(original_text or "")
    out: list[ChunkRecord] = []

    search_pos = 0

    for idx, chunk in enumerate(chunk_texts):
        c = str(chunk or "")
        if not c:
            continue

        pos = src.find(c, search_pos)

        if pos < 0:
            # 少し弱い一致を試す
            c2 = c.replace("\n", " ").strip()
            src2 = src[search_pos:].replace("\n", " ")
            rel = src2.find(c2)
            if rel >= 0:
                pos = search_pos + rel
            else:
                # どうしても見つからない場合は長さベースの仮置き
                pos = search_pos

        end = pos + len(c)

        out.append(
            ChunkRecord(
                chunk_index=idx,
                text=c,
                span_start=pos,
                span_end=end,
                chunk_len_tokens=estimate_token_count(c),
            )
        )

        search_pos = max(search_pos, end)

    return out


# =============================================================================
# public main
# =============================================================================
def chunk_text(
    text: str,
    *,
    options: ChunkOptions | None = None,
) -> list[ChunkRecord]:
    # -----------------------------------------------------------------------------
    # テキストを chunk 化して ChunkRecord の list を返す
    #
    # 処理手順：
    # 1. normalize
    # 2. 文らしき単位へ分割
    # 3. 長すぎる unit は分割
    # 4. unit をまとめて chunk 化
    # 5. span_start / span_end を付与
    # -----------------------------------------------------------------------------
    opt = options or ChunkOptions()

    normalized = normalize_text_for_chunking(text)
    if not normalized:
        return []

    units = split_text_into_sentence_like_units(normalized)

    # 文らしき単位が取れなかった場合の保険
    if not units:
        units = [normalized]

    expanded_units: list[str] = []
    for unit in units:
        parts = split_long_unit(unit, opt.hard_max_chars)
        expanded_units.extend(parts)

    chunk_texts = build_chunks_from_units(
        expanded_units,
        options=opt,
    )

    return attach_spans_from_chunks(
        original_text=normalized,
        chunk_texts=chunk_texts,
    )



# =============================================================================
# page-aware chunk
# =============================================================================
@dataclass(slots=True)
class _PagedUnit:
    text: str
    pages: tuple[int, ...]


def _unique_pages(pages: Iterable[int]) -> tuple[int, ...]:
    out: list[int] = []
    seen: set[int] = set()

    for p in pages:
        pp = int(p)
        if pp <= 0:
            continue
        if pp in seen:
            continue
        seen.add(pp)
        out.append(pp)

    return tuple(out)


def build_chunks_from_paged_units(
    units: Sequence[_PagedUnit],
    *,
    options: ChunkOptions,
) -> list[tuple[str, tuple[int, ...]]]:
    chunks: list[tuple[str, tuple[int, ...]]] = []

    buf = ""
    buf_pages: list[int] = []

    for unit in units:
        u = str(unit.text or "").strip()
        if not u:
            continue

        if not buf:
            buf = u
            buf_pages = list(unit.pages)
            continue

        cand = f"{buf}\n{u}"
        cand_pages = list(buf_pages) + list(unit.pages)

        if len(cand) <= options.max_chars:
            buf = cand
            buf_pages = cand_pages
            continue

        if len(buf) >= options.min_chars:
            chunks.append((buf.strip(), _unique_pages(buf_pages)))
            buf = u
            buf_pages = list(unit.pages)
            continue

        if len(cand) <= options.hard_max_chars:
            buf = cand
            buf_pages = cand_pages
            continue

        chunks.append((buf.strip(), _unique_pages(buf_pages)))
        buf = u
        buf_pages = list(unit.pages)

    if buf.strip():
        chunks.append((buf.strip(), _unique_pages(buf_pages)))

    return [(text, pages) for text, pages in chunks if text]


def chunk_text_from_pages(
    pages: Sequence[dict],
    *,
    options: ChunkOptions | None = None,
) -> tuple[str, list[ChunkRecord], list[tuple[int, int]]]:
    opt = options or ChunkOptions()

    normalized_page_texts: list[str] = []
    paged_units: list[_PagedUnit] = []

    for row in pages:
        if not isinstance(row, dict):
            continue

        page_no = int(row.get("page", row.get("page_no", 0)) or 0)
        raw_text = str(row.get("text", "") or "")

        if page_no <= 0:
            continue

        normalized = normalize_text_for_chunking(raw_text)
        if not normalized:
            continue

        normalized_page_texts.append(normalized)

        units = split_text_into_sentence_like_units(normalized)
        if not units:
            units = [normalized]

        for unit in units:
            parts = split_long_unit(unit, opt.hard_max_chars)
            for part in parts:
                part_text = str(part or "").strip()
                if part_text:
                    paged_units.append(
                        _PagedUnit(
                            text=part_text,
                            pages=(page_no,),
                        )
                    )

    ingest_text = "\n".join(normalized_page_texts).strip()

    if not ingest_text or not paged_units:
        return "", [], []

    chunk_pairs = build_chunks_from_paged_units(
        paged_units,
        options=opt,
    )

    chunks: list[ChunkRecord] = []
    chunk_page_ranges: list[tuple[int, int]] = []

    cursor = 0

    for idx, (chunk_body, pages_in_chunk) in enumerate(chunk_pairs):
        text = str(chunk_body or "").strip()
        if not text:
            continue

        page_list = [int(p) for p in pages_in_chunk if int(p) > 0]

        if page_list:
            page_start = min(page_list)
            page_end = max(page_list)
        else:
            page_start = 0
            page_end = 0

        span_start = cursor
        span_end = span_start + len(text)

        chunks.append(
            ChunkRecord(
                chunk_index=len(chunks),
                text=text,
                span_start=span_start,
                span_end=span_end,
                chunk_len_tokens=estimate_token_count(text),
            )
        )

        chunk_page_ranges.append((int(page_start), int(page_end)))

        cursor = span_end + 1

    return ingest_text, chunks, chunk_page_ranges

# =============================================================================
# convenience
# =============================================================================
def chunk_text_default(text: str) -> list[ChunkRecord]:
    # -----------------------------------------------------------------------------
    # デフォルト設定で chunk 化
    # -----------------------------------------------------------------------------
    return chunk_text(
        text,
        options=ChunkOptions(),
    )


def chunk_text_with_char_limits(
    text: str,
    *,
    max_chars: int,
    min_chars: int,
    hard_max_chars: int,
) -> list[ChunkRecord]:
    # -----------------------------------------------------------------------------
    # 文字数制御を明示して chunk 化
    # -----------------------------------------------------------------------------
    return chunk_text(
        text,
        options=ChunkOptions(
            max_chars=max_chars,
            min_chars=min_chars,
            hard_max_chars=hard_max_chars,
        ),
    )