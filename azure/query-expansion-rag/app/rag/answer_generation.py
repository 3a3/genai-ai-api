"""回答生成: 検索結果を context として LLM に渡し、引用付き回答を作る。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .aoai_client import AOAIClient
from .prompts import ANSWER_GENERATION_SYSTEM
from .search import SearchHit

logger = logging.getLogger(__name__)


@dataclass
class Reference:
    number: int
    source_path: str
    source_locator: str
    title: str
    section: str
    page: int | None

    def display(self) -> str:
        loc = ""
        if self.section:
            loc = self.section
        elif self.page is not None:
            loc = f"p.{self.page}"
        elif self.source_locator:
            loc = self.source_locator
        head = f"[出典{self.number}] {self.source_path}"
        return f"{head} {loc}".strip() if loc else head


@dataclass
class AnswerResult:
    answer: str           # Markdown 回答（出典番号埋め込み済み）
    references: list[Reference]
    used_chunks: int


def _format_context(hits: list[SearchHit]) -> tuple[str, list[Reference]]:
    """context 文字列と reference リストを構築。"""
    lines: list[str] = []
    refs: list[Reference] = []
    for i, h in enumerate(hits, start=1):
        refs.append(
            Reference(
                number=i,
                source_path=h.source_path,
                source_locator=h.source_locator,
                title=h.title,
                section=h.section,
                page=h.page,
            )
        )
        header = f"[出典{i}] {h.source_path}"
        if h.section:
            header += f" / {h.section}"
        if h.page is not None:
            header += f" / p.{h.page}"
        lines.append(f"{header}\n{h.content}\n")
    return "\n".join(lines), refs


def generate_answer(
    aoai: AOAIClient,
    question: str,
    hits: list[SearchHit],
    response_footer: str = "",
) -> AnswerResult:
    if not hits:
        return AnswerResult(
            answer="該当する情報が見つかりませんでした。別の聞き方でお試しください。" + response_footer,
            references=[],
            used_chunks=0,
        )

    context, refs = _format_context(hits)
    user_msg = ANSWER_GENERATION_SYSTEM.format(context=context, question=question)
    # LLM 呼び出し（system は空、user に全部入れる）
    answer = aoai.chat(system="", user=user_msg, temperature=0.0, max_tokens=2048)

    # 参照されなかった refs を間引く
    used_numbers = {int(m.group(1)) for m in re.finditer(r"\[出典(\d+)\]", answer)}
    filtered_refs = [r for r in refs if r.number in used_numbers]

    # 参照リストを末尾に付ける
    if filtered_refs:
        refs_block = "\n\n**参考情報:**\n" + "\n".join(f"- {r.display()}" for r in filtered_refs)
        answer = answer.rstrip() + refs_block

        # 各出典のチャンク本文を Markdown blockquote で append（要約せず原文ママ）
        details_lines: list[str] = ["\n\n---\n\n### 参考した文書\n"]
        for ref in filtered_refs:
            hit = hits[ref.number - 1]  # number は 1-indexed
            heading_parts = [f"[出典{ref.number}] {hit.source_path}"]
            if hit.section:
                heading_parts.append(hit.section)
            elif hit.page is not None:
                heading_parts.append(f"p.{hit.page}")
            heading = " / ".join(heading_parts)

            quoted_lines = [
                f"> {line}" if line.strip() else ">"
                for line in hit.content.splitlines()
            ]
            quoted_content = "\n".join(quoted_lines)
            details_lines.append(f"\n#### {heading}\n\n{quoted_content}\n")
        answer = answer.rstrip() + "\n".join(details_lines)

    return AnswerResult(
        answer=answer + response_footer,
        references=filtered_refs,
        used_chunks=len(hits),
    )
