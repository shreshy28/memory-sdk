from datetime import UTC, datetime
from uuid import uuid4

from memory_domain import (
    Memory,
    MemoryKind,
    MemoryStatus,
    MemoryVersion,
    ProvenanceMode,
    Sensitivity,
)
from memory_retrieval import RankedMemory, RetrievalStatus, compile_context


def ranked(text: str, score: float) -> RankedMemory:
    now, memory_id = datetime.now(UTC), uuid4()
    version = MemoryVersion(
        uuid4(),
        memory_id,
        1,
        text,
        None,
        1.0,
        0.5,
        Sensitivity.GENERAL,
        now,
        uuid4(),
        "test",
    )
    memory = Memory(
        memory_id,
        uuid4(),
        uuid4(),
        uuid4(),
        MemoryKind.FACT,
        ProvenanceMode.EXPLICIT,
        MemoryStatus.ACTIVE,
        version,
        now,
        now,
    )
    return RankedMemory(memory, score, 1, 1)


def test_compiler_reserves_budget_deduplicates_and_reports_omissions() -> None:
    first = ranked("tea preference", 1.0)
    duplicate = ranked(" TEA   PREFERENCE ", 0.9)
    too_large = ranked("x" * 80, 0.8)

    package = compile_context((first, duplicate, too_large), 20, 10, RetrievalStatus.COMPLETE)

    assert package.used_tokens <= 10
    assert [entry.ranked.memory.id for entry in package.entries] == [first.memory.id]
    assert [reason.value for _, reason in package.omissions] == ["duplicate", "budget_exceeded"]
    assert str(first.memory.id) in package.rendered


def test_compiler_preserves_degraded_status() -> None:
    package = compile_context((), 100, 20, RetrievalStatus.DEGRADED_TIMEOUT)
    assert package.retrieval_status is RetrievalStatus.DEGRADED_TIMEOUT
    assert package.rendered == ""
