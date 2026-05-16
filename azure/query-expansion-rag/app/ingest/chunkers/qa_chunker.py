"""QA 用のチャンカー。

戦略:
- 1 Section（= Excel 1 行）= 1 Chunk
- title は質問の先頭 120 文字
- 例外的に長い QA（5000+ 文字）はそのまま 1 chunk として扱う（QA は通常短い前提）
"""

from __future__ import annotations

import hashlib
from typing import Iterable

from ..types import Chunk, Section, SourceFile


def _make_id(source_path: str, chunk_index: int) -> str:
    return hashlib.sha256(f"{source_path}#{chunk_index}".encode()).hexdigest()


def chunk_qa(source: SourceFile, sections: Iterable[Section]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for idx, sec in enumerate(sections):
        chunks.append(
            Chunk(
                id=_make_id(source.blob_path, idx),
                content=sec.text,
                source_path=source.blob_path,
                source_locator=sec.locator,
                source_hash=source.source_hash,
                doc_type=source.doc_type,
                title=sec.title[:120] if sec.title else "",
                section="",
                page=None,
                chunk_index=idx,
            )
        )
    return chunks
