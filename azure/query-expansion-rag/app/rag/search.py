"""AI Search 検索ラッパ（RAG ランタイム用、ハイブリッド検索専用）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from azure.core.credentials import TokenCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    id: str
    score: float
    content: str
    source_path: str
    source_locator: str
    doc_type: str
    title: str
    section: str
    page: int | None


class RagSearch:
    def __init__(
        self,
        endpoint: str,
        index_name: str,
        credential: TokenCredential,
    ) -> None:
        self._client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)

    def hybrid_search(self, query_text: str, query_vector: list[float], top_k: int = 5) -> list[SearchHit]:
        """テキスト検索とベクトル検索を同時に投入し、AI Search の RRF で合成。"""
        results = self._client.search(
            search_text=query_text,
            vector_queries=[
                VectorizedQuery(
                    vector=query_vector,
                    k_nearest_neighbors=top_k,
                    fields="content_vector",
                )
            ],
            select=[
                "id", "content", "source_path", "source_locator",
                "doc_type", "title", "section", "page",
            ],
            top=top_k,
        )
        hits: list[SearchHit] = []
        for r in results:
            hits.append(
                SearchHit(
                    id=r["id"],
                    score=float(r["@search.score"]),
                    content=r.get("content") or "",
                    source_path=r.get("source_path") or "",
                    source_locator=r.get("source_locator") or "",
                    doc_type=r.get("doc_type") or "",
                    title=r.get("title") or "",
                    section=r.get("section") or "",
                    page=r.get("page"),
                )
            )
        return hits
