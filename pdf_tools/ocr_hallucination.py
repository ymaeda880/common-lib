# -*- coding: utf-8 -*-
# common_lib/pdf_tools/ocr_hallucination.py
# ============================================================
# OCRハルシネーション判定 共通処理
#
# 機能：
# - PDFページから本文由来dark pixelsを取得する
# - 外周・ページ番号領域・長い水平線・垂直線を除外する
# - OCR結果の実文字数を取得する
# - GPT Vision OCRのハルシネーション疑いをS1/S2/S3で判定する
#
# 方針：
# - 報告書・契約書から共通利用する
# - 判定対象はGPT Vision OCRのみとする
# - S1/S2/S3の閾値は現在の報告書OCRの判定条件を維持する
# - 判定結果は確定的なハルシネーションではなく「疑い」とする
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================

from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any


# ============================================================
# public：本文由来の画像濃度
# ============================================================

def get_page_content_dark_density(
    *,
    fitz: Any,
    pdf_bytes: bytes,
    page_no: int,
    render_dpi: int = 72,
    dark_threshold: int = 220,
) -> dict[str, float | int]:
    # ------------------------------------------------------------
    # 外周・ページ番号領域・長い罫線を除外して，
    # 本文・図表由来と考えられるdark pixelsを取得する
    # ------------------------------------------------------------
    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    try:
        page = document.load_page(
            int(page_no) - 1
        )

        scale = float(render_dpi) / 72.0

        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            colorspace=fitz.csGRAY,
            alpha=False,
        )

        width = int(pixmap.width)
        height = int(pixmap.height)
        samples = pixmap.samples

        # --------------------------------------------------------
        # 本文候補領域
        #
        # 左右・上の外周を少し除外し，
        # 下部10%はページ番号領域として除外する
        # --------------------------------------------------------
        x1 = int(width * 0.05)
        x2 = int(width * 0.95)
        y1 = int(height * 0.05)
        y2 = int(height * 0.90)

        dark_map: list[list[bool]] = []

        for y in range(y1, y2):
            row_offset = y * width

            dark_map.append([
                int(samples[row_offset + x]) < int(dark_threshold)
                for x in range(x1, x2)
            ])

        region_height = len(dark_map)
        region_width = (
            len(dark_map[0])
            if dark_map
            else 0
        )

        if region_height <= 0 or region_width <= 0:
            return {
                "content_dark_pixels": 0,
                "content_pixel_count": 0,
                "content_dark_ratio": 0.0,
            }

        # --------------------------------------------------------
        # 長い水平線を除外
        # --------------------------------------------------------
        horizontal_limit = int(
            region_width * 0.50
        )

        for row in dark_map:
            run_start = None

            for x in range(region_width + 1):
                is_dark = (
                    x < region_width
                    and row[x]
                )

                if is_dark and run_start is None:
                    run_start = x

                elif not is_dark and run_start is not None:
                    run_length = x - run_start

                    if run_length >= horizontal_limit:
                        for xx in range(run_start, x):
                            row[xx] = False

                    run_start = None

        # --------------------------------------------------------
        # 長い垂直線を除外
        # --------------------------------------------------------
        vertical_limit = int(
            region_height * 0.50
        )

        for x in range(region_width):
            run_start = None

            for y in range(region_height + 1):
                is_dark = (
                    y < region_height
                    and dark_map[y][x]
                )

                if is_dark and run_start is None:
                    run_start = y

                elif not is_dark and run_start is not None:
                    run_length = y - run_start

                    if run_length >= vertical_limit:
                        for yy in range(run_start, y):
                            dark_map[yy][x] = False

                    run_start = None

        content_dark_pixels = sum(
            1
            for row in dark_map
            for value in row
            if value
        )

        content_pixel_count = (
            region_width * region_height
        )

        return {
            "content_dark_pixels": content_dark_pixels,
            "content_pixel_count": content_pixel_count,
            "content_dark_ratio": (
                content_dark_pixels / content_pixel_count
                if content_pixel_count > 0
                else 0.0
            ),
        }

    finally:
        document.close()


# ============================================================
# public：OCR文字密度
# ============================================================

def get_ocr_text_density(
    *,
    text: str,
    pixel_count: int,
) -> dict[str, float | int]:
    # ------------------------------------------------------------
    # OCR結果の実文字数から文字密度を取得する
    #
    # 空白・改行は文字量に含めない．
    # ------------------------------------------------------------
    normalized = re.sub(
        r"\s+",
        "",
        str(text or ""),
    )

    char_count = len(normalized)

    text_density = (
        char_count / int(pixel_count)
        if int(pixel_count) > 0
        else 0.0
    )

    return {
        "char_count": char_count,
        "text_density": text_density,
    }


# ============================================================
# public：OCRハルシネーション判定
# ============================================================

