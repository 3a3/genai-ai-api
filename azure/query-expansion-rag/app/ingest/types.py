"""ingest パイプラインで使う共通データ型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DocType = Literal["rules", "qa"]


@dataclass
class SourceFile:
    """原本ファイル（Blob 単位）。"""

    blob_path: str        # 例: "rules/2026/general.pdf"
    content: bytes
    mime_type: str        # 検証層が決定
    doc_type: DocType     # "rules" / "qa"
    source_hash: str      # 更新検知用 (SHA-256)


@dataclass
class Section:
    """ローダーが原本から抽出した論理セクション。

    PDF なら条文単位、Excel なら 1 行単位。
    """

    text: str
    title: str = ""        # 例: "第3条 保険金の支払"
    section: str = ""      # 例: "第3条"
    page: int | None = None
    locator: str = ""      # 例: "sheet=Sheet1#row=42"
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class Chunk:
    """埋め込み対象の最終チャンク。"""

    id: str                # SHA-256(source_path + chunk_index)
    content: str
    source_path: str
    source_locator: str
    source_hash: str
    doc_type: DocType
    title: str
    section: str
    page: int | None
    chunk_index: int


@dataclass
class EmbeddedChunk(Chunk):
    """embedding 済みチャンク。AI Search に投入する形。"""

    content_vector: list[float] = field(default_factory=list)


@dataclass
class IngestStats:
    """1 実行の集計。"""

    added: int = 0
    updated: int = 0
    deleted: int = 0
    failed: int = 0
    total: int = 0
