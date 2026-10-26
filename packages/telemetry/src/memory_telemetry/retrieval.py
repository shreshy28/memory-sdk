from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalEvent:
    status: str
    candidate_count: int
    selected_count: int
    elapsed_ms: float


def safe_attributes(event: RetrievalEvent) -> dict[str, str | int | float]:
    return {
        "retrieval.status": event.status,
        "retrieval.candidate_count": event.candidate_count,
        "retrieval.selected_count": event.selected_count,
        "retrieval.elapsed_ms": event.elapsed_ms,
    }
