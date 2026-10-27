import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from memory_domain.identity import RequestContext
from memory_domain.memory import Memory
from memory_domain.policy import is_currently_eligible


class ConsolidationAction(StrEnum):
    REINFORCE = "reinforce"
    MERGE = "merge"
    CONFLICT = "conflict"
    SUPERSEDE = "supersede"
    NO_OP = "no_op"


class ConsolidationRejection(StrEnum):
    UNAUTHORIZED = "unauthorized"
    SUPPRESSED = "suppressed"
    INELIGIBLE = "ineligible"
    STALE_VERSION = "stale_version"
    SCOPE_MISMATCH = "scope_mismatch"
    SELF_CANDIDATE = "self_candidate"


class ConsolidationRejectedError(ValueError):
    def __init__(self, reason: ConsolidationRejection) -> None:
        self.reason = reason
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class ConsolidationInput:
    memory: Memory
    expected_version_id: UUID
    authorized: bool = True
    suppressed: bool = False


@dataclass(frozen=True, slots=True)
class ConsolidationProposal:
    action: ConsolidationAction
    target_memory_id: UUID
    candidate_memory_id: UUID
    source_version_ids: tuple[UUID, UUID]
    reason: str
    proposed_text: str | None = None


def propose_consolidation(
    context: RequestContext,
    target: ConsolidationInput,
    candidate: ConsolidationInput,
    *,
    now: datetime | None = None,
    overlap_threshold: float = 0.75,
) -> ConsolidationProposal:
    if not 0 < overlap_threshold <= 1:
        raise ValueError("overlap_threshold must be between 0 and 1")
    instant = now or datetime.now(UTC)
    _validate_input(context, target, instant)
    _validate_input(context, candidate, instant)
    _validate_pair(target.memory, candidate.memory)

    target_memory, candidate_memory = target.memory, candidate.memory
    lineage = (target_memory.current_version.id, candidate_memory.current_version.id)
    target_text = _normalize_text(target_memory.current_version.text)
    candidate_text = _normalize_text(candidate_memory.current_version.text)

    if target_text == candidate_text:
        return ConsolidationProposal(
            ConsolidationAction.REINFORCE,
            target_memory.id,
            candidate_memory.id,
            lineage,
            "normalized_text_match",
            target_memory.current_version.text,
        )

    structured = _structured_relationship(target_memory, candidate_memory)
    if structured is not None:
        action, reason = structured
        return ConsolidationProposal(
            action,
            target_memory.id,
            candidate_memory.id,
            lineage,
            reason,
            (
                candidate_memory.current_version.text
                if action is ConsolidationAction.SUPERSEDE
                else None
            ),
        )

    overlap = _token_overlap(target_text, candidate_text)
    if overlap >= overlap_threshold:
        proposed_text = max(
            (target_memory.current_version.text, candidate_memory.current_version.text),
            key=lambda value: (len(_tokens(value)), len(value)),
        )
        return ConsolidationProposal(
            ConsolidationAction.MERGE,
            target_memory.id,
            candidate_memory.id,
            lineage,
            f"normalized_token_overlap:{overlap:.3f}",
            proposed_text,
        )

    return ConsolidationProposal(
        ConsolidationAction.NO_OP,
        target_memory.id,
        candidate_memory.id,
        lineage,
        f"insufficient_overlap:{overlap:.3f}",
    )


def _validate_input(context: RequestContext, item: ConsolidationInput, instant: datetime) -> None:
    memory = item.memory
    if (
        not item.authorized
        or memory.tenant_id != context.tenant_id
        or memory.project_id != context.project_id
    ):
        raise ConsolidationRejectedError(ConsolidationRejection.UNAUTHORIZED)
    if item.suppressed:
        raise ConsolidationRejectedError(ConsolidationRejection.SUPPRESSED)
    if memory.current_version.id != item.expected_version_id:
        raise ConsolidationRejectedError(ConsolidationRejection.STALE_VERSION)
    if not is_currently_eligible(memory, now=instant):
        raise ConsolidationRejectedError(ConsolidationRejection.INELIGIBLE)


def _validate_pair(target: Memory, candidate: Memory) -> None:
    if target.id == candidate.id or target.current_version.id == candidate.current_version.id:
        raise ConsolidationRejectedError(ConsolidationRejection.SELF_CANDIDATE)
    if (
        target.tenant_id,
        target.project_id,
        target.subject_id,
        target.collection_id,
        target.kind,
        target.current_version.sensitivity,
    ) != (
        candidate.tenant_id,
        candidate.project_id,
        candidate.subject_id,
        candidate.collection_id,
        candidate.kind,
        candidate.current_version.sensitivity,
    ):
        raise ConsolidationRejectedError(ConsolidationRejection.SCOPE_MISMATCH)


def _structured_relationship(
    target: Memory, candidate: Memory
) -> tuple[ConsolidationAction, str] | None:
    target_value = target.current_version.structured_value
    candidate_value = candidate.current_version.structured_value
    if not target_value or not candidate_value:
        return None
    if target_value.get("key") != candidate_value.get("key"):
        return None
    if "value" not in target_value or "value" not in candidate_value:
        return None
    if target_value["value"] == candidate_value["value"]:
        return None
    target_start = target.current_version.valid_from
    candidate_start = candidate.current_version.valid_from
    if target_start is not None and candidate_start is not None and candidate_start > target_start:
        return ConsolidationAction.SUPERSEDE, "newer_structured_value"
    return ConsolidationAction.CONFLICT, "conflicting_structured_value"


def _normalize_text(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def _token_overlap(left: str, right: str) -> float:
    left_tokens, right_tokens = set(_tokens(left)), set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    common = left_tokens & right_tokens
    if len(common) < 2:
        return 0.0
    return len(common) / min(len(left_tokens), len(right_tokens))
