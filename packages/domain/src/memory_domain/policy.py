from datetime import UTC, datetime

from memory_domain.memory import Memory, MemoryStatus


def is_currently_eligible(memory: Memory, *, now: datetime | None = None) -> bool:
    instant = now or datetime.now(UTC)
    version = memory.current_version
    return (
        memory.status is MemoryStatus.ACTIVE
        and (version.valid_from is None or version.valid_from <= instant)
        and (version.valid_to is None or version.valid_to > instant)
    )
