from dataclasses import dataclass
from enum import StrEnum

from memory_retrieval.candidates import RankedMemory, RetrievalStatus


class OmissionReason(StrEnum):
    BUDGET_EXCEEDED = "budget_exceeded"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class ContextEntry:
    ranked: RankedMemory
    token_cost: int


@dataclass(frozen=True, slots=True)
class ContextPackage:
    entries: tuple[ContextEntry, ...]
    rendered: str
    total_budget: int
    reserved_tokens: int
    used_tokens: int
    omissions: tuple[tuple[str, OmissionReason], ...]
    retrieval_status: RetrievalStatus


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def compile_context(
    items: tuple[RankedMemory, ...],
    total_budget: int,
    reserved_tokens: int,
    status: RetrievalStatus,
) -> ContextPackage:
    if total_budget < 1 or reserved_tokens < 0 or reserved_tokens > total_budget:
        raise ValueError("reserved tokens must fit within the total budget")
    available = total_budget - reserved_tokens
    selected: list[ContextEntry] = []
    omissions: list[tuple[str, OmissionReason]] = []
    seen: set[str] = set()
    used = 0
    for item in items:
        normalized = " ".join(item.memory.current_version.text.casefold().split())
        if normalized in seen:
            omissions.append((str(item.memory.id), OmissionReason.DUPLICATE))
            continue
        cost = estimate_tokens(item.memory.current_version.text)
        if used + cost > available:
            omissions.append((str(item.memory.id), OmissionReason.BUDGET_EXCEEDED))
            continue
        seen.add(normalized)
        used += cost
        selected.append(ContextEntry(item, cost))
    rendered = "\n".join(
        f"- [memory:{entry.ranked.memory.id} "
        f"version:{entry.ranked.memory.current_version.version}] "
        f"{entry.ranked.memory.current_version.text}"
        for entry in selected
    )
    return ContextPackage(
        tuple(selected), rendered, total_budget, reserved_tokens, used, tuple(omissions), status
    )
