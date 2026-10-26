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


def main() -> None:
    now = datetime.now(UTC)
    memory_id, version_id, actor_id = uuid4(), uuid4(), uuid4()
    version = MemoryVersion(
        version_id,
        memory_id,
        1,
        "The user prefers tea",
        None,
        0.9,
        0.7,
        Sensitivity.GENERAL,
        now,
        actor_id,
        "smoke",
    )
    memory = Memory(
        memory_id,
        uuid4(),
        uuid4(),
        uuid4(),
        MemoryKind.PREFERENCE,
        ProvenanceMode.EXPLICIT,
        MemoryStatus.ACTIVE,
        version,
        now,
        now,
    )
    package = compile_context((RankedMemory(memory, 1.0, 1, 1),), 100, 20, RetrievalStatus.COMPLETE)
    if not package.entries or package.used_tokens > 80:
        raise SystemExit("retrieval smoke check failed")
    print("retrieval smoke check passed")


if __name__ == "__main__":
    main()
