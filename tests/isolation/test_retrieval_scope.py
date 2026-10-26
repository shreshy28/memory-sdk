from datetime import UTC, datetime
from uuid import uuid4

from memory_domain import (
    Memory,
    MemoryKind,
    MemoryStatus,
    MemoryVersion,
    ProvenanceMode,
    RequestContext,
    Sensitivity,
)
from memory_retrieval.candidates import QueryPlan, SearchFilters
from memory_retrieval.eligibility import is_eligible


def test_canonical_eligibility_fails_closed_across_scope_and_policy() -> None:
    context, now = RequestContext(uuid4(), uuid4(), uuid4()), datetime.now(UTC)
    subject, memory_id = uuid4(), uuid4()
    version = MemoryVersion(
        uuid4(),
        memory_id,
        1,
        "secret",
        None,
        1.0,
        1.0,
        Sensitivity.RESTRICTED,
        now,
        uuid4(),
        "test",
    )
    memory = Memory(
        memory_id,
        context.tenant_id,
        context.project_id,
        subject,
        MemoryKind.FACT,
        ProvenanceMode.EXPLICIT,
        MemoryStatus.ACTIVE,
        version,
        now,
        now,
    )
    plan = QueryPlan(
        "secret", subject, SearchFilters(sensitivities=(Sensitivity.RESTRICTED,)), 10, 20
    )

    assert not is_eligible(context, memory, plan)
    assert not is_eligible(
        RequestContext(uuid4(), context.project_id, context.principal_id), memory, plan
    )
