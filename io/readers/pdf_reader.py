# -*- coding: utf-8 -*-
# common_lib/io/readers/pdf_reader.py
# ============================================================
# .pdf reader（UI非依存）
#
# 方針（正本）：
# - まず PyMuPDF（fitz）で text layer を抽出（日本語の復元に強い）
# - 次に pypdf（推奨）/ PyPDF2 でフォールバック抽出
# - B案：有効文字数（空白除去） < threshold(=50) なら画像PDF扱いでエラー
# - 文字化け（ToUnicode復元失敗）も検出してエラー（将来OCRへ）
#
# 依存：
# - 推奨：pymupdf
# - 代替：pypdf / PyPDF2
# ============================================================

from __future__ import annotations

import re
from typing import Tuple

from common_lib.io.readers.pdf_policy import PdfPolicy


# ============================================================
# helpers（有効文字数カウント用）
# ============================================================
def _strip_whitespace_for_count(s: str) -> str:
    if not s:
        return ""
    return (
        s.replace(" ", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace("\t", "")
        .replace("\u3000", "")
    )


# ============================================================
# helpers（文字化け判定：日本語比率）
# - 「文字数はあるのに読めない」を弾く
# - 将来OCRに回すための判定材料
# ============================================================
_RE_JA = re.compile(r"[ぁ-んァ-ヶ一-龥々ー]")
_RE_LETTERS = re.compile(r"[A-Za-zΑ-Ωα-ω]")  # ラテン/ギリシャ（化けやすい）


def _is_mojibake_like(text: str, *, min_len: int = 200, ja_ratio_min: float = 0.05) -> bool:
    """
    文字化けっぽいPDF抽出を検出する（ヒューリスティック）。
    - 有効文字が十分あるのに日本語比率が極端に低い場合を弾く。

    min_len:
      有効文字数がこの値未満なら判定しない（短文PDFで誤判定しない）
    ja_ratio_min:
      日本語比率の下限
    """
    effective = _strip_whitespace_for_count(text)
    if len(effective) < min_len:
        return False

    ja = len(_RE_JA.findall(effective))
    total = len(effective)
    if total <= 0:
        return False

    ja_ratio = ja / total
    if ja_ratio >= ja_ratio_min:
        return False

    # 追加の状況証拠：ラテン/ギリシャが多い（DXɾAI΁ͷ... みたいなケース）
    letters = len(_RE_LETTERS.findall(effective))
    # 日本語が少なく、記号・文字が多い → 化けの可能性が高い
    if letters >= int(total * 0.10):
        return True

    # 文字がほぼ日本語ゼロでも、他が多ければ化け扱い
    return ja <= 5


# ============================================================
# extractors
# ============================================================
def _extract_with_pymupdf(data: bytes) -> str:
    """
    PyMuPDF（fitz）で text 抽出。
    """
    try:
        import fitz  # type: ignore  # PyMuPDF
    except Exception as e:
        raise RuntimeError("PyMuPDF（pymupdf）が未インストールです。") from e

    doc = fitz.open(stream=data, filetype="pdf")
    parts = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        t = page.get_text("text") or ""
        if t:
            parts.append(t)
    doc.close()
    return "\n".join(parts)


def _extract_with_pypdf_or_pypdf2(data: bytes) -> str:
    """
    pypdf / PyPDF2 で text 抽出（フォールバック）。
    """
    PdfReader = None
    try:
        from pypdf import PdfReader as _PdfReader  # type: ignore
        PdfReader = _PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader as _PdfReader  # type: ignore
            PdfReader = _PdfReader
        except Exception as e:
            raise RuntimeError(
                "PDF の text 抽出には pypdf（推奨）または PyPDF2 が必要です。（OCRは未対応）"
            ) from e

    from io import BytesIO

    reader = PdfReader(BytesIO(data))
    parts = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t:
            parts.append(t)
    return "\n".join(parts)


# ============================================================
# reader（正本）
# ============================================================
def read_pdf_bytes_text_only(
    data: bytes,
    *,
    policy: PdfPolicy,
) -> Tuple[str, int, bool]:
    """
    PDF bytes から text layer のみ抽出する（OCRしない）。

    Returns
    -------
    (text, extracted_chars, seems_image_based)

    Raises
    ------
    RuntimeError:
      - 依存不足
      - 画像PDF扱い（B案：< threshold）
      - 文字化け扱い（日本語比率が極端に低い）
    """
    # ------------------------------------------------------------
    # 1) まず PyMuPDF（日本語に強い）
    # ------------------------------------------------------------
    text = ""
    try:
        text = _extract_with_pymupdf(data)
    except Exception:
        text = ""

    # ------------------------------------------------------------
    # 2) フォールバック：pypdf / PyPDF2
    # ------------------------------------------------------------
    if not (text or "").strip():
        text = _extract_with_pypdf_or_pypdf2(data)

    extracted_chars = len(text)

    # ------------------------------------------------------------
    # B案：画像PDF判定（有効文字数 < threshold）
    # ------------------------------------------------------------
    effective = _strip_whitespace_for_count(text)
    seems_image_based = (len(effective) < int(policy.text_threshold))

    if seems_image_based:
        raise RuntimeError(
            "PDF から十分なテキストを抽出できませんでした。"
            "このPDFは画像（スキャン）ベースの可能性が高く、"
            "現仕様（text layer のみ）では扱えません。"
            "（OCRは将来対応予定）"
        )

    # ------------------------------------------------------------
    # 文字化け判定（ToUnicode復元失敗っぽい場合）
    # ------------------------------------------------------------
    if _is_mojibake_like(text):
        raise RuntimeError(
            "PDF からテキストは抽出できましたが、文字化けの可能性が高いため前提文書として採用しません。"
            "（このPDFはフォントの文字マップ復元に失敗している可能性があります。OCRは将来対応予定）"
        )

    return text, extracted_chars, False
