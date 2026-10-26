from typing import Any

from memory_domain import RequestContext
from memory_retrieval import Candidate, QueryPlan
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from memory_postgres.rls import set_trusted_scope


class PostgresLexicalSearch:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def search(
        self,
        context: RequestContext,
        plan: QueryPlan,
        query_vector: tuple[float, ...] | None = None,
    ) -> tuple[Candidate, ...]:
        del query_vector
        conditions, parameters = _scope_conditions(context, plan)
        parameters["query"] = plan.query
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT m.id, v.id AS version_id, "
                            "ts_rank_cd(to_tsvector('simple', v.text), "
                            "plainto_tsquery('simple', :query)) AS score "
                            "FROM memories m JOIN memory_versions v ON v.id = m.current_version_id "
                            "LEFT JOIN suppression_markers s ON s.memory_id = m.id "
                            f"WHERE {' AND '.join(conditions)} AND "
                            "to_tsvector('simple', v.text) @@ plainto_tsquery('simple', :query) "
                            "ORDER BY score DESC, m.id LIMIT :limit"
                        ),
                        parameters,
                    )
                )
                .mappings()
                .all()
            )
        return tuple(
            Candidate(row["id"], row["version_id"], rank, float(row["score"]))
            for rank, row in enumerate(rows, 1)
        )


def _scope_conditions(context: RequestContext, plan: QueryPlan) -> tuple[list[str], dict[str, Any]]:
    conditions = [
        "m.tenant_id = :tenant",
        "m.project_id = :project",
        "m.subject_id = :subject",
        "m.status = 'active'",
        "s.memory_id IS NULL",
        "(v.valid_from IS NULL OR v.valid_from <= now())",
        "(v.valid_to IS NULL OR v.valid_to > now())",
        "v.sensitivity = ANY(:sensitivities)",
    ]
    parameters: dict[str, Any] = {
        "tenant": context.tenant_id,
        "project": context.project_id,
        "subject": plan.subject_id,
        "sensitivities": [item.value for item in plan.filters.sensitivities],
        "limit": plan.candidate_limit,
    }
    if plan.filters.kinds:
        conditions.append("m.kind = ANY(:kinds)")
        parameters["kinds"] = [item.value for item in plan.filters.kinds]
    if plan.filters.collection_id is not None:
        conditions.append("m.collection_id = :collection")
        parameters["collection"] = plan.filters.collection_id
    return conditions, parameters
