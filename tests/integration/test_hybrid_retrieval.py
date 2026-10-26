import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from memory_application.ports import EmbeddingBatch
from memory_domain import (
    Memory,
    MemoryKind,
    MemoryStatus,
    MemoryVersion,
    ProvenanceMode,
    RequestContext,
    Sensitivity,
)
from memory_retrieval import Candidate, QueryPlan, RetrievalService, RetrievalStatus


def make_memory(context: RequestContext, subject_id: UUID, text: str) -> Memory:
    now, memory_id = datetime.now(UTC), uuid4()
    version = MemoryVersion(
        uuid4(), memory_id, 1, text, None, 0.8, 0.7, Sensitivity.GENERAL, now, uuid4(), "test"
    )
    return Memory(
        memory_id,
        context.tenant_id,
        context.project_id,
        subject_id,
        MemoryKind.PREFERENCE,
        ProvenanceMode.EXPLICIT,
        MemoryStatus.ACTIVE,
        version,
        now,
        now,
    )


class Source:
    def __init__(self, memories: list[Memory], order: list[int], delay: float = 0) -> None:
        self.memories, self.order, self.delay = memories, order, delay

    async def search(
        self,
        context: RequestContext,
        plan: QueryPlan,
        query_vector: tuple[float, ...] | None = None,
    ) -> tuple[Candidate, ...]:
        await asyncio.sleep(self.delay)
        return tuple(
            Candidate(self.memories[index].id, self.memories[index].current_version.id, rank, 1.0)
            for rank, index in enumerate(self.order, 1)
        )


class UnavailableSource(Source):
    async def search(
        self,
        context: RequestContext,
        plan: QueryPlan,
        query_vector: tuple[float, ...] | None = None,
    ) -> tuple[Candidate, ...]:
        raise ConnectionError("retrieval store unavailable")


class Canonical:
    def __init__(self, memories: list[Memory]) -> None:
        self.memories = memories

    async def load_eligible(
        self, context: RequestContext, candidate_versions: tuple[tuple[UUID, UUID], ...]
    ) -> tuple[Memory, ...]:
        versions = {version for _, version in candidate_versions}
        return tuple(item for item in self.memories if item.current_version.id in versions)


class Embeddings:
    async def embed(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(((0.1, 0.2),), "test", "test-v1", 2)


@pytest.mark.asyncio
async def test_hybrid_search_fuses_and_revalidates_current_versions() -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    memories = [make_memory(context, subject, "tea"), make_memory(context, subject, "coffee")]
    stale = make_memory(context, subject, "stale")
    source_memories = [*memories, stale]
    service = RetrievalService(
        Source(source_memories, [0, 2]),
        Source(source_memories, [1, 0]),
        Canonical(memories),
        Embeddings(),
    )

    result = await service.search(context, query="drink", subject_id=subject)

    assert result.status is RetrievalStatus.COMPLETE
    assert [item.memory.current_version.text for item in result.items] == ["tea", "coffee"]
    assert result.items[0].lexical_rank == 1
    assert result.items[0].semantic_rank == 2


@pytest.mark.asyncio
async def test_search_returns_explicit_degraded_timeout() -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    memory = make_memory(context, subject, "tea")
    service = RetrievalService(
        Source([memory], [0], 0.05), Source([], []), Canonical([memory]), Embeddings()
    )
    result = await service.search(context, query="tea", subject_id=subject, deadline_seconds=0.001)
    assert result.status is RetrievalStatus.DEGRADED_TIMEOUT
    assert result.items == ()


@pytest.mark.asyncio
async def test_search_returns_explicit_degraded_unavailable() -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    service = RetrievalService(
        UnavailableSource([], []), Source([], []), Canonical([]), Embeddings()
    )

    result = await service.search(context, query="tea", subject_id=subject)

    assert result.status is RetrievalStatus.DEGRADED_UNAVAILABLE
    assert result.items == ()
    assert result.omitted == ("retrieval_unavailable",)
