# common_lib/pdf_tools/text_clean/cleaner.py
# ============================================================
# PDF text clean（共通ライブラリ：正本）
#
# 目的：
# - OCR後の .txt テキストを RAG 向けにクリーニングする正本ロジック
#
# 機能：
# - Unicode正規化（NFKC）
# - 罫線/装飾行の削除
# - 単独記号など短いノイズ行の削除
# - 英字ゴミ行の削除（日本語文書向け）
# - 目次ブロック除去（連続判定）
# - 反復行除去（頻度ベース：ヘッダー/フッター候補）
# - 文中改行の結合
# - 空行圧縮
# - 日本語文中の単発スペース除去（例：手賀 沼 → 手賀沼、2 つ → 2つ）
#
# 設計方針：
# - 「削りすぎない」を優先（RAG用途：意味を壊さない）
# - UIに依存しない（Streamlitは使わない）
# - 返り値に debug_report を含め、運用時の検証を容易にする
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List, Tuple


# ============================================================
# public config
# ============================================================
@dataclass(frozen=True)
class CleanOptions:
    # ------------------------------------------------------------
    # 基本正規化
    # ------------------------------------------------------------
    enable_nfkc: bool = True
    compress_spaces: bool = True
    normalize_newlines: bool = True

    # ------------------------------------------------------------
    # 日本語文中スペース除去（OCRノイズ対策）
    # ------------------------------------------------------------
    remove_jp_in_sentence_spaces: bool = True

    # ------------------------------------------------------------
    # 行ノイズ除去
    # ------------------------------------------------------------
    drop_decoration_lines: bool = True
    drop_tiny_noise_lines: bool = True
    drop_garbage_english_lines: bool = True

    # ------------------------------------------------------------
    # 目次ブロック除去（連続判定）
    # ------------------------------------------------------------
    drop_toc_block: bool = True
    toc_min_run: int = 6  # 目次っぽい行が連続で何行以上ならブロック扱いするか

    # ------------------------------------------------------------
    # 反復行除去（頻度ベース：ヘッダー/フッター候補）
    # ------------------------------------------------------------
    drop_repeated_lines: bool = True
    repeated_min_count: int = 3
    repeated_max_len: int = 40

    # ------------------------------------------------------------
    # 文中改行結合
    # ------------------------------------------------------------
    join_wrapped_lines: bool = True

    # ------------------------------------------------------------
    # 空行圧縮
    # ------------------------------------------------------------
    compress_blank_lines: bool = True


# ============================================================
# constants / regex
# ============================================================
_SYMBOLS = set("|｜¦┃━―─-_=~^`'\".,。・:：;；!！?？()（）[]［］{}｛｝<>＜＞／/\\+*#@＆&％%…")
_JP_CHARS_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")  # ひらがな・カタカナ・漢字
_LATIN_RE = re.compile(r"[A-Za-z]")
_DIGIT_RE = re.compile(r"[0-9]")

# 目次っぽい行（先頭：番号/章節、末尾：ページ数）
_TOC_LINE_RE = re.compile(
    r"^\s*("
    r"(第\s*\d+\s*[章節項])"     # 第1章 等
    r"|([IVX]+[.\s])"           # I. II.
    r"|(\d+\s*[.)])"            # 1. 2)
    r")"
    r".*"
    r"(\s*[0-9]{1,3}\s*)$"       # 末尾ページ番号
)

_JP_OR_KANJI = r"\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"  # 日本語文字範囲


# ============================================================
# helpers（ratios）
# ============================================================
def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _symbol_ratio(line: str) -> float:
    s = line.strip()
    if not s:
        return 0.0
    sym = sum(1 for ch in s if ch in _SYMBOLS)
    return sym / max(1, len(s))


def _jp_ratio(line: str) -> float:
    s = line.strip()
    if not s:
        return 0.0
    jp = len(_JP_CHARS_RE.findall(s))
    return jp / max(1, len(s))


def _latin_ratio(line: str) -> float:
    s = line.strip()
    if not s:
        return 0.0
    lt = len(_LATIN_RE.findall(s))
    return lt / max(1, len(s))


def _digit_ratio(line: str) -> float:
    s = line.strip()
    if not s:
        return 0.0
    dg = len(_DIGIT_RE.findall(s))
    return dg / max(1, len(s))


