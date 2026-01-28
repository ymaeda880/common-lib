# -*- coding: utf-8 -*-
# common_lib/io/__init__.py
# ============================================================
# I/O（正本：UI非依存）
# - 文書コンテキスト（前提文書）の読み込みを common_lib に集約
# - ページ側は UI + session_state のみ
# ============================================================



from __future__ import annotations

# ------------------------------------------------------------
# re-export（高レベルAPI）
# ------------------------------------------------------------
from common_lib.io.doc_context import (  # noqa: F401
    read_doc_context_from_bytes,
    read_doc_context_from_text,
)

# ------------------------------------------------------------
# re-export（型）
# ------------------------------------------------------------
from common_lib.io.doc_context_types import (  # noqa: F401
    DocContext,
    DocContextMeta,
)

# ============================================================
# common_lib/io  ― 文書読込（前提文書）I/O 正本
# ============================================================
#
# ■ 目的（Why this exists）
# ------------------------------------------------------------
# このディレクトリは、AI 実行時に用いる「前提文書（doc_context）」を
# 安全かつ一貫した形でテキスト化するための、UI 非依存の正本 I/O レイヤです。
#
# - pages/* に分散していた docx / txt / md / json / pdf の読込ロジックを集約
# - 同じ入力 → 同じ前提文書 を保証し、静かな不整合・再現性崩壊を防ぐ
# - ページ側は UI と session_state 管理のみに専念させる
#
# ※ ここは「意味解釈・要約・AIロジック」を行う場所ではありません。
#    やるのは「入力 → テキスト化 → 正規化 → 明示的な成功/失敗」のみです。
#
#
# ■ 全体構造（Layered Design）
# ------------------------------------------------------------
# pages/*
#   └─ UI / session_state / 表示のみ
#        ↓
# common_lib/io/doc_context.py      ← 正本入口（ページはここだけ呼ぶ）
#        ↓
# common_lib/io/readers/*           ← 形式別 reader（docx/json/pdf/txt/md）
#        ↓
# common_lib/io/decode.py           ← bytes → str の正本 decode
# common_lib/io/normalize.py        ← 改行・最大文字数など共通正規化
# common_lib/io/text.py             ← 低レベル text ユーティリティ（既存）
#
#
# ■ 正本 API（ページが呼ぶもの）
# ------------------------------------------------------------
# ● ファイル入力
#   - 入力: file_name + bytes
#   - 出力: DocContext(kind, text, meta)
#   - 拡張子分岐・decode・抽出・正規化・判定はすべて common_lib 側で行う
#
# ● 貼り付け入力
#   - 入力: raw_text (str)
#   - 出力: DocContext(kind, text, meta)
#
# ページ側の禁止事項：
#   - 拡張子分岐をしない
#   - decode をしない
#   - docx / json / pdf を直接触らない
#   - OCR 判定や例外握りをしない
#
#
# ■ 出力構造（DocContext）
# ------------------------------------------------------------
# kind : str
#   表示用の文書種別ラベル（Word / JSON / PDF / Text / Pasted 等）
#
# text : str
#   AI に渡す前提文書テキスト
#
# meta : dict
#   処理結果・警告・判定理由・制約を含むメタ情報
#
# meta の目的：
#   - 「なぜこの結果になったか」を後から必ず説明できること
#   - 静かに失敗しないこと
#
#
# ■ 形式別仕様（正本）
# ------------------------------------------------------------
#
# 【Word (.docx)】
# - python-docx 必須
# - 段落（paragraphs）のみ抽出
# - 空段落は除外し、改行で連結
# - 表・ヘッダ・フッタ等は現時点では抽出しない
# - 依存不足時は明示エラー（空文字で誤魔化さない）
# - meta:
#     docx_mode="paragraphs"
#     warnings=["docx_tables_not_included"]
#
#
# 【テキスト (.txt / .md)】
# - bytes → UTF-8 decode
# - decode 正本方針：
#     * UTF-8（BOM対応）を優先
#     * 失敗時は replace
#     * ignore は使用しない（静かな欠落を防ぐ）
# - markdown はそのままテキストとして扱う
#
#
# 【JSON (.json)】
# - decode → JSON パースを試行
# - パースできる場合：
#     * 構造を壊さず、indent=2 / ensure_ascii=False で整形してテキスト化
# - パースできない場合：
#     * 正本仕様としてエラー停止（厳格）
#
# 「JSONはパースできるなら整形して渡す」とは：
#   JSON の構造を保持したまま、人間・AI が読みやすい
#   構造化テキストに戻すことを意味する
#
#
# 【PDF (.pdf)】
# - text layer（文字レイヤー）のみ抽出
# - OCR は現時点では行わない（将来対応予定）
#
# 画像PDF判定（B案・正本）：
# - 抽出後、空白除去した有効文字数 < 50 の場合
#     → 画像（スキャン）PDF扱い
#     → 明示エラー
#
# - meta:
#     pdf_mode="text_only"
#     pdf_text_threshold=50
#     pdf_seems_image_based=True / False
#     ocr_supported=False
#
#
# ■ 共通正規化（全形式）
# ------------------------------------------------------------
# - 改行正規化（CRLF / CR → LF）
# - BOM / ゼロ幅文字の除去（必要に応じて）
# - 最大文字数制限（例: 15000 chars）
#     * 超過時は先頭からカット
#     * meta.truncated=True を必ず残す
#
#
# ■ エラー方針（最重要）
# ------------------------------------------------------------
# - 静かに空文字を返さない
# - 読めない / 依存不足 / 画像PDF は必ずエラー
# - ページ側は判断しない（エラー文言を表示するのみ）
#
#
# ■ py（pages/*）からの呼び方（要点）
# ------------------------------------------------------------
# ファイル入力：
#   dc = read_doc_context_from_bytes(file_name=uploaded.name, data=uploaded.read())
#   st.session_state["doc_context"] = dc.to_dict()
#
# 貼り付け入力：
#   dc = read_doc_context_from_text(raw_text=pasted_text)
#   st.session_state["doc_context"] = dc.to_dict()
#
# 例外時：
#   try / except でエラーメッセージを UI 表示するのみ
#
#
# ■ 禁止事項（この層でやらないこと）
# ------------------------------------------------------------
# - 要約・意味解釈・AI 呼び出し
# - UI / Streamlit 依存
# - ページ固有の例外握り
#
#
# ■ 設計思想（将来の自分へ）
# ------------------------------------------------------------
# - この層は「前提文書の事実」を作る場所
# - 品質を落とすより、止める方が正しい
# - 仕様変更は 1 か所で全ページに効くようにする
# - OCR・表対応は後付け可能な設計にしてある
#
# ============================================================


