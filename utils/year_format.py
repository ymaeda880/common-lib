# -*- coding: utf-8 -*-
# common_lib/utils/year_format.py
# ============================================================
# 年度の表示変換（Streamlit・DBに依存しない共通関数）
# ============================================================

from __future__ import annotations


def format_project_year_legacy(year: int | str | None) -> str:
    """西暦4桁の年度を、プロジェクトで使う旧表記に変換する。

    1972〜1988年度: S47〜S63
    1989〜2018年度: H01〜H30（1〜9年も必ず2桁）
    2019年度以降: 西暦4桁のまま

    変換規則のない1971年度以前も、西暦4桁をそのまま返す。
    空欄・None・不正入力は空文字を返し、入力途中の表示にも使える。
    元の年度データは変更せず、表示用の文字列だけを返す。
    """
    # 小数や真偽値を年度として暗黙に変換しない。
    if isinstance(year, bool) or not isinstance(year, (int, str)):
        return ""

    # 入力欄の文字列と、DBなどの整数値の両方を受け付ける。
    text = str(year).strip()
    if len(text) != 4 or not text.isdecimal():
        return ""
    year_value = int(text)
    if not 1000 <= year_value <= 9999:
        return ""

    # 年度単位の指定なので、1989年度は一律H01、2019年度は西暦。
    if 1972 <= year_value <= 1988:
        return f"S{year_value - 1925:02d}"
    if 1989 <= year_value <= 2018:
        return f"H{year_value - 1988:02d}"

    # 指定範囲外の年度について、別の元号変換を推測で追加しない。
    return f"{year_value:04d}"
