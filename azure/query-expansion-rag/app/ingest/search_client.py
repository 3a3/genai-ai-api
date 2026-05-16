"""Azure AI Search クライアント。

- インデックススキーマ作成（無ければ作る）
- ドキュメント upload (mergeOrUpload)
- source_path をキーにした batch delete
- source_path のユニーク一覧取得（sync 用）
"""

from __future__ import annotations

import logging
from typing import Iterable

from azure.core.credentials import TokenCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
)

from .errors import UploaderError
from .types import EmbeddedChunk

logger = logging.getLogger(__name__)

# AI Search 内部の名前
_VECTOR_PROFILE = "rag-vector-profile"
_HNSW_CONFIG = "rag-hnsw"
_SEMANTIC_CONFIG = "rag-semantic"


def build_index_schema(index_name: str, embedding_dim: int = 1536) -> SearchIndex:
    """RAG 用インデックススキーマ定義。"""
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
            analyzer_name="ja.microsoft",
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=embedding_dim,
            vector_search_profile_name=_VECTOR_PROFILE,
        ),
        SimpleField(name="source_path", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="source_locator", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="source_hash", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="title", type=SearchFieldDataType.String, analyzer_name="ja.microsoft"),
        SimpleField(name="section", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True),
        SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name=_HNSW_CONFIG,
                parameters=HnswParameters(m=4, ef_construction=400, ef_search=500, metric=VectorSearchAlgorithmMetric.COSINE),
            )
        ],
        profiles=[
            VectorSearchProfile(name=_VECTOR_PROFILE, algorithm_configuration_name=_HNSW_CONFIG)
        ],
    )

    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=_SEMANTIC_CONFIG,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                ),
            )
        ]
    )

    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


class AISearchClient:
    def __init__(
        self,
        endpoint: str,
        index_name: str,
        credential: TokenCredential,
        embedding_dim: int = 1536,
    ) -> None:
        self.endpoint = endpoint
        self.index_name = index_name
        self.embedding_dim = embedding_dim
        self._credential = credential
        self._index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
        self._search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)

    # ----- インデックス管理 -----
    def ensure_index(self) -> None:
        """無ければ作成、有ればスキップ。"""
        existing = {ix.name for ix in self._index_client.list_indexes()}
        if self.index_name in existing:
            logger.info("index '%s' already exists; skip creation", self.index_name)
            return
        schema = build_index_schema(self.index_name, embedding_dim=self.embedding_dim)
        self._index_client.create_index(schema)
        logger.info("index '%s' created", self.index_name)

    # ----- ドキュメント操作 -----
    def upload_chunks(self, chunks: Iterable[EmbeddedChunk]) -> int:
        """mergeOrUpload で同 id 上書き。"""
        docs = [
            {
                "id": c.id,
                "content": c.content,
                "content_vector": c.content_vector,
                "source_path": c.source_path,
                "source_locator": c.source_locator,
                "source_hash": c.source_hash,
                "doc_type": c.doc_type,
                "title": c.title,
                "section": c.section,
                "page": c.page,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]
        if not docs:
            return 0
        try:
            results = self._search_client.merge_or_upload_documents(documents=docs)
        except Exception as exc:  # noqa: BLE001
            raise UploaderError("(batch)", f"AI Search upload failed: {exc}") from exc
        failed = [r for r in results if not r.succeeded]
        if failed:
            raise UploaderError(
                "(batch)",
                f"{len(failed)} of {len(docs)} documents failed to upload; first key={failed[0].key}",
            )
        return len(docs)

    def delete_by_source_path(self, source_path: str) -> int:
        """source_path に紐づく全 chunk を削除。"""
        results = self._search_client.search(
            search_text="*",
            filter=f"source_path eq '{source_path}'",
            select=["id"],
            top=1000,
        )
        ids = [r["id"] for r in results]
        if not ids:
            return 0
        self._search_client.delete_documents(documents=[{"id": i} for i in ids])
        logger.info("deleted %d chunks for source_path=%s", len(ids), source_path)
        return len(ids)

    def list_source_paths(self) -> set[str]:
        """インデックスに含まれる全 source_path のユニーク集合。"""
        # facet で取得（上限 1000）
        results = self._search_client.search(
            search_text="*",
            facets=["source_path,count:1000"],
            top=0,
        )
        facets = results.get_facets() or {}
        return {f["value"] for f in facets.get("source_path", [])}

    def list_source_hashes(self) -> dict[str, str]:
        """source_path → source_hash（最初に出会った値）"""
        result: dict[str, str] = {}
        # ページネーション簡略化（数千件まで想定）
        results = self._search_client.search(
            search_text="*",
            select=["source_path", "source_hash"],
            top=1000,
        )
        for r in results:
            sp = r.get("source_path")
            sh = r.get("source_hash")
            if sp and sh and sp not in result:
                result[sp] = sh
        return result
