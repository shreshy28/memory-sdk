from datetime import UTC, datetime

from memory_domain import Memory, RequestContext, Sensitivity
from memory_domain.policy import is_currently_eligible

from memory_retrieval.candidates import QueryPlan


def is_eligible(
    context: RequestContext, memory: Memory, plan: QueryPlan, *, now: datetime | None = None
) -> bool:
    instant = now or datetime.now(UTC)
    return (
        memory.tenant_id == context.tenant_id
        and memory.project_id == context.project_id
        and memory.subject_id == plan.subject_id
        and is_currently_eligible(memory, now=instant)
        and memory.current_version.sensitivity in plan.filters.sensitivities
        and (not plan.filters.kinds or memory.kind in plan.filters.kinds)
        and (
            plan.filters.collection_id is None or memory.collection_id == plan.filters.collection_id
        )
        and memory.current_version.sensitivity is not Sensitivity.RESTRICTED
    )
