"""検索 + 関連性評価。

- 各クエリに対して並列にハイブリッド検索
- chunk id でデデュープ（スコア最大値を採用）
- 上位 N 件を取り出し、LLM で「関連性 YES/NO」を判定
- YES のもののみを final として返す
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from .aoai_client import AOAIClient
from .prompts import RELEVANCE_RATING_SYSTEM, RELEVANCE_RATING_USER
from .search import RagSearch, SearchHit

logger = logging.getLogger(__name__)


def retrieve(
    aoai: AOAIClient,
    search: RagSearch,
    queries: list[str],
    top_k_per_query: int = 5,
    max_workers: int = 5,
) -> list[SearchHit]:
    """各クエリで並列検索 → デデュープ → スコア降順。"""

    def run_one(q: str) -> list[SearchHit]:
        vec = aoai.embed(q)
        return search.hybrid_search(query_text=q, query_vector=vec, top_k=top_k_per_query)

    all_hits: list[SearchHit] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(queries))) as ex:
        for hits in ex.map(run_one, queries):
            all_hits.extend(hits)

    # id でデデュープ、スコア max を採用
    best: dict[str, SearchHit] = {}
    for h in all_hits:
        cur = best.get(h.id)
        if cur is None or h.score > cur.score:
            best[h.id] = h
    deduped = sorted(best.values(), key=lambda h: h.score, reverse=True)
    return deduped


def rate_relevance(
    aoai: AOAIClient,
    question: str,
    hits: list[SearchHit],
    keep_top_n: int = 6,
    max_workers: int = 5,
) -> list[SearchHit]:
    """LLM に YES/NO を聞いて、YES のもののみ返す。NO ばかりなら緩和して上位 N 件を返す。"""
    if not hits:
        return []
    candidates = hits[: keep_top_n * 2]  # 評価対象は keep の 2 倍まで

    def rate_one(h: SearchHit) -> bool:
        user = RELEVANCE_RATING_USER.format(question=question, passage=h.content[:1500])
        try:
            verdict = aoai.chat(system=RELEVANCE_RATING_SYSTEM, user=user, temperature=0.0, max_tokens=8)
        except Exception as exc:  # noqa: BLE001
            logger.warning("relevance rating failed for hit %s: %s; treating as YES", h.id, exc)
            return True
        return verdict.strip().upper().startswith("YES")

    keep: list[SearchHit] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(candidates))) as ex:
        verdicts = list(ex.map(rate_one, candidates))
    for h, ok in zip(candidates, verdicts):
        if ok:
            keep.append(h)
        if len(keep) >= keep_top_n:
            break

    # 全部 NO だった場合は LLM の判断を信頼せず、ベクトル/テキスト検索のトップを返す
    if not keep:
        logger.info("all candidates marked NO by relevance rating; falling back to top-k by score")
        return hits[:keep_top_n]
    return keep