def get_hallucination_result(
    *,
    method: str,
    content_dark_pixels: int,
    ocr_char_count: int,
) -> tuple[bool, str]:
    # ------------------------------------------------------------
    # GPT Vision OCRについて，
    # 元画像の本文情報量とOCR文字量の不整合を多段階で判定する
    #
    # 戻り値：
    # - bool：ハルシネーション疑いの有無
    # - str ：人手確認用の判定理由
    #
    # S1は既存条件をそのまま維持する．
    # S2・S3は950_ハルシネーション.pyの検証結果に基づく．
    # ------------------------------------------------------------
    if str(method or "").strip() != "gpt_vision":
        return False, ""

    dark_pixels = int(content_dark_pixels)
    char_count = int(ocr_char_count)

    # --------------------------------------------------------
    # S1：既存条件
    #
    # 本文由来dark pixelsが0なのに，
    # GPT OCRが10文字以上を生成している．
    # --------------------------------------------------------
    if (
        dark_pixels == 0
        and char_count >= 10
    ):
        return (
            True,
            (
                "S1：元画像の本文由来dark pixelsが0ですが，"
                f"GPT OCRが{char_count:,}文字を生成しました．"
            ),
        )

    # --------------------------------------------------------
    # S2：本文情報が極端に少ない
    #
    # 本文由来dark pixelsが1～500しかないのに，
    # GPT OCRが10文字以上を生成している．
    # --------------------------------------------------------
    if (
        0 < dark_pixels <= 500
        and char_count >= 10
    ):
        return (
            True,
            (
                "S2：元画像の本文由来dark pixelsが"
                f"{dark_pixels:,}と極端に少ないですが，"
                f"GPT OCRが{char_count:,}文字を生成しました．"
            ),
        )

    # --------------------------------------------------------
    # S3：画像情報量に対してOCR文字量が異常に多い
    #
    # 本文由来dark pixelsが500を超えている場合でも，
    # OCR文字数 / dark pixels が0.05以上なら疑いとする．
    #
    # 950での確認値：
    # - 正常1行      ：約0.0171
    # - 正常複数行  ：約0.0135
    # - 1行＋75文字：約0.0512
    # --------------------------------------------------------
    if (
        dark_pixels > 500
        and char_count >= 10
        and (
            char_count
            / dark_pixels
        ) >= 0.05
    ):
        ocr_ratio = (
            char_count
            / dark_pixels
        )

        return (
            True,
            (
                "S3：画像情報量に対してOCR文字量が"
                "異常に多い可能性があります．"
                f" dark pixels={dark_pixels:,}，"
                f"OCR文字数={char_count:,}，"
                f"OCR比率={ocr_ratio:.6f}"
            ),
        )

    return False, ""


# ============================================================
# public：ハルシネーション疑いログ保存
# ============================================================

def append_hallucination_log(
    *,
    log_path: Path,
    document_type: str,
    project_year: int,
    project_no: str,
    page_no: int,
    method: str,
    model: str,
    reason: str,
    content_dark_pixels: int,
    ocr_char_count: int,
    detected_by: str,
    action: str = "ocr_text_not_saved",
    review_status: str = "unreviewed",
) -> None:
    # ------------------------------------------------------------
    # OCRハルシネーション疑いに関する履歴を保存する．
    #
    # 一括OCRで疑いを検出して保存を止めた場合は，
    # action="ocr_text_not_saved"，
    # review_status="unreviewed" として記録する．
    #
    # 人手確認後に白紙として確定した場合は，
    # action="confirmed_blank"，
    # review_status="confirmed_blank" として記録する．
    #
    # 疑わしいOCR本文そのものはログへ保存しない．
    # ------------------------------------------------------------
    log_path = Path(log_path)

    if log_path.exists():
        try:
            payload = json.loads(
                log_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise RuntimeError(
                f"ハルシネーションログを読めません． path={log_path}"
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(
                f"ハルシネーションログ形式が不正です． path={log_path}"
            )
    else:
        payload = {
            "version": 1,
            "document_type": str(document_type),
            "events": [],
        }

    events = payload.get("events")

    if not isinstance(events, list):
        raise RuntimeError(
            f"ハルシネーションログのeventsが不正です． path={log_path}"
        )

    reason_value = str(reason or "")
    stage = ""

    for candidate in ("S1", "S2", "S3"):
        if reason_value.startswith(f"{candidate}："):
            stage = candidate
            break

    events.append(
        {
            "detected_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "document_type": str(document_type),
            "project_year": int(project_year),
            "project_no": str(project_no),
            "page_no": int(page_no),
            "method": str(method),
            "model": str(model or ""),
            "stage": stage,
            "reason": reason_value,
            "content_dark_pixels": int(content_dark_pixels),
            "ocr_char_count": int(ocr_char_count),
            "action": str(action or ""),
            "review_status": str(review_status or ""),
            "detected_by": str(detected_by or ""),
        }
    )

    payload["version"] = 1
    payload["document_type"] = str(document_type)
    payload["events"] = events

    log_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = log_path.with_suffix(
        log_path.suffix + ".tmp"
    )

    tmp_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    tmp_path.replace(log_path)