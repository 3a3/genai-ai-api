"""RAG パイプライン全体のオーケストレーション。Function App から 1 関数で呼ばれる。"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from azure.identity import DefaultAzureCredential

from .aoai_client import AOAIClient
from .answer_generation import AnswerResult, generate_answer
from .config import RagConfig
from .query_expansion import expand_query
from .retrieve_and_rating import rate_relevance, retrieve
from .search import RagSearch

logger = logging.getLogger(__name__)


@dataclass
class RagInvokeResult:
    answer: str
    references: list[dict[str, Any]]
    debug: dict[str, Any]


class RagPipeline:
    _instance: "RagPipeline | None" = None

    @classmethod
    def get(cls) -> "RagPipeline":
        """Function プロセス内で 1 個共有（接続再利用）。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.config = RagConfig.from_env()
        self.credential = DefaultAzureCredential()
        self.aoai = AOAIClient(
            endpoint=self.config.aoai_endpoint,
            chat_deployment=self.config.aoai_chat_deployment,
            embedding_deployment=self.config.aoai_embedding_deployment,
            api_version=self.config.aoai_api_version,
            credential=self.credential,
        )
        self.search = RagSearch(
            endpoint=self.config.search_endpoint,
            index_name=self.config.search_index_name,
            credential=self.credential,
        )

    def invoke(self, question: str) -> RagInvokeResult:
        t0 = time.time()

        # ① クエリ拡張
        t_qe_start = time.time()
        queries = expand_query(self.aoai, question, n_queries=self.config.n_expanded_queries)
        t_qe = time.time() - t_qe_start
        logger.info("query_expansion: %d queries in %.2fs", len(queries), t_qe)

        # ② 並列検索
        t_rt_start = time.time()
        hits = retrieve(self.aoai, self.search, queries, top_k_per_query=self.config.top_k_per_query)
        t_rt = time.time() - t_rt_start
        logger.info("retrieve: %d hits in %.2fs", len(hits), t_rt)

        # ③ 関連性評価
        t_rr_start = time.time()
        if self.config.enable_relevance_filter:
            kept = rate_relevance(self.aoai, question, hits, keep_top_n=self.config.final_top_k)
        else:
            kept = hits[: self.config.final_top_k]
        t_rr = time.time() - t_rr_start
        logger.info("rate_relevance: kept %d/%d in %.2fs", len(kept), len(hits), t_rr)

        # ④ 回答生成
        t_ag_start = time.time()
        result: AnswerResult = generate_answer(
            self.aoai, question, kept, response_footer=self.config.response_footer
        )
        t_ag = time.time() - t_ag_start
        logger.info("answer_generation: %d chars in %.2fs", len(result.answer), t_ag)

        total = time.time() - t0
        return RagInvokeResult(
            answer=result.answer,
            references=[asdict(r) for r in result.references],
            debug={
                "queries": queries,
                "n_hits": len(hits),
                "n_kept": len(kept),
                "elapsed_seconds": {
                    "total": round(total, 2),
                    "query_expansion": round(t_qe, 2),
                    "retrieve": round(t_rt, 2),
                    "rate_relevance": round(t_rr, 2),
                    "answer_generation": round(t_ag, 2),
                },
            },
        )
