"""ingest 設定（環境変数から読む）。"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IngestConfig:
    # Storage
    storage_account: str
    source_container: str
    quarantine_container: str
    reports_container: str

    # AOAI
    aoai_endpoint: str
    aoai_embedding_deployment: str
    aoai_api_version: str

    # AI Search
    search_endpoint: str
    search_index_name: str

    # 制限
    max_file_size_mb: int = 100
    embedding_batch_size: int = 16
    embedding_dimensions: int = 1536

    @classmethod
    def from_env(cls) -> "IngestConfig":
        def req(key: str) -> str:
            v = os.environ.get(key)
            if not v:
                raise RuntimeError(f"Environment variable {key} is required")
            return v

        return cls(
            storage_account=req("AZURE_STORAGE_ACCOUNT"),
            source_container=os.environ.get("AZURE_STORAGE_SOURCE_CONTAINER", "source-docs"),
            quarantine_container=os.environ.get("AZURE_STORAGE_QUARANTINE_CONTAINER", "quarantine"),
            reports_container=os.environ.get("AZURE_STORAGE_REPORTS_CONTAINER", "ingest-reports"),
            aoai_endpoint=req("AZURE_OPENAI_ENDPOINT"),
            aoai_embedding_deployment=req("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
            aoai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            search_endpoint=req("AZURE_SEARCH_ENDPOINT"),
            search_index_name=os.environ.get("AZURE_SEARCH_INDEX_NAME", "rag-index"),
            max_file_size_mb=int(os.environ.get("INGEST_MAX_FILE_SIZE_MB", "100")),
            embedding_batch_size=int(os.environ.get("INGEST_EMBEDDING_BATCH_SIZE", "16")),
            embedding_dimensions=int(os.environ.get("INGEST_EMBEDDING_DIMENSIONS", "1536")),
        )
