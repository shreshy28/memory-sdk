from datetime import UTC, datetime

from memory_domain import Memory


def deterministic_score(
    memory: Memory, fused_score: float, *, now: datetime | None = None
) -> float:
    instant = now or datetime.now(UTC)
    age_days = max(0.0, (instant - memory.current_version.recorded_at).total_seconds() / 86400)
    recency = 1 / (1 + age_days / 30)
    version = memory.current_version
    return fused_score + 0.015 * version.importance + 0.01 * version.confidence + 0.005 * recency
