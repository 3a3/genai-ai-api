"""チャンカー: doc_type に応じて Section を Chunk に分割。"""

from __future__ import annotations

from ..types import Chunk, DocType, Section, SourceFile
from . import qa_chunker, section_chunker


def chunk(source: SourceFile, sections: list[Section]) -> list[Chunk]:
    if source.doc_type == "qa":
        return qa_chunker.chunk_qa(source, sections)
    return section_chunker.chunk_sections(source, sections)
