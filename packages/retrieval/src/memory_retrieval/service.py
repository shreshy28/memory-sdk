import asyncio
from uuid import UUID

from memory_application.ports import EmbeddingProvider
from memory_domain import RequestContext

from memory_retrieval.candidates import (
    CandidateSource,
    EligibilityRepository,
    RankedMemory,
    RetrievalStatus,
    SearchFilters,
    SearchResult,
)
from memory_retrieval.eligibility import is_eligible
from memory_retrieval.fusion import reciprocal_rank_fusion
from memory_retrieval.query_plan import build_query_plan
from memory_retrieval.ranking import deterministic_score


class RetrievalService:
    def __init__(
        self,
        lexical: CandidateSource,
        semantic: CandidateSource,
        eligibility: EligibilityRepository,
        embeddings: EmbeddingProvider,
    ) -> None:
        self.lexical = lexical
        self.semantic = semantic
        self.eligibility = eligibility
        self.embeddings = embeddings

    async def search(
        self,
        context: RequestContext,
        *,
        query: str,
        subject_id: UUID,
        filters: SearchFilters | None = None,
        top_k: int = 10,
        deadline_seconds: float = 1.0,
    ) -> SearchResult:
        plan = build_query_plan(query, subject_id, filters or SearchFilters(), top_k)
        if not 0 < deadline_seconds <= 30:
            raise ValueError("deadline_seconds must be between 0 and 30")
        try:
            async with asyncio.timeout(deadline_seconds):
                embedding = await self.embeddings.embed([plan.query])
                vector = tuple(float(value) for value in embedding.vectors[0])
                lexical, semantic = await asyncio.gather(
                    self.lexical.search(context, plan),
                    self.semantic.search(context, plan, vector),
                )
                fused = reciprocal_rank_fusion(lexical, semantic)
                versions = tuple((item.memory_id, item.version_id) for item in fused)
                canonical = await self.eligibility.load_eligible(context, versions)
        except TimeoutError:
            return SearchResult((), RetrievalStatus.DEGRADED_TIMEOUT, ("deadline_exceeded",))
        except (ConnectionError, OSError):
            return SearchResult(
                (), RetrievalStatus.DEGRADED_UNAVAILABLE, ("retrieval_unavailable",)
            )
        by_version = {memory.current_version.id: memory for memory in canonical}
        ranked = []
        for item in fused:
            memory = by_version.get(item.version_id)
            if memory is None or not is_eligible(context, memory, plan):
                continue
            ranked.append(
                RankedMemory(
                    memory,
                    deterministic_score(memory, item.score),
                    item.lexical_rank,
                    item.semantic_rank,
                )
            )
        ranked.sort(key=lambda item: (-item.score, str(item.memory.id)))
        return SearchResult(tuple(ranked[:top_k]), RetrievalStatus.COMPLETE)
