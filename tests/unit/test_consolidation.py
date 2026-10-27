from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from memory_domain import (
    ConsolidationAction,
    ConsolidationInput,
    ConsolidationRejectedError,
    ConsolidationRejection,
    Memory,
    MemoryKind,
    MemoryStatus,
    MemoryVersion,
    ProvenanceMode,
    RequestContext,
    Sensitivity,
    propose_consolidation,
)


def memory(
    context: RequestContext,
    text: str,
    *,
    subject_id: UUID,
    collection_id: UUID | None = None,
    kind: MemoryKind = MemoryKind.PREFERENCE,
    sensitivity: Sensitivity = Sensitivity.GENERAL,
    structured_value: dict[str, object] | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    status: MemoryStatus = MemoryStatus.ACTIVE,
) -> Memory:
    now, memory_id = datetime.now(UTC), uuid4()
    version = MemoryVersion(
        uuid4(),
        memory_id,
        1,
        text,
        structured_value,
        0.8,
        0.7,
        sensitivity,
        now,
        context.principal_id,
        "test",
        valid_from,
        valid_to,
    )
    return Memory(
        memory_id,
        context.tenant_id,
        context.project_id,
        subject_id,
        kind,
        ProvenanceMode.OBSERVED,
        status,
        version,
        now,
        now,
        collection_id,
    )


def item(value: Memory) -> ConsolidationInput:
    return ConsolidationInput(value, value.current_version.id)


def test_exact_normalized_duplicates_propose_reinforcement_with_lineage() -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    target = memory(context, "The user prefers Jasmine tea.", subject_id=subject)
    candidate = memory(context, "  THE user prefers jasmine tea ", subject_id=subject)

    proposal = propose_consolidation(context, item(target), item(candidate))

    assert proposal.action is ConsolidationAction.REINFORCE
    assert proposal.target_memory_id == target.id
    assert proposal.candidate_memory_id == candidate.id
    assert proposal.source_version_ids == (
        target.current_version.id,
        candidate.current_version.id,
    )
    assert proposal.proposed_text == target.current_version.text


def test_overlapping_compatible_text_proposes_non_destructive_merge() -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    target = memory(context, "prefers jasmine tea in the morning", subject_id=subject)
    candidate = memory(context, "the user prefers jasmine tea in the morning", subject_id=subject)

    proposal = propose_consolidation(context, item(target), item(candidate))

    assert proposal.action is ConsolidationAction.MERGE
    assert proposal.proposed_text == candidate.current_version.text
    assert proposal.source_version_ids == (
        target.current_version.id,
        candidate.current_version.id,
    )


def test_different_structured_values_propose_conflict_without_overwriting() -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    target = memory(
        context,
        "favorite drink is tea",
        subject_id=subject,
        structured_value={"key": "favorite_drink", "value": "tea"},
    )
    candidate = memory(
        context,
        "favorite drink is coffee",
        subject_id=subject,
        structured_value={"key": "favorite_drink", "value": "coffee"},
    )

    proposal = propose_consolidation(context, item(target), item(candidate))

    assert proposal.action is ConsolidationAction.CONFLICT
    assert proposal.proposed_text is None
    assert proposal.source_version_ids == (
        target.current_version.id,
        candidate.current_version.id,
    )


def test_later_valid_structured_value_proposes_supersession() -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    earlier = datetime.now(UTC) - timedelta(days=2)
    later = earlier + timedelta(days=1)
    target = memory(
        context,
        "lives in London",
        subject_id=subject,
        structured_value={"key": "city", "value": "London"},
        valid_from=earlier,
    )
    candidate = memory(
        context,
        "lives in Paris",
        subject_id=subject,
        structured_value={"key": "city", "value": "Paris"},
        valid_from=later,
    )

    proposal = propose_consolidation(context, item(target), item(candidate))

    assert proposal.action is ConsolidationAction.SUPERSEDE
    assert proposal.proposed_text == "lives in Paris"


def test_unrelated_memories_propose_no_op() -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    target = memory(context, "prefers jasmine tea", subject_id=subject)
    candidate = memory(context, "runs marathons on weekends", subject_id=subject)

    proposal = propose_consolidation(context, item(target), item(candidate))

    assert proposal.action is ConsolidationAction.NO_OP
    assert proposal.proposed_text is None


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("tenant", ConsolidationRejection.UNAUTHORIZED),
        ("project", ConsolidationRejection.UNAUTHORIZED),
        ("subject", ConsolidationRejection.SCOPE_MISMATCH),
        ("collection", ConsolidationRejection.SCOPE_MISMATCH),
        ("kind", ConsolidationRejection.SCOPE_MISMATCH),
        ("sensitivity", ConsolidationRejection.SCOPE_MISMATCH),
    ],
)
def test_scope_and_policy_boundaries_reject_before_classification(
    change: str, expected: ConsolidationRejection
) -> None:
    context, subject, collection = RequestContext(uuid4(), uuid4(), uuid4()), uuid4(), uuid4()
    target = memory(context, "same text", subject_id=subject, collection_id=collection)
    candidate = memory(context, "same text", subject_id=subject, collection_id=collection)
    if change == "tenant":
        candidate = replace(candidate, tenant_id=uuid4())
    elif change == "project":
        candidate = replace(candidate, project_id=uuid4())
    elif change == "subject":
        candidate = replace(candidate, subject_id=uuid4())
    elif change == "collection":
        candidate = replace(candidate, collection_id=uuid4())
    elif change == "kind":
        candidate = replace(candidate, kind=MemoryKind.FACT)
    else:
        candidate = replace(
            candidate,
            current_version=replace(candidate.current_version, sensitivity=Sensitivity.SENSITIVE),
        )

    with pytest.raises(ConsolidationRejectedError) as captured:
        propose_consolidation(context, item(target), item(candidate))

    assert captured.value.reason is expected


@pytest.mark.parametrize(
    ("candidate_input", "expected"),
    [
        ("unauthorized", ConsolidationRejection.UNAUTHORIZED),
        ("suppressed", ConsolidationRejection.SUPPRESSED),
        ("stale", ConsolidationRejection.STALE_VERSION),
        ("deleted", ConsolidationRejection.INELIGIBLE),
        ("expired", ConsolidationRejection.INELIGIBLE),
    ],
)
def test_ineligible_candidates_are_rejected(
    candidate_input: str, expected: ConsolidationRejection
) -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    target = memory(context, "same text", subject_id=subject)
    candidate = memory(context, "same text", subject_id=subject)
    candidate_item = item(candidate)
    if candidate_input == "unauthorized":
        candidate_item = replace(candidate_item, authorized=False)
    elif candidate_input == "suppressed":
        candidate_item = replace(candidate_item, suppressed=True)
    elif candidate_input == "stale":
        candidate_item = replace(candidate_item, expected_version_id=uuid4())
    elif candidate_input == "deleted":
        candidate_item = item(replace(candidate, status=MemoryStatus.DELETED))
    else:
        expired = replace(
            candidate,
            current_version=replace(
                candidate.current_version, valid_to=datetime.now(UTC) - timedelta(seconds=1)
            ),
        )
        candidate_item = item(expired)

    with pytest.raises(ConsolidationRejectedError) as captured:
        propose_consolidation(context, item(target), candidate_item)

    assert captured.value.reason is expected


def test_self_candidate_is_rejected() -> None:
    context, subject = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    target = memory(context, "same text", subject_id=subject)

    with pytest.raises(ConsolidationRejectedError) as captured:
        propose_consolidation(context, item(target), item(target))

    assert captured.value.reason is ConsolidationRejection.SELF_CANDIDATE
