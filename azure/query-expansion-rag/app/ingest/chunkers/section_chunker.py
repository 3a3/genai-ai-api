"""規約 PDF 用のチャンカー。

戦略:
- セクション境界（"第N条" "第N章" など）でテキストを再分割
- 検出できない場合は MAX_CHARS の固定長分割にフォールバック
- 1 chunk あたり 200〜1200 文字を目安
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

from ..types import Chunk, Section, SourceFile

# 章条の境界
# PDF からの抽出テキストは行頭にあるとは限らないため、^ は付けない。
# 「第N条（タイトル）」のパターンに限定し、ページ参照（P.数字）や短すぎる中身は除外。
_SECTION_PATTERNS = [
    # 第N条（タイトル）  ※ 中身は 3 文字以上、"P." で始まらない
    re.compile(r"第[0-9〇一二三四五六七八九十百千]+条[（(](?!P\.?\d|p\.?\d)[^()（）\n]{3,60}[)）]"),
    re.compile(r"第[0-9〇一二三四五六七八九十百千]+章[（(][^()（）\n]{3,60}[)）]"),
    re.compile(r"第[0-9〇一二三四五六七八九十百千]+節[（(][^()（）\n]{3,60}[)）]"),
]

# 固定長分割の上限
_MAX_CHARS = 1200
_MIN_CHARS = 100


def _split_by_sections(text: str) -> list[tuple[str, str]]:
    """(セクション見出し, 本文) のリストに分ける。"""
    boundaries: list[tuple[int, str]] = []
    for pat in _SECTION_PATTERNS:
        for m in pat.finditer(text):
            boundaries.append((m.start(), m.group().strip()))
    boundaries.sort()
    if not boundaries:
        return []

    chunks: list[tuple[str, str]] = []
    for i, (start, heading) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        body = text[start:end].strip()
        chunks.append((heading, body))
    return chunks


def _split_fixed(text: str, max_chars: int = _MAX_CHARS) -> list[str]:
    """改行を尊重しつつ固定長で分割。"""
    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > max_chars and len(current) >= _MIN_CHARS:
            parts.append(current.strip())
            current = line
        else:
            current += line
    if current.strip():
        parts.append(current.strip())
    return parts


def _make_id(source_path: str, chunk_index: int) -> str:
    return hashlib.sha256(f"{source_path}#{chunk_index}".encode()).hexdigest()


def chunk_sections(source: SourceFile, sections: Iterable[Section]) -> list[Chunk]:
    chunks: list[Chunk] = []
    chunk_index = 0

    # まず全 Section を縦に連結（ページ跨ぎの条文を扱うため）
    combined = "\n\n".join(s.text for s in sections)
    by_sec = _split_by_sections(combined)

    if by_sec:
        for heading, body in by_sec:
            for part in _split_fixed(body):
                chunks.append(
                    Chunk(
                        id=_make_id(source.blob_path, chunk_index),
                        content=part,
                        source_path=source.blob_path,
                        source_locator=heading,
                        source_hash=source.source_hash,
                        doc_type=source.doc_type,
                        title=heading[:120],
                        section=heading.split()[0] if heading else "",
                        page=None,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1
    else:
        # セクション検出できなければページ単位 + 固定長
        for sec in sections:
            for part in _split_fixed(sec.text):
                chunks.append(
                    Chunk(
                        id=_make_id(source.blob_path, chunk_index),
                        content=part,
                        source_path=source.blob_path,
                        source_locator=sec.locator,
                        source_hash=source.source_hash,
                        doc_type=source.doc_type,
                        title=sec.title or f"page {sec.page}" if sec.page else "",
                        section="",
                        page=sec.page,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1

    return chunks