# ============================================================
# helpers（line classification）
# ============================================================
def _is_heading_like(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if re.match(r"^(第\s*\d+\s*[章節項]|[IVX]+\.|\d+\s*[.)]|\(\d+\)|（\d+）|[〇○●◎■◆◇・※\-])", s):
        return True
    if s in {"目次", "まえがき", "前書き", "序", "序文", "資料", "資料編", "参考資料"}:
        return True
    return False


def _is_decoration_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if re.search(r"(ー|―|─|\-|_|=|・|\.|。){5,}", s):
        return True
    if _symbol_ratio(s) >= 0.7 and len(s) >= 6:
        return True
    if re.fullmatch(r"[|｜¦┃\s]{4,}", s):
        return True
    return False


def _is_tiny_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _is_heading_like(s):
        return False
    if len(s) <= 2:
        if re.fullmatch(r"\d{1,3}", s):
            return False
        return True
    return False


def _is_garbage_english_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _is_heading_like(s):
        return False
    if len(s) > 60:
        return False
    jp_r = _jp_ratio(s)
    lt_r = _latin_ratio(s)
    sym_r = _symbol_ratio(s)
    if jp_r < 0.10 and (lt_r + sym_r) >= 0.60 and lt_r >= 0.25:
        return True
    return False


# ============================================================
# helpers（inline normalization）
# ============================================================
def _remove_japanese_in_sentence_spaces(text: str) -> str:
    """
    日本語文中に入る単発スペースを除去する（OCRノイズ対策）。
    例：
      - 手賀 沼 → 手賀沼
      - 2 つ → 2つ
      - 平成12 年度 → 平成12年度
      - を みると → をみると
    """
    t = text
    # 日本語 ↔ 日本語
    t = re.sub(rf"(?<=[{_JP_OR_KANJI}])\s+(?=[{_JP_OR_KANJI}])", "", t)
    # 数字 ↔ 日本語
    t = re.sub(rf"(?<=\d)\s+(?=[{_JP_OR_KANJI}])", "", t)
    t = re.sub(rf"(?<=[{_JP_OR_KANJI}])\s+(?=\d)", "", t)
    return t


def _cleanup_inline_noise(text: str, opt: CleanOptions) -> str:
    t = text

    if opt.normalize_newlines:
        t = t.replace("\r\n", "\n").replace("\r", "\n")

    if opt.enable_nfkc:
        t = _nfkc(t)

    # 連続装飾の圧縮（やりすぎない）
    t = re.sub(r"(・){3,}", "・", t)
    t = re.sub(r"(\.){3,}", "...", t)
    t = re.sub(r"(ー){3,}", "ー", t)
    t = re.sub(r"(=){3,}", "==", t)

    # 単独パイプ（単語間）をスペースへ
    t = re.sub(r"\s[|｜]\s", " ", t)

    if opt.compress_spaces:
        t = re.sub(r"[ \t]{2,}", " ", t)

    if opt.remove_jp_in_sentence_spaces:
        t = _remove_japanese_in_sentence_spaces(t)

    return t


# ============================================================
# helpers（TOC block）
# ============================================================
def _looks_like_toc_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s == "目次":
        return True
    if _TOC_LINE_RE.match(s):
        return True
    if re.search(r"\s[0-9]{1,3}\s*$", s) and _symbol_ratio(s) >= 0.35 and len(s) >= 8:
        if re.match(r"^(第\s*\d+|[IVX]+\.|\d+\s*[.)])", s):
            return True
    return False


def _drop_toc_blocks(lines: List[str], toc_min_run: int) -> Tuple[List[str], List[Tuple[int, int]]]:
    if toc_min_run < 2:
        toc_min_run = 2

    dropped: List[Tuple[int, int]] = []
    keep: List[str] = []

    i = 0
    n = len(lines)
    while i < n:
        if _looks_like_toc_line(lines[i]):
            j = i
            while j < n and _looks_like_toc_line(lines[j]):
                j += 1
            run_len = j - i
            if run_len >= toc_min_run:
                dropped.append((i, j - 1))
                i = j
                continue
        keep.append(lines[i])
        i += 1

    return keep, dropped


# ============================================================
# helpers（repeated line）
# ============================================================
def _canonicalize_line_for_count(line: str) -> str:
    s = line.strip()
    if not s:
        return ""
    s = _nfkc(s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s


def _detect_repeated_lines(
    lines: Iterable[str],
    *,
    min_count: int,
    max_len: int,
) -> List[str]:
    if min_count < 2:
        min_count = 2
    if max_len < 10:
        max_len = 10

    canon = [_canonicalize_line_for_count(x) for x in lines]
    canon = [x for x in canon if x]

    cnt = Counter(canon)
    targets: List[str] = []
    for s, c in cnt.items():
        if c >= min_count and len(s) <= max_len:
            if _is_heading_like(s):
                continue
            targets.append(s)

    return targets


# ============================================================
# helpers（join / compress）
# ============================================================
def _join_wrapped_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    buf = ""

    def flush_buf() -> None:
        nonlocal buf
        if buf.strip():
            out.append(buf.strip())
        buf = ""

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_buf()
            continue

        if _is_heading_like(line):
            flush_buf()
            out.append(line)
            continue

        if re.match(r"^[〇○●◎■◆◇・※\-]\s*", line):
            flush_buf()
            out.append(line)
            continue

        if not buf:
            buf = line
            continue

        prev = buf

        if re.search(r"[。．.!！?？:]$", prev):
            flush_buf()
            buf = line
            continue

        if _is_heading_like(line):
            flush_buf()
            out.append(line)
            continue

        buf = f"{prev} {line}"

    flush_buf()
    return out


def _compress_blank_lines(lines: List[str]) -> List[str]:
    out: List[str] = []
    prev_blank = False
    for ln in lines:
        s = ln.strip()
        if not s:
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(s)
            prev_blank = False
    return out


# ============================================================
# public api
# ============================================================
def clean_ocr_text(src_text: str, opt: CleanOptions) -> Tuple[str, str]:
    """
    戻り値:
      - cleaned_text
      - debug_report（UI表示用）
    """
    # 0) inline normalize
    t = _cleanup_inline_noise(src_text, opt)

    # 1) line split
    raw_lines = t.split("\n")

    # 2) line-level filtering
    kept: List[str] = []
    dropped_decoration = 0
    dropped_tiny = 0
    dropped_garbage_en = 0

    for ln in raw_lines:
        s = ln.strip()
        if not s:
            kept.append("")
            continue

        if opt.drop_decoration_lines and _is_decoration_line(s):
            dropped_decoration += 1
            continue

        if opt.drop_tiny_noise_lines and _is_tiny_noise_line(s):
            dropped_tiny += 1
            continue

        if opt.drop_garbage_english_lines and _is_garbage_english_line(s):
            dropped_garbage_en += 1
            continue

        kept.append(s)

    # 3) drop TOC blocks
    toc_dropped_ranges: List[Tuple[int, int]] = []
    if opt.drop_toc_block:
        kept, toc_dropped_ranges = _drop_toc_blocks(kept, toc_min_run=int(opt.toc_min_run))

    # 4) drop repeated lines（frequency based）
    repeated_targets: List[str] = []
    dropped_repeated = 0
    if opt.drop_repeated_lines:
        repeated_targets = _detect_repeated_lines(
            kept,
            min_count=int(opt.repeated_min_count),
            max_len=int(opt.repeated_max_len),
        )
        if repeated_targets:
            new_lines: List[str] = []
            for ln in kept:
                canon = _canonicalize_line_for_count(ln)
                if canon and canon in repeated_targets:
                    dropped_repeated += 1
                    continue
                new_lines.append(ln)
            kept = new_lines

    # 5) join wrapped lines
    joined = kept
    if opt.join_wrapped_lines:
        joined = _join_wrapped_lines(kept)

    # 6) compress blank lines
    final_lines = joined
    if opt.compress_blank_lines:
        final_lines = _compress_blank_lines(joined)

    cleaned = "\n".join(final_lines).strip()

    # debug report
    report_lines: List[str] = []
    report_lines.append("=== cleaning report ===")
    report_lines.append(f"lines_in={len(raw_lines)}")
    report_lines.append(f"lines_after_line_filter={len(kept)}")
    report_lines.append(f"dropped_decoration={dropped_decoration}")
    report_lines.append(f"dropped_tiny_noise={dropped_tiny}")
    report_lines.append(f"dropped_garbage_english={dropped_garbage_en}")

    if opt.drop_toc_block:
        report_lines.append(f"toc_dropped_blocks={len(toc_dropped_ranges)} (min_run={int(opt.toc_min_run)})")
        if toc_dropped_ranges:
            show = toc_dropped_ranges[:3]
            show_txt = ", ".join([f"{a+1}-{b+1}" for a, b in show])
            report_lines.append(f"toc_block_ranges(line_no_1based)={show_txt}")

    if opt.drop_repeated_lines:
        report_lines.append(
            f"repeated_lines_removed={dropped_repeated} "
            f"(min_count={int(opt.repeated_min_count)}, max_len={int(opt.repeated_max_len)})"
        )
        if repeated_targets:
            top = repeated_targets[:10]
            report_lines.append("repeated_targets_top10=")
            for x in top:
                report_lines.append(f"  - {x}")

    report_lines.append("=======================")

    return cleaned, "\n".join(report_lines)


def decode_text_bytes(raw_bytes: bytes) -> str:
    """
    OCR後txtのデコード（BOM/文字化けに強め）
    """
    decoded = ""
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            decoded = raw_bytes.decode(enc)
            break
        except Exception:
            pass
    if not decoded:
        decoded = raw_bytes.decode("utf-8", errors="ignore")
    return decoded


def build_clean_txt_filename(src_name: str) -> str:
    base = (src_name or "text").strip()
    if base.lower().endswith(".txt"):
        base = base[:-4]
    return f"{base}_cleaned.txt"