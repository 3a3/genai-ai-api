"""RAG ランタイム設定（環境変数から読む）。"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RagConfig:
    aoai_endpoint: str
    aoai_chat_deployment: str
    aoai_embedding_deployment: str
    aoai_api_version: str
    search_endpoint: str
    search_index_name: str
    storage_account: str
    reports_container: str

    # チューニングパラメータ
    n_expanded_queries: int = 3
    top_k_per_query: int = 5
    final_top_k: int = 6
    enable_relevance_filter: bool = True
    response_footer: str = (
        "\n\n---\n"
        "※この回答は生成 AI によって作成されており、情報が正確でない場合があります。"
        "重要な判断は必ず原本（出典）をご確認ください。"
    )

    @classmethod
    def from_env(cls) -> "RagConfig":
        def req(key: str) -> str:
            v = os.environ.get(key)
            if not v:
                raise RuntimeError(f"Environment variable {key} is required")
            return v

        return cls(
            aoai_endpoint=req("AZURE_OPENAI_ENDPOINT"),
            aoai_chat_deployment=req("AZURE_OPENAI_CHAT_DEPLOYMENT"),
            aoai_embedding_deployment=req("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
            aoai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            search_endpoint=req("AZURE_SEARCH_ENDPOINT"),
            search_index_name=os.environ.get("AZURE_SEARCH_INDEX_NAME", "rag-index"),
            storage_account=req("AZURE_STORAGE_ACCOUNT"),
            reports_container=os.environ.get("AZURE_STORAGE_REPORTS_CONTAINER", "ingest-reports"),
            n_expanded_queries=int(os.environ.get("RAG_N_EXPANDED_QUERIES", "3")),
            top_k_per_query=int(os.environ.get("RAG_TOP_K_PER_QUERY", "5")),
            final_top_k=int(os.environ.get("RAG_FINAL_TOP_K", "6")),
            enable_relevance_filter=os.environ.get("RAG_ENABLE_RELEVANCE_FILTER", "true").lower() == "true",
        )
