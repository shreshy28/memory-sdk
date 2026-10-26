from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from memory_retrieval.candidates import Candidate


@dataclass(frozen=True, slots=True)
class FusedCandidate:
    memory_id: UUID
    version_id: UUID
    score: float
    lexical_rank: int | None
    semantic_rank: int | None


@dataclass(slots=True)
class _Accumulator:
    score: float = 0.0
    lexical_rank: int | None = None
    semantic_rank: int | None = None


def reciprocal_rank_fusion(
    lexical: Sequence[Candidate], semantic: Sequence[Candidate], *, rank_constant: int = 60
) -> tuple[FusedCandidate, ...]:
    if rank_constant < 1:
        raise ValueError("rank_constant must be positive")
    combined: dict[tuple[UUID, UUID], _Accumulator] = {}
    for index, candidates in enumerate((lexical, semantic)):
        for candidate in candidates:
            key = (candidate.memory_id, candidate.version_id)
            state = combined.setdefault(key, _Accumulator())
            state.score += 1 / (rank_constant + candidate.rank)
            if index == 0:
                state.lexical_rank = candidate.rank
            else:
                state.semantic_rank = candidate.rank
    return tuple(
        FusedCandidate(
            memory_id,
            version_id,
            values.score,
            values.lexical_rank,
            values.semantic_rank,
        )
        for (memory_id, version_id), values in sorted(
            combined.items(), key=lambda item: (-item[1].score, str(item[0][0]))
        )
    )
