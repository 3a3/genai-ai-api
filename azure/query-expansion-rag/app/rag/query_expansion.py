"""クエリ拡張: 1 質問 → N 個の検索クエリ。"""

from __future__ import annotations

import logging

from .aoai_client import AOAIClient
from .prompts import QUERY_EXPANSION_SYSTEM

logger = logging.getLogger(__name__)


def expand_query(aoai: AOAIClient, question: str, n_queries: int = 3) -> list[str]:
    """LLM に検索クエリを n_queries 個生成させる。元の質問も常に含める。"""
    system = QUERY_EXPANSION_SYSTEM.format(n_queries=n_queries)
    data = aoai.chat_json(system=system, user=question, temperature=0.3, max_tokens=512)
    raw_queries = data.get("queries") if isinstance(data, dict) else None
    queries: list[str] = []
    if isinstance(raw_queries, list):
        for q in raw_queries:
            if isinstance(q, str) and q.strip():
                queries.append(q.strip())

    if not queries:
        logger.warning("query expansion returned no usable queries; falling back to original")
        return [question]

    # 元の質問を必ず先頭に含めてベクトル検索のリコールを保つ
    final = [question] + [q for q in queries if q != question]
    return final[: n_queries + 1]
