from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from memory_domain import Memory, MemoryKind, RequestContext, Sensitivity


class RetrievalStatus(StrEnum):
    COMPLETE = "complete"
    DEGRADED_TIMEOUT = "degraded_timeout"
    DEGRADED_UNAVAILABLE = "degraded_unavailable"


@dataclass(frozen=True, slots=True)
class SearchFilters:
    kinds: tuple[MemoryKind, ...] = ()
    sensitivities: tuple[Sensitivity, ...] = (Sensitivity.GENERAL,)
    collection_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class QueryPlan:
    query: str
    subject_id: UUID
    filters: SearchFilters
    top_k: int
    candidate_limit: int


@dataclass(frozen=True, slots=True)
class Candidate:
    memory_id: UUID
    version_id: UUID
    rank: int
    score: float


@dataclass(frozen=True, slots=True)
class RankedMemory:
    memory: Memory
    score: float
    lexical_rank: int | None
    semantic_rank: int | None
    rank_policy: str = "deterministic-v1"


@dataclass(frozen=True, slots=True)
class SearchResult:
    items: tuple[RankedMemory, ...]
    status: RetrievalStatus
    omitted: tuple[str, ...] = ()


class CandidateSource(Protocol):
    async def search(
        self,
        context: RequestContext,
        plan: QueryPlan,
        query_vector: tuple[float, ...] | None = None,
    ) -> tuple[Candidate, ...]: ...


class EligibilityRepository(Protocol):
    async def load_eligible(
        self, context: RequestContext, candidate_versions: tuple[tuple[UUID, UUID], ...]
    ) -> tuple[Memory, ...]: ...
