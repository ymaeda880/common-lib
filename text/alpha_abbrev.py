# -*- coding: utf-8 -*-
# common_lib/text/alpha_abbrev.py
# ============================================================
# アルファベット略語の正規化（共通ライブラリ）
# ------------------------------------------------------------
# 目的：
# - アルファベット略語・記号トークン（例：PJ, PNO, FY, year）を機械的に正規化する
# - LLM に解釈させず、前段で意味を確定させる（再現性・監査性）
# - 将来的に匿名化（人名/部署名/地名のID化など）にも同じ枠組みを拡張して使う
#
# 機能：
# - normalize_alpha_abbrev(text) -> (normalized_text, report)
# - 置換ログ（report）を返す（どのルールが何回当たったか）
#
# 設計方針：
# - “語境界”を使い、英数字連結IDの一部を壊さない
#   例：PJNO / PJN / ABPJ12 の PJ は勝手に置換しない
# - 置換は「ユーザー入力テキスト」にのみ適用（Retrieved Contexts は改変しない）
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
import re

from common_lib.text.alpha_abbrev_rules import ALPHA_ABBREV_RULES

# ============================================================
# 置換ログ（要約）
# ============================================================

@dataclass(frozen=True)
class AlphaAbbrevRewriteHit:
    """
    1つのルールが何回当たったか（要約ログ）
    """
    key: str
    replacement: str
    count: int


# ============================================================
# 置換ルール（正本）
# - 長い語（PJNO等）を先に処理して短い語（PJ）に誤爆しない
# - (?i) で大文字小文字を吸収（pno/PNO 等）
# - 英数字・アンダースコアに挟まれた場合は置換しない（ID破壊防止）
# ============================================================
def _compile_rules() -> List[Tuple[str, re.Pattern[str], str]]:
    """
    辞書（ALPHA_ABBREV_RULES）から正規表現ルールを生成する。

    設計：
    - 語境界：英数字/アンダースコアに挟まれていないトークンのみ対象
    - 大文字小文字は吸収（re.IGNORECASE）
    - ルール順は辞書定義順（長い語→短い語）を尊重
    """
    # 語境界：英数字/アンダースコアに挟まれていないトークン
    boundary = r"(?<![A-Za-z0-9_]){tok}(?![A-Za-z0-9_])"

    rules: List[Tuple[str, re.Pattern[str], str]] = []

    for key, token, replacement in ALPHA_ABBREV_RULES:
        pat = re.compile(
            boundary.format(tok=re.escape(token)),
            flags=re.IGNORECASE,
        )
        rules.append((key, pat, replacement))

    return rules



_RULES = _compile_rules()


# ============================================================
# 正規化API（正本）
# ============================================================

def normalize_alpha_abbrev(text: str) -> Tuple[str, List[AlphaAbbrevRewriteHit]]:
    """
    アルファベット略語・記号トークンを機械的に正規化する（LLM前段用）。

    Parameters
    ----------
    text : str
        入力テキスト（例：ユーザー質問）

    Returns
    -------
    normalized_text : str
        置換後テキスト
    report : List[AlphaAbbrevRewriteHit]
        どのルールが何回当たったか（要約）
    """
    s = (text or "")
    if not s:
        return s, []

    counts: Dict[str, int] = {}
    out = s

    # ------------------------------------------------------------
    # 置換適用（ルール順は重要：長い語→短い語）
    # ------------------------------------------------------------
    for key, pat, repl in _RULES:
        out2, n = pat.subn(repl, out)
        if n:
            counts[key] = counts.get(key, 0) + n
        out = out2

    report: List[AlphaAbbrevRewriteHit] = []
    for key, pat, repl in _RULES:
        c = counts.get(key, 0)
        if c:
            report.append(AlphaAbbrevRewriteHit(key=key, replacement=repl, count=c))

    return out, report
