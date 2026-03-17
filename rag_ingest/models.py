# common_lib/rag_ingest/models.py
# =============================================================================
# RAG ingest 共通データ構造
#
# 役割：
# - RAG ingest 共通基盤で使う dataclass を定義する
# - collection_id / shard_id / doc_id / attrs を中心にした抽象モデルを持つ
# - project / rules など個別ドメインに依存しない共通表現を提供する
#
# 方針：
# - year / pno のようなドメイン固有属性は attrs に入れる
# - path は原則としてルート相対パス文字列で保持する
# - meta / processed / 実行結果の正本データ構造をここに集約する
# =============================================================================

from __future__ import annotations

# =============================================================================
# imports
# =============================================================================
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional


# =============================================================================
# type aliases
# =============================================================================
IngestStatus = Literal["ok", "skip", "error"]
SourceTextKind = Literal["raw", "clean", "other"]
YesNo = Literal["yes", "no"]


# =============================================================================
# 共通ヘルパ
# =============================================================================
def _safe_attrs(attrs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    # -----------------------------------------------------------------------------
    # attrs を必ず dict に正規化する
    # -----------------------------------------------------------------------------
    if isinstance(attrs, dict):
        return dict(attrs)
    return {}


# =============================================================================
# 文書ソース情報
# =============================================================================
@dataclass(slots=True)
class IngestSource:
    # -----------------------------------------------------------------------------
    # 1文書を ingest するために必要な「解決済みソース情報」
    #
    # 例：
    # - collection_id = "project"
    # - shard_id      = "2019"
    # - doc_id        = "2019/009/xxx.pdf"
    #
    # source_pdf_path / source_text_path / source_pages_path は
    # ルート相対パスを想定する。
    # attrs には year / pno / ocr などドメイン固有情報を持たせる。
    # -----------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    doc_id: str

    file: str
    file_name: str

    source_pdf_path: str
    source_text_path: str
    source_pages_path: str
    source_text_kind: SourceTextKind

    input_text: str

    sha256: str
    embed_model: str

    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # -------------------------------------------------------------------------
        # attrs 正規化
        # -------------------------------------------------------------------------
        self.attrs = _safe_attrs(self.attrs)

    def to_dict(self) -> Dict[str, Any]:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return asdict(self)


# =============================================================================
# chunk情報
# =============================================================================
@dataclass(slots=True)
class ChunkRecord:
    # -----------------------------------------------------------------------------
    # chunk_ops が返す chunk 情報
    #
    # page 依存を避けるため、chunk_id はここではまだ持たない。
    # chunk_id は manifest_ops 側で doc_id + chunk_index から採番する想定。
    # -----------------------------------------------------------------------------
    chunk_index: int
    text: str
    span_start: int
    span_end: int
    chunk_len_tokens: int

    def to_dict(self) -> Dict[str, Any]:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return asdict(self)


# =============================================================================
# meta.jsonl 1行分
# =============================================================================
@dataclass(slots=True)
class MetaRecord:
    # -----------------------------------------------------------------------------
    # vectors.npy の1行に対応する chunk metadata
    #
    # 重要：
    # - vectors.npy の i 行目 <-> meta.jsonl の i 行目
    # - attrs にドメイン固有情報を保持する
    # -----------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    doc_id: str

    file: str
    file_name: str

    chunk_id: str
    chunk_index: int

    vector_index: int

    text: str
    span_start: int
    span_end: int
    chunk_len_tokens: int

    page_start: int
    page_end: int

    source_pdf_path: str
    source_text_path: str
    source_pages_path: str
    source_text_kind: SourceTextKind

    sha256: str
    embed_model: str
    ingested_at: str

    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # -------------------------------------------------------------------------
        # attrs 正規化
        # -------------------------------------------------------------------------
        self.attrs = _safe_attrs(self.attrs)

    def to_dict(self) -> Dict[str, Any]:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return asdict(self)


# =============================================================================
# processed_files.json 1件分
# =============================================================================
@dataclass(slots=True)
class ProcessedFileRecord:
    # -----------------------------------------------------------------------------
    # 文書単位の ingest 記録
    #
    # 用途：
    # - 未処理だけ追加
    # - 同名差し替え検知（sha256）
    # - どの source_text / model で ingest したかの追跡
    # -----------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    doc_id: str

    file: str

    sha256: str

    source_pdf_path: str
    source_text_path: str
    source_text_kind: SourceTextKind

    embed_model: str
    ingested_at: str

    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # -------------------------------------------------------------------------
        # attrs 正規化
        # -------------------------------------------------------------------------
        self.attrs = _safe_attrs(self.attrs)

    def to_dict(self) -> Dict[str, Any]:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return asdict(self)


# =============================================================================
# embedding 実行結果（共通基盤側で扱う要約）
# =============================================================================
@dataclass(slots=True)
class EmbeddingRunResult:
    # -----------------------------------------------------------------------------
    # embedding_ops が返す要約結果
    #
    # vectors は chunk 順に並ぶ 2次元 list[ list[float] ] を想定する。
    # in_tokens / out_tokens / cost は取得できた場合のみ埋める。
    # run_id は busy_run の run_id を保持する。
    # -----------------------------------------------------------------------------
    provider: str
    model: str
    vectors: List[List[float]]

    dimension: int
    n_items: int

    run_id: Optional[str] = None
    in_tokens: Optional[int] = None
    out_tokens: Optional[int] = None
    cost_obj: Any = None

    def to_dict(self) -> Dict[str, Any]:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return asdict(self)


# =============================================================================
# 1文書 ingest の戻り値
# =============================================================================
@dataclass(slots=True)
class IngestResult:
    # -----------------------------------------------------------------------------
    # ingest_usecase / rebuild_usecase が返す共通結果
    # -----------------------------------------------------------------------------
    status: IngestStatus

    collection_id: str
    shard_id: str
    doc_id: str

    file: str
    file_name: str

    message: str

    chunk_count: int = 0
    vector_count: int = 0

    source_text_kind: Optional[SourceTextKind] = None
    source_text_path: Optional[str] = None
    source_pdf_path: Optional[str] = None

    sha256: Optional[str] = None
    embed_model: Optional[str] = None

    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # -------------------------------------------------------------------------
        # attrs 正規化
        # -------------------------------------------------------------------------
        self.attrs = _safe_attrs(self.attrs)

    def to_dict(self) -> Dict[str, Any]:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return asdict(self)


# =============================================================================
# 複数件実行の集計結果
# =============================================================================
@dataclass(slots=True)
class BatchIngestResult:
    # -----------------------------------------------------------------------------
    # batch_usecase が返す集計結果
    # -----------------------------------------------------------------------------
    total: int = 0
    ok_count: int = 0
    skip_count: int = 0
    error_count: int = 0

    results: List[IngestResult] = field(default_factory=list)

    def add(self, result: IngestResult) -> None:
        # -------------------------------------------------------------------------
        # 結果1件を追加して集計更新
        # -------------------------------------------------------------------------
        self.results.append(result)
        self.total += 1

        if result.status == "ok":
            self.ok_count += 1
        elif result.status == "skip":
            self.skip_count += 1
        else:
            self.error_count += 1

    def to_dict(self) -> Dict[str, Any]:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return {
            "total": self.total,
            "ok_count": self.ok_count,
            "skip_count": self.skip_count,
            "error_count": self.error_count,
            "results": [x.to_dict() for x in self.results],
        }


# =============================================================================
# vectorstore 読み込み結果
# =============================================================================
@dataclass(slots=True)
class VectorStoreSnapshot:
    # -----------------------------------------------------------------------------
    # vectorstore_io が shard 読み込み時に返すスナップショット
    #
    # vectors:
    #   2次元配列相当（numpy array を直接入れてもよいし list でもよい）
    #
    # meta_records / processed_records:
    #   正本 dataclass の list
    # -----------------------------------------------------------------------------
    vectors: Any
    meta_records: List[MetaRecord] = field(default_factory=list)
    processed_records: List[ProcessedFileRecord] = field(default_factory=list)

    def meta_count(self) -> int:
        # -------------------------------------------------------------------------
        # meta件数
        # -------------------------------------------------------------------------
        return len(self.meta_records)

    def processed_count(self) -> int:
        # -------------------------------------------------------------------------
        # processed件数
        # -------------------------------------------------------------------------
        return len(self.processed_records)


# =============================================================================
# selector ベース削除条件（将来拡張用）
# =============================================================================
@dataclass(slots=True)
class DeleteSelector:
    # -----------------------------------------------------------------------------
    # rebuild / delete 系で使う選択条件
    #
    # 初期実装では主に doc_id を使う想定だが、
    # 将来 attrs 条件などでの削除にも拡張しやすい形で定義しておく。
    # -----------------------------------------------------------------------------
    collection_id: str
    shard_id: str
    doc_id: Optional[str] = None
    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # -------------------------------------------------------------------------
        # attrs 正規化
        # -------------------------------------------------------------------------
        self.attrs = _safe_attrs(self.attrs)

    def to_dict(self) -> Dict[str, Any]:
        # -------------------------------------------------------------------------
        # dict 変換
        # -------------------------------------------------------------------------
        return asdict(self)