# ============================================================
# ■ py（pages/*）からの呼び方（実装者向けまとめ）
# ============================================================
#
# ページ側の役割は「UI → common_lib に渡す → session_state に保存」だけ。
# 拡張子分岐・decode・抽出・判定ロジックは一切書かない。
#
#
# ------------------------------------------------------------
# 1) ファイルアップロード（docx / txt / md / json / pdf）
# ------------------------------------------------------------
#
# Streamlit の file_uploader が返す UploadedFile をそのまま使う。
#
# 例：
#
#   from common_lib.io import read_doc_context_from_bytes
#
#   uploaded = st.file_uploader(
#       "前提文書",
#       type=["docx", "txt", "md", "json", "pdf"],
#   )
#
#   if uploaded is not None:
#       try:
#           dc = read_doc_context_from_bytes(
#               file_name=uploaded.name,
#               data=uploaded.read(),
#               max_chars=15000,   # 省略可（正本の既定値を使う場合）
#           )
#           # 正本形式で保存
#           st.session_state["doc_context"] = dc.to_dict()
#       except Exception as e:
#           # ページ側は判断しない。表示のみ。
#           st.error(str(e))
#
#
# ------------------------------------------------------------
# 2) テキスト貼り付け（raw text）
# ------------------------------------------------------------
#
# 貼り付け入力は file とは別 API を使う。
#
# 例：
#
#   from common_lib.io import read_doc_context_from_text
#
#   pasted = st.text_area("前提文書（貼り付け）")
#
#   if st.button("この文書をセット"):
#       try:
#           dc = read_doc_context_from_text(
#               raw_text=pasted,
#               max_chars=15000,          # 省略可
#               kind="貼り付けテキスト"   # 表示用ラベル（省略可）
#           )
#           st.session_state["doc_context"] = dc.to_dict()
#       except Exception as e:
#           st.error(str(e))
#
#
# ------------------------------------------------------------
# 3) session_state の正本構造
# ------------------------------------------------------------
#
# ページ側では、保存形式を以下に固定する：
#
#   st.session_state["doc_context"] = {
#       "kind": <str>,
#       "text": <str>,
#       "meta": <dict>,
#   }
#
# - kind : 表示用（「Word(.docx)」「PDF(.pdf)」など）
# - text : AI に渡す前提文書テキスト
# - meta : truncate / pdf判定 / 警告などの再現性情報
#
#
# ------------------------------------------------------------
# 4) チャット・生成処理での利用
# ------------------------------------------------------------
#
# AI 実行時は、ページ側で doc_context を参照して prompt を組み立てる。
#
# 例（イメージ）：
#
#   ctx = st.session_state.get("doc_context")
#   if ctx:
#       kind = ctx.get("kind", "")
#       text = ctx.get("text", "")
#       prompt = f"【前提文書：{kind}】\n{text}\n\n" + user_prompt
#
# ※ meta は必要な場合のみ UI 表示やログに使用する。
#
#
# ------------------------------------------------------------
# 5) ページ側の禁止事項（再掲）
# ------------------------------------------------------------
#
# ページ側で以下を行ってはいけない：
#
# - 拡張子分岐（docx/json/pdf の判定）
# - bytes decode（utf-8 / shift_jis 等）
# - json.loads / docx.Document / PDF 抽出
# - OCR 判定・文字数閾値判定
# - 失敗時に空文字で続行する処理
#
# これらはすべて common_lib/io が正本。
#
# ============================================================

