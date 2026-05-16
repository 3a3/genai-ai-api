"""AOAI 埋め込み生成。

- text-embedding-3-small を Managed Identity（ローカルは az login）で呼ぶ
- バッチで投入（API 1 リクエストあたり最大 2048 入力対応だが、保守的に 16）
- 一時障害は exponential backoff で 3 回まで再試行
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

from azure.core.credentials import TokenCredential
from azure.identity import get_bearer_token_provider
from openai import APIError, AzureOpenAI

from .errors import EmbedderError
from .types import Chunk, EmbeddedChunk

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(
        self,
        endpoint: str,
        deployment: str,
        api_version: str,
        credential: TokenCredential,
        batch_size: int = 16,
        dimensions: int = 1536,
    ) -> None:
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version,
            azure_ad_token_provider=token_provider,
        )
        self._deployment = deployment
        self._batch_size = batch_size
        self._dimensions = dimensions

    def embed_chunks(self, chunks: Iterable[Chunk]) -> list[EmbeddedChunk]:
        chunk_list = list(chunks)
        if not chunk_list:
            return []
        results: list[EmbeddedChunk] = []
        for i in range(0, len(chunk_list), self._batch_size):
            batch = chunk_list[i : i + self._batch_size]
            vectors = self._embed_batch([c.content for c in batch])
            for c, v in zip(batch, vectors):
                results.append(
                    EmbeddedChunk(
                        id=c.id,
                        content=c.content,
                        source_path=c.source_path,
                        source_locator=c.source_locator,
                        source_hash=c.source_hash,
                        doc_type=c.doc_type,
                        title=c.title,
                        section=c.section,
                        page=c.page,
                        chunk_index=c.chunk_index,
                        content_vector=v,
                    )
                )
        return results

    def _embed_batch(self, inputs: list[str]) -> list[list[float]]:
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                resp = self._client.embeddings.create(
                    model=self._deployment,
                    input=inputs,
                )
                return [d.embedding for d in resp.data]
            except APIError as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning("embedding API error (attempt %d): %s; retrying in %ds", attempt, exc, wait)
                time.sleep(wait)
            except Exception as exc:  # noqa: BLE001
                raise EmbedderError("(batch)", f"unexpected embedding error: {exc}") from exc
        raise EmbedderError("(batch)", f"embedding failed after 3 attempts: {last_exc}")